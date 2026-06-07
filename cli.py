"""CLI entry point — Factor #11: trigger from anywhere.

Usage:
    python cli.py crawl "https://youtube.com/watch?v=xxx" --keyword "hiking tips"
    python cli.py crawl "https://example.com/article" --source web
    python cli.py knowledge --show
"""

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from state import make_state
from knowledge import load_knowledge, save_knowledge
from llm import LLM
from reducer import crawl


def main():
    parser = argparse.ArgumentParser(description="AI Crawler v2 — 12-Factor Agents")
    sub = parser.add_subparsers(dest="command")

    # crawl command
    p_crawl = sub.add_parser("crawl", help="Crawl a URL")

    # setup command
    p_setup = sub.add_parser("setup", help="First-run setup (YouTube cookies)")
    p_setup.add_argument("--check", action="store_true", help="Check if cookies are valid")
    p_crawl.add_argument("url", help="URL to crawl")
    p_crawl.add_argument("--source", default="youtube", choices=["youtube", "web", "reddit"])
    p_crawl.add_argument("--keyword", default="", help="Target keyword")
    p_crawl.add_argument("--content-type", default="Beginner Guide")
    p_crawl.add_argument("--target-words", type=int, default=1200)
    p_crawl.add_argument("--min-score", type=int, default=70, help="Min verify score")
    p_crawl.add_argument("--knowledge", default="knowledge.json", help="Knowledge file path")
    p_crawl.add_argument("--save-state", default="", help="Save state to file (for pause/resume)")
    p_crawl.add_argument("--load-state", default="", help="Load state from file (resume)")
    p_crawl.add_argument("-v", "--verbose", action="store_true")

    # knowledge command
    p_know = sub.add_parser("knowledge", help="View/manage knowledge")
    p_know.add_argument("--show", action="store_true", help="Show knowledge summary")
    p_know.add_argument("--path", default="knowledge.json")

    # dashboard command
    p_dash = sub.add_parser("dashboard", help="Launch web dashboard")
    p_dash.add_argument("--port", type=int, default=8080)
    p_dash.add_argument("--host", default="0.0.0.0")

    args = parser.parse_args()

    # Logging
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.command == "crawl":
        cmd_crawl(args)
    elif args.command == "setup":
        from setup import cmd_setup
        cmd_setup(args)
    elif args.command == "knowledge":
        cmd_knowledge(args)
    elif args.command == "dashboard":
        import uvicorn
        uvicorn.run("web.app:app", host=args.host, port=args.port, reload=True)
    else:
        parser.print_help()


def cmd_crawl(args):
    """Execute a crawl."""
    from setup import check_cookies, COOKIES_PATH
    if args.source == "youtube" and not _has_cookies():
        print("⚠️  YouTube 爬取需要 cookies（云服务器 IP 被 YouTube 封锁）")
        print()
        print("首次使用，请先导出你的 YouTube cookies：")
        print()
        print("  在你的电脑上运行：")
        print("    yt-dlp --cookies-from-browser chrome --cookies cookies.txt \\")
        print("           'https://www.youtube.com' --skip-download")
        print()
        print("  然后上传到服务器：")
        print(f"    scp cookies.txt <user>@<server>:{COOKIES_PATH}")
        print()
        print("  或直接运行引导：")
        print("    python cli.py setup")
        print()
        sys.exit(1)

    knowledge = load_knowledge(args.knowledge)
    llm = LLM()

    # Load or create state
    if args.load_state:
        state = make_state.__func__.__class__.load(args.load_state)
        print(f"Resumed from: {args.load_state}")
    else:
        state = make_state(
            url=args.url,
            source=args.source,
            keyword=args.keyword,
            content_type=args.content_type,
            target_words=args.target_words,
        )

    # Auto-create states dir for WAL (Factor #6)
    state_dir = Path(args.knowledge).parent / "states"
    state_dir.mkdir(parents=True, exist_ok=True)
    state_hash = f"{hash(state.url) & 0xFFFFFF:06x}"
    auto_state_path = str(state_dir / f"{state_hash}.json")

    # Run reducer with WAL auto-save
    print(f"\nCrawling: {state.url}")
    print(f"Source: {state.source.value} | Keyword: {state.keyword}")
    print("-" * 50)

    state = crawl(state, knowledge, llm, state_path=auto_state_path)

    # Save state if requested
    if args.save_state:
        state.save(args.save_state)
        print(f"State saved: {args.save_state}")

    # Save knowledge
    save_knowledge(knowledge, args.knowledge)

    # Print result
    print("-" * 50)
    print(f"Result: {state.step.value}")
    if state.html_path:
        print(f"HTML: {state.html_path}")
    if state.verify:
        print(f"Score: {state.verify.score}/100 (passed={state.verify.passed})")
    if state.error:
        print(f"Error: {state.error}")
    if state.failure_report:
        print(f"\nFAILED - needs human review:")
        print(f"  URL: {state.failure_report['url']}")
        print(f"  Error: {state.failure_report['error']}")
        print(f"  Attempts: {state.failure_report['attempts']}")

    # Print event timeline
    print(f"\nEvents ({len(state.events)}):")
    for evt in state.events:
        icon = "+" if evt.success else "x"
        print(f"  [{icon}] {evt.tool}: {evt.message}")


def _has_cookies() -> bool:
    """Check if any valid cookies file exists."""
    from setup import COOKIES_PATH
    candidates = [
        COOKIES_PATH,
        Path.home() / "yt_cookies.txt",
    ]
    return any(c.exists() and c.stat().st_size > 200 for c in candidates)


def cmd_knowledge(args):
    """Show knowledge summary."""
    knowledge = load_knowledge(args.path)
    print(f"Crawled URLs: {len(knowledge.crawled_urls)}")
    print(f"Site patterns: {len(knowledge.site_patterns)}")
    print(f"Failure log: {len(knowledge.failure_log)} entries")
    print(f"Prompt stats: {len(knowledge.prompt_stats)} prompts")

    if knowledge.prompt_stats:
        print("\nPrompt performance:")
        for path, stats in knowledge.prompt_stats.items():
            print(f"  {path}: avg={stats.avg_score:.1f} ({stats.count} samples)")


if __name__ == "__main__":
    main()

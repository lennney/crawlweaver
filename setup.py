"""First-run setup — guide user through cookies configuration (Factor #11).

Usage:
    python cli.py setup              # Interactive setup
    python cli.py setup --check      # Check if cookies are valid
"""

import subprocess
import sys
from pathlib import Path

COOKIES_PATH = Path(__file__).parent / "yt_cookies.txt"
DIYHUB_COOKIES = Path.home() / "diyhub" / "yt_cookies.txt"


def cmd_setup(args):
    """First-run setup: configure YouTube cookies."""

    if args.check:
        return check_cookies()

    print("=" * 60)
    print("  AI Crawler v2 — 首次设置")
    print("=" * 60)
    print()

    # Step 1: Check if cookies already exist
    if check_cookies():
        print("\nCookies 已配置且可用，无需重新设置。")
        print(f"如需刷新，删除 {COOKIES_PATH} 后重新运行 setup。")
        return

    print("YouTube 字幕提取需要 cookies 认证（云服务器 IP 被 YouTube 封锁）。")
    print()
    print("请选择 cookies 来源：")
    print()
    print("  [1] 从本地浏览器导出（推荐）")
    print("      在你的电脑上运行：")
    print("      yt-dlp --cookies-from-browser chrome --cookies yt_cookies.txt \\")
    print("             'https://www.youtube.com' --skip-download")
    print("      然后上传到服务器：")
    print(f"      scp yt_cookies.txt hermes@<server-ip>:{COOKIES_PATH}")
    print()
    print("  [2] 从 Firefox 导出")
    print("      yt-dlp --cookies-from-browser firefox --cookies yt_cookies.txt \\")
    print("             'https://www.youtube.com' --skip-download")
    print()
    print("  [3] 手动提供 cookies 文件路径")
    print()

    choice = input("选择 (1/2/3) 或直接粘贴文件路径: ").strip()

    if choice == "1" or choice == "2":
        browser = "chrome" if choice == "1" else "firefox"
        print(f"\n请在你的电脑上运行：")
        print(f"  yt-dlp --cookies-from-browser {browser} --cookies yt_cookies.txt \\")
        print(f"         'https://www.youtube.com' --skip-download")
        print(f"\n然后上传到服务器：")
        print(f"  scp yt_cookies.txt hermes@<server-ip>:{COOKIES_PATH}")
        print(f"\n上传完成后，运行: python cli.py setup --check")
    elif choice == "3":
        path = input("输入 cookies 文件路径: ").strip()
        src = Path(path).expanduser()
        if not src.exists():
            print(f"文件不存在: {src}")
            sys.exit(1)
        import shutil
        shutil.copy2(src, COOKIES_PATH)
        print(f"已复制到 {COOKIES_PATH}")
        check_cookies()
    else:
        # Treat as file path
        src = Path(choice).expanduser()
        if src.exists():
            import shutil
            shutil.copy2(src, COOKIES_PATH)
            print(f"已复制到 {COOKIES_PATH}")
            check_cookies()
        else:
            print(f"无效选择或文件不存在: {choice}")
            sys.exit(1)


def check_cookies() -> bool:
    """Check if cookies exist and are valid."""
    # Check v2 local
    candidates = [
        COOKIES_PATH,
        Path.home() / "yt_cookies.txt",
        DIYHUB_COOKIES,
    ]

    found = None
    for c in candidates:
        if c.exists() and c.stat().st_size > 200:
            found = c
            break

    if not found:
        print("❌ 未找到 YouTube cookies 文件")
        print(f"   期望位置: {COOKIES_PATH}")
        return False

    # Quick validation: try yt-dlp
    print(f"🔍 测试 cookies: {found}")
    try:
        result = subprocess.run(
            ["yt-dlp", "--cookies", str(found), "--skip-download",
             "--print", "title", "https://www.youtube.com/watch?v=aircAruvnKk"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            title = result.stdout.strip()
            print(f"✅ Cookies 有效！测试视频: {title}")

            # Copy to v2 location if not already there
            if found != COOKIES_PATH:
                import shutil
                shutil.copy2(found, COOKIES_PATH)
                print(f"   已复制到 {COOKIES_PATH}")

            return True
        else:
            print(f"❌ Cookies 无效或已过期")
            print(f"   错误: {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False

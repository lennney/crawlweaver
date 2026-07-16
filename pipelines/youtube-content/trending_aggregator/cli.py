"""观测平台 CLI — 唯一入口。

用法:
    python trending_aggregator/cli.py                         # 跑全部平台 (默认 scouts)
    python trending_aggregator/cli.py --platform tiktok       # 只跑一个
    python trending_aggregator/cli.py tags                    # 按 tag 搜索（所有平台）
    python trending_aggregator/cli.py --platform tiktok tags  # 只搜 TK
    python trending_aggregator/cli.py tags --tag-file data/tags.txt  # 自定义 tag 列表
    python trending_aggregator/cli.py account list                   # 列出追踪账号
    python trending_aggregator/cli.py account add --platform tiktok netflix  # 添加账号
    python trending_aggregator/cli.py account remove 1               # 删除账号
    python trending_aggregator/cli.py account fetch                  # 跑账号采集
"""
import argparse
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from trending_aggregator.orchestrator import run_all, run_scout

load_dotenv()

logger = logging.getLogger("trending_aggregator")

# 默认 tag 列表：编辑 data/tags.txt 或通过 --tag-file 传入
DEFAULT_TAG_FILE = Path(__file__).parent.parent / "data" / "tags.txt"
DEFAULT_TAGS = ["movie", "kdrama", "film", "netflix", "series", "drama"]


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )

    parser = argparse.ArgumentParser(description="观测平台 — 采集热门视频数据")
    parser.add_argument(
        "--platform", choices=["youtube", "tiktok", "all"], default="all",
        help="指定平台 (默认: all)。与 tags 子命令共用时限定平台",
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    # tags 子命令
    tag_parser = sub.add_parser("tags", help="按 #tag 搜索高播视频")
    tag_parser.add_argument(
        "--tag-file", type=Path, default=None,
        help="tag 列表文件（每行一个，可带 #）",
    )
    tag_parser.add_argument(
        "--min-views", type=int, default=500_000,
    )
    tag_parser.add_argument(
        "--min-likes", type=int, default=30_000,
    )
    tag_parser.add_argument(
        "--max-videos", type=int, default=100,
        help="TK trending 扫描上限（TK 无直接 tag API，从热门中按文本筛选）",
    )
    tag_parser.add_argument(
        "--videos-per-tag", type=int, default=30,
        help="YTB 每个 tag 搜索条数",
    )
    tag_parser.add_argument(
        "--no-lang-filter", action="store_true",
        help="关闭语言过滤",
    )
    tag_parser.add_argument(
        "--max-duration", type=int, default=None,
        help="最大时长（秒），设 120 只抓 Shorts",
    )

    # account 子命令
    acct_parser = sub.add_parser("account", help="账号追踪管理")
    acct_sub = acct_parser.add_subparsers(dest="account_action")

    acct_list = acct_sub.add_parser("list", help="列出追踪账号")
    acct_list.add_argument("--platform", choices=["youtube", "tiktok"], default=None, help="按平台筛选")
    acct_list.add_argument("--category", default=None, help="按分类筛选（kdrama, movie, brand...）")
    acct_list.add_argument("--active-only", action="store_true", default=True, help="只显示活跃账号（默认）")
    acct_list.add_argument("--all", action="store_true", dest="show_all", help="显示所有账号（含停用）")

    acct_add = acct_sub.add_parser("add", help="添加追踪账号")
    acct_add.add_argument("--platform", choices=["youtube", "tiktok"], required=True)
    acct_add.add_argument("--category", default=None, help="分类（kdrama, movie, brand...）")
    acct_add.add_argument("--name", default=None, help="显示名（可选）")
    acct_add.add_argument("--note", default=None, help="备注（粉丝数等）")
    acct_add.add_argument("usernames", nargs="+", help="账号名（无需 @ 前缀，支持多个）")

    acct_remove = acct_sub.add_parser("remove", help="删除追踪账号")
    acct_remove.add_argument("id", type=int, help="账号 ID（从 list 查看）")

    acct_fetch = acct_sub.add_parser("fetch", help="运行账号采集")

    acct_import = acct_sub.add_parser("import", help="从 CSV 文件批量导入账号")
    acct_import.add_argument("--file", "-f", type=Path, required=True, help="CSV 文件路径")
    acct_import.add_argument("--dry-run", action="store_true", help="预览导入内容，不实际写入")

    args = parser.parse_args()

    if args.command == "tags":
        _run_tags(args)
    elif args.command == "account":
        _run_account(args)
    else:
        _run_scout(args)


def _run_scout(args):
    if args.platform == "all":
        logger.info("观测平台启动 — 全部数据源")
        results = run_all()
        for platform, count in results.items():
            logger.info("  %s: %s 条", platform, count)
    else:
        from trending_aggregator.orchestrator import _default_scouts
        scout = next(s for s in _default_scouts() if s.platform == args.platform)
        count = run_scout(scout)
        logger.info("%s: %s 条入库", args.platform, count)


def _run_tags(args):
    """按 tag 搜索 + 过滤 + 入库。"""
    tags = _load_tags(args.tag_file)

    from trending_aggregator.orchestrator import run_all as run_scouts
    from trending_aggregator.scouts.tiktok_tag import TikTokTagScout
    from trending_aggregator.scouts.youtube_tag import YouTubeTagScout

    scouts = []
    if args.platform in ("all", "tiktok"):
        scouts.append(TikTokTagScout(
            tags=tags,
            min_views=args.min_views,
            min_likes=args.min_likes,
            language_filter=not args.no_lang_filter,
            max_videos=args.max_videos,
        ))
    if args.platform in ("all", "youtube"):
        scouts.append(YouTubeTagScout(
            tags=tags,
            min_views=args.min_views,
            min_likes=args.min_likes,
            language_filter=not args.no_lang_filter,
            videos_per_tag=args.videos_per_tag,
            max_duration=args.max_duration,
        ))

    if not scouts:
        logger.error("没有匹配的采集器，跳过")
        return

    results = run_scouts(scouts)
    for platform, count in results.items():
        logger.info("  %s: %s 条入库", platform, count)


def _load_tags(tag_file: Path | None) -> list[str]:
    """从文件加载 tag 列表。"""
    if tag_file and tag_file.exists():
        with open(tag_file) as f:
            tags = [line.strip().lstrip("#") for line in f if line.strip()]
        if tags:
            return tags
        logger.warning("tag 文件 %s 为空，使用默认 tag", tag_file)
    return DEFAULT_TAGS


def _get_db_session():
    """获取 DB session（SQLite dev 或 PG）。"""
    from sqlalchemy import create_engine
    from factory.models import Base, get_session

    db_url = os.environ.get("DATABASE_URL", "sqlite:///dev.db")
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    return get_session(engine)


def _run_account(args):
    """账号管理：list / add / remove / fetch / import。"""
    from factory.models import TrackedAccount

    if args.account_action == "list":
        session = _get_db_session()
        try:
            q = session.query(TrackedAccount)
            # 过滤
            if not args.show_all:
                q = q.filter_by(active=True)
            if args.platform:
                q = q.filter_by(platform=args.platform)
            if args.category:
                q = q.filter_by(category=args.category)
            q = q.order_by(TrackedAccount.id)

            accounts = q.all()
            if not accounts:
                logger.info("没有匹配的追踪账号")
                return

            print(f"  {'ID':>3} {'平台':>8} {'分类':>12} {'用户名':>20} {'视频':>5} {'上次采集':>12}  显示名")
            print(f"  {'-'*75}")
            for a in accounts:
                status = "🟢" if a.active else "🔴"
                cat = a.category or "-"
                last_fetch = a.last_fetched_at.strftime("%m-%d %H:%M") if a.last_fetched_at else "-"
                vc = a.video_count or 0
                print(f"  {status}{a.id:>3} {a.platform:>8} {cat:>12} @{a.username:<18} {vc:>4} {last_fetch:>12}  {a.display_name or ''}")
        finally:
            session.close()

    elif args.account_action == "add":
        session = _get_db_session()
        try:
            added = 0
            for username in args.usernames:
                username = username.lstrip("@")
                existing = session.query(TrackedAccount).filter_by(
                    platform=args.platform, username=username,
                ).first()
                if existing:
                    logger.info("⏭️ 已存在: %s/%s", args.platform, username)
                    continue
                acct = TrackedAccount(
                    platform=args.platform,
                    username=username,
                    display_name=args.name,
                    category=args.category,
                    notes=args.note,
                )
                session.add(acct)
                added += 1
            session.commit()
            logger.info("✅ 添加 %s 个账号到 %s", added, args.platform)
        finally:
            session.close()

    elif args.account_action == "remove":
        session = _get_db_session()
        try:
            acct = session.get(TrackedAccount, args.id)
            if not acct:
                logger.error("账号 ID %s 不存在", args.id)
                return
            session.delete(acct)
            session.commit()
            logger.info("🗑️ 删除账号: [%s] %s/%s", args.id, acct.platform, acct.username)
        finally:
            session.close()

    elif args.account_action == "import":
        _run_account_import(args)

    elif args.account_action == "fetch":
        from trending_aggregator.orchestrator import run_all as run_scouts
        from trending_aggregator.scouts.account import AccountScout

        scout = AccountScout()
        results = run_scouts([scout])
        for platform, count in results.items():
            logger.info("  %s: %s 条入库", platform, count)


def _run_account_import(args):
    """从 CSV 文件批量导入账号。"""
    import csv
    from factory.models import TrackedAccount

    path = args.file
    if not path.exists():
        logger.error("文件不存在: %s", path)
        return

    with open(path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if args.dry_run:
        logger.info("🔍 预览导入（%s 条）:", len(rows))
        print(f"  {'平台':>8} {'用户名':>20} {'显示名':>20} {'分类':>12}")
        print(f"  {'-'*65}")
        for r in rows:
            print(f"  {r.get('platform',''):>8} @{r.get('username',''):<18} {r.get('display_name',''):>20} {r.get('category',''):>12}")
        return

    session = _get_db_session()
    try:
        added = 0
        for r in rows:
            platform = r.get("platform", "").strip()
            username = r.get("username", "").strip().lstrip("@")
            display_name = r.get("display_name", "").strip() or None
            category = r.get("category", "").strip() or None
            notes = r.get("notes", "").strip() or None

            if not platform or not username:
                continue

            existing = session.query(TrackedAccount).filter_by(
                platform=platform, username=username,
            ).first()
            if existing:
                continue

            session.add(TrackedAccount(
                platform=platform, username=username,
                display_name=display_name, category=category, notes=notes,
            ))
            added += 1
        session.commit()
        logger.info("✅ 从 %s 导入 %s 个账号", path.name, added)
    finally:
        session.close()


if __name__ == "__main__":
    main()

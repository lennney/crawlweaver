"""账号追踪 CLI — 独立入口，不依赖 AI 管线。

用法:
    python -m trending_aggregator.account_tracker list
    python -m trending_aggregator.account_tracker add --platform tiktok --category kdrama user1 user2
    python -m trending_aggregator.account_tracker remove 1
    python -m trending_aggregator.account_tracker import --file accounts.csv
    python -m trending_aggregator.account_tracker fetch [--detailed]
    python -m trending_aggregator.account_tracker export [--format csv|json] [--output path]
    python -m trending_aggregator.account_tracker report [--top 20]
    python -m trending_aggregator.account_tracker daily-report [--date YYYY-MM-DD] [--format table|csv]
"""
import argparse
import csv
import json
import logging
import re
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

from .models import TrackedAccount, VideoSnapshot, AccountSnapshot, get_session

logger = logging.getLogger("account_tracker")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="账号追踪 — 独立模块")
    sub = parser.add_subparsers(dest="action", required=True)

    # list
    list_p = sub.add_parser("list", help="列出追踪账号")
    list_p.add_argument("--platform", choices=["youtube", "tiktok"], default=None)
    list_p.add_argument("--category", default=None)
    list_p.add_argument("--all", action="store_true", dest="show_all", help="含停用账号")

    # add
    add_p = sub.add_parser("add", help="批量添加账号")
    add_p.add_argument("--platform", choices=["youtube", "tiktok"], required=True)
    add_p.add_argument("--category", default=None)
    add_p.add_argument("--name", default=None, help="显示名")
    add_p.add_argument("--note", default=None, help="备注")
    add_p.add_argument("usernames", nargs="+", help="账号名（无需 @）")

    # remove
    rm_p = sub.add_parser("remove", help="删除账号")
    rm_p.add_argument("id", type=int, help="账号 ID")

    # import
    imp_p = sub.add_parser("import", help="从 CSV 导入")
    imp_p.add_argument("--file", "-f", type=Path, required=True)
    imp_p.add_argument("--dry-run", action="store_true")

    # fetch
    fetch_p = sub.add_parser("fetch", help="采集所有活跃账号")
    fetch_p.add_argument("--detailed", action="store_true", help="获取真实 views/likes（慢但准，仅 YouTube）")

    # export
    export_p = sub.add_parser("export", help="导出数据")
    export_p.add_argument("--format", choices=["csv", "json"], default="csv")
    export_p.add_argument("--output", "-o", type=Path, default=None, help="输出文件（默认 stdout）")
    export_p.add_argument("--table", choices=["accounts", "snapshots", "latest"], default="latest",
                          help="导出哪张表: accounts=账号列表, snapshots=全部快照, latest=每条视频最新状态（默认）")

    # report
    report_p = sub.add_parser("report", help="统计摘要")
    report_p.add_argument("--top", type=int, default=20, help="显示 Top N 视频（默认 20）")
    report_p.add_argument("--days", type=int, default=7, help="分析最近 N 天（默认 7）")

    # daily-report
    daily_p = sub.add_parser("daily-report", help="每日运营报表 — 昨日发布内容的浏览量/点赞/粉丝数/涨粉")
    daily_p.add_argument("--date", default=None, help="指定日期 YYYY-MM-DD（默认昨天）")
    daily_p.add_argument("--format", choices=["table", "csv"], default="table", help="输出格式")

    # trending-report
    trending_p = sub.add_parser("trending-report", help="推流报告 — 每个账号今日推流 top 3 视频")
    trending_p.add_argument("--date", default=None, help="指定日期 YYYY-MM-DD（默认昨天）")
    trending_p.add_argument("--top", type=int, default=3, help="每个账号显示 Top N 视频（默认 3）")
    trending_p.add_argument("--format", choices=["table", "csv"], default="table", help="输出格式")

    args = parser.parse_args()

    if args.action == "list":
        _list(args)
    elif args.action == "add":
        _add(args)
    elif args.action == "remove":
        _remove(args)
    elif args.action == "import":
        _import_csv(args)
    elif args.action == "fetch":
        _fetch(args)
    elif args.action == "export":
        _export(args)
    elif args.action == "report":
        _report(args)
    elif args.action == "daily-report":
        _daily_report(args)
    elif args.action == "trending-report":
        _trending_report(args)


def _list(args):
    session = get_session()
    try:
        q = session.query(TrackedAccount)
        if not args.show_all:
            q = q.filter_by(active=True)
        if args.platform:
            q = q.filter_by(platform=args.platform)
        if args.category:
            q = q.filter_by(category=args.category)
        q = q.order_by(TrackedAccount.id).all()

        if not q:
            logger.info("无匹配账号")
            return
        print(f"  {'ID':>3} {'平台':>8} {'分类':>12} {'用户名':>20} {'视频':>5} {'上次采集':>12}  显示名")
        print(f"  {'-'*75}")
        for a in q:
            s = "🟢" if a.active else "🔴"
            lf = a.last_fetched_at.strftime("%m-%d %H:%M") if a.last_fetched_at else "-"
            print(f"  {s}{a.id:>3} {a.platform:>8} {a.category or '-':>12} @{a.username:<18} {a.video_count or 0:>4} {lf:>12}  {a.display_name or ''}")
    finally:
        session.close()


def _add(args):
    session = get_session()
    try:
        added = 0
        for u in args.usernames:
            u = u.lstrip("@")
            exists = session.query(TrackedAccount).filter_by(platform=args.platform, username=u).first()
            if exists:
                logger.info("⏭️ 已存在: %s/%s", args.platform, u)
                continue
            session.add(TrackedAccount(
                platform=args.platform, username=u,
                display_name=args.name, category=args.category, notes=args.note,
            ))
            added += 1
        session.commit()
        logger.info("✅ 添加 %s 个", added)
    finally:
        session.close()


def _remove(args):
    session = get_session()
    try:
        a = session.get(TrackedAccount, args.id)
        if not a:
            logger.error("ID %s 不存在", args.id)
            return
        session.delete(a)
        session.commit()
        logger.info("🗑️ 删除 [%s] %s/%s", args.id, a.platform, a.username)
    finally:
        session.close()


def _import_csv(args):
    path = args.file
    if not path.exists():
        logger.error("文件不存在: %s", path)
        return
    with open(path) as f:
        rows = list(csv.DictReader(f))

    if args.dry_run:
        logger.info("🔍 预览 %s 条:", len(rows))
        print(f"  {'平台':>8} {'用户名':>20} {'显示名':>20} {'分类':>12}")
        print(f"  {'-'*65}")
        for r in rows:
            print(f"  {r.get('platform',''):>8} @{r.get('username',''):<18} {r.get('display_name',''):>20} {r.get('category',''):>12}")
        return

    session = get_session()
    try:
        added = 0
        for r in rows:
            platform = r.get("platform", "").strip()
            username = r.get("username", "").strip().lstrip("@")
            if not platform or not username:
                continue
            exists = session.query(TrackedAccount).filter_by(platform=platform, username=username).first()
            if exists:
                continue
            session.add(TrackedAccount(
                platform=platform, username=username,
                display_name=r.get("display_name", "").strip() or None,
                category=r.get("category", "").strip() or None,
                notes=r.get("notes", "").strip() or None,
            ))
            added += 1
        session.commit()
        logger.info("✅ 从 %s 导入 %s 个", path.name, added)
    finally:
        session.close()


def _fetch(args):
    from .scout import AccountScout
    scout = AccountScout(detailed=args.detailed)
    videos = scout.scrape()
    logger.info("合计: %s 条视频", len(videos))
    if args.detailed:
        logger.info("（--detailed 模式: YouTube 数据为真实 views/likes）")


def _export(args):
    """导出 CSV 或 JSON。"""
    session = get_session()
    try:
        if args.table == "accounts":
            rows = session.query(TrackedAccount).order_by(TrackedAccount.id).all()
            fields = ["id", "platform", "username", "display_name", "category", "active", "video_count", "last_fetched_at"]
            data = [{f: getattr(r, f) for f in fields} for r in rows]
        elif args.table == "snapshots":
            rows = session.query(VideoSnapshot).order_by(VideoSnapshot.fetched_at.desc()).limit(10000).all()
            fields = ["id", "video_id", "platform", "title", "views", "likes", "comments", "shares", "fetched_at"]
            data = [{f: getattr(r, f) for f in fields} for r in rows]
        else:  # latest — 每条视频的最新一条快照
            # subquery: max fetched_at per video_id
            subq = (
                session.query(
                    VideoSnapshot.video_id,
                    VideoSnapshot.fetched_at,
                )
                .order_by(VideoSnapshot.fetched_at.desc())
                .distinct()
                .subquery()
            )
            # ponytail: O(n²) 对小数据量够用；千万级建索引后用窗口函数
            latest = []
            seen = set()
            for r in session.query(VideoSnapshot).order_by(VideoSnapshot.fetched_at.desc()).all():
                if r.video_id not in seen:
                    seen.add(r.video_id)
                    latest.append(r)
            fields = ["video_id", "platform", "title", "url", "views", "likes", "comments", "shares", "duration", "fetched_at"]
            data = [{f: getattr(r, f) for f in fields} for r in latest]

        if args.format == "json":
            output = json.dumps(data, indent=2, default=str, ensure_ascii=False)
        else:
            import io
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            w.writerows(data)
            output = buf.getvalue()

        if args.output:
            args.output.write_text(output, encoding="utf-8")
            logger.info("✅ 已写入 %s （%s 条）", args.output, len(data))
        else:
            print(output)
    finally:
        session.close()


def _report(args):
    """统计摘要 + Top N 视频。"""
    session = get_session()
    try:
        cutoff = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ) - __import__("datetime").timedelta(days=args.days)

        # ---- 账号概况 ----
        total_accts = session.query(TrackedAccount).filter_by(active=True).count()
        from sqlalchemy import func
        plat_counts = (
            session.query(TrackedAccount.platform, func.count(TrackedAccount.id))
            .filter_by(active=True)
            .group_by(TrackedAccount.platform)
            .all()
        )
        cat_counts = (
            session.query(TrackedAccount.category, func.count(TrackedAccount.id))
            .filter_by(active=True)
            .group_by(TrackedAccount.category)
            .all()
        )

        # ---- 快照统计 ----
        total_snapshots = session.query(VideoSnapshot).count()
        recent_snapshots = session.query(VideoSnapshot).filter(
            VideoSnapshot.fetched_at >= cutoff
        ).count()

        fetch_days = (
            session.query(func.date(VideoSnapshot.fetched_at), func.count(VideoSnapshot.id))
            .filter(VideoSnapshot.fetched_at >= cutoff)
            .group_by(func.date(VideoSnapshot.fetched_at))
            .order_by(func.date(VideoSnapshot.fetched_at).desc())
            .all()
        )

        # ---- Top N 视频（最新快照） ----
        seen = set()
        top = []
        for r in session.query(VideoSnapshot).order_by(VideoSnapshot.views.desc()).all():
            if r.video_id not in seen:
                seen.add(r.video_id)
                top.append(r)
            if len(top) >= args.top:
                break

        # ---- 输出 ----
        print(f"\n📊 账号追踪报告（最近 {args.days} 天）\n")
        print(f"  活跃账号: {total_accts}")
        for p, c in plat_counts:
            print(f"    {p}: {c}")
        print()
        for cat, c in cat_counts:
            if cat:
                print(f"    {cat}: {c}")
        print()
        print(f"  快照总数: {total_snapshots}")
        print(f"  近期采集: {recent_snapshots} 条")
        print()
        print(f"  采集日历:")
        for day, cnt in fetch_days:
            print(f"    {day}: {cnt} 条快照")
        print()
        print(f"  Top {args.top} 视频（按播放量）:")
        print(f"    {'#':>3} {'播放量':>10} {'点赞':>8} {'平台':>8} {'视频 ID':>30}  标题")
        print(f"    {'-'*80}")
        for i, r in enumerate(top, 1):
            vid = r.video_id
            if len(vid) > 28:
                vid = vid[:25] + "..."
            print(f"    {i:>3} {r.views:>10,} {r.likes:>8,} {r.platform:>8} {vid:>30}  {r.title[:30]}")
    finally:
        session.close()


def _daily_report(args):
    """每日运营报表 — 昨日发布内容的浏览量/点赞/粉丝数/涨粉。

    查询逻辑:
      1. 确定目标日期（默认昨天）
      2. 从 video_snapshots 找 published_at 在目标日期的视频，取最新一条快照
      3. 关联 tracked_accounts 获取粉丝数
      4. 查询 account_snapshots 计算涨粉（今天 vs 昨天）
      5. 输出表格
    """
    session = get_session()
    try:
        # 1. 确定日期
        if args.date:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        else:
            target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

        today = datetime.now(timezone.utc).date()
        day_start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)

        # 2. 查目标日期发布的视频，取每条 video_id 的最新快照
        # ponytail: O(n) 内存去重，20-30 个账号日更量级够用
        all_snaps = (
            session.query(VideoSnapshot)
            .filter(
                VideoSnapshot.published_at >= day_start,
                VideoSnapshot.published_at < day_end,
            )
            .order_by(VideoSnapshot.fetched_at.desc())
            .all()
        )
        seen: set[str] = set()
        latest_snaps: list[VideoSnapshot] = []
        for s in all_snaps:
            if s.video_id not in seen:
                seen.add(s.video_id)
                latest_snaps.append(s)

        if not latest_snaps:
            logger.info("📭 %s 无发布内容", target_date)
            return

        # 3. 获取账号信息（按 username 匹配）
        accounts = {a.username: a for a in session.query(TrackedAccount).all()}

        # 4. 涨粉数: 每个账号取最新两次快照 → 今天 - 昨天
        all_fs = (
            session.query(AccountSnapshot)
            .order_by(AccountSnapshot.account_id, AccountSnapshot.fetched_at.desc())
            .all()
        )
        today_fc: dict[int, int] = {}
        prev_fc: dict[int, int] = {}
        for s in all_fs:
            if s.account_id not in today_fc:
                today_fc[s.account_id] = s.follower_count
            elif s.account_id not in prev_fc and s.fetched_at.date() < today:
                prev_fc[s.account_id] = s.follower_count

        # 5. 提取 相关剧集
        def extract_drama_tag(title: str) -> str:
            """从标题提取 #tag 作为剧集名。"""
            m = re.findall(r"#([\w一-鿿\-]+)", title)
            if m:
                return m[0]
            return "-"

        # 6. 构建报表行 — 列顺序对齐(新)社媒运营情况表格:
        #    发布时间 | 视频方向 | 相关剧集 | 视频内容 | 浏览量 | 点赞 | 点赞率 | 粉丝数 | 涨粉
        rows = []
        for snap in latest_snaps:
            username = snap.username or ""
            acct = accounts.get(username)
            acct_id = acct.id if acct else None
            followers = acct.follower_count if acct else None
            growth = None
            if acct_id and acct_id in today_fc and acct_id in prev_fc:
                growth = today_fc[acct_id] - prev_fc[acct_id]

            likes = snap.likes or 0
            views = snap.views or 0
            like_rate = f"{likes / views * 100:.1f}%" if views > 0 else "0.0%"

            rows.append({
                "published_at": snap.published_at,
                "direction": "-",
                "drama": extract_drama_tag(snap.title or ""),
                "content": (snap.title or "")[:60],
                "views": views,
                "likes": likes,
                "like_rate": like_rate,
                "followers": followers,
                "growth": growth,
                "username": username,
                "platform": snap.platform,
            })

        # 按账号+发布时间排序
        rows.sort(key=lambda r: (r["username"], r["published_at"] or datetime.min.replace(tzinfo=timezone.utc)))

        # 7. 输出
        csv_fields = [
            "published_at", "direction", "drama", "content",
            "views", "likes", "like_rate", "followers", "growth",
            "username", "platform",
        ]
        if args.format == "csv":
            import io
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=csv_fields)
            w.writeheader()
            for r in rows:
                r_copy = dict(r)
                r_copy["published_at"] = r["published_at"].strftime("%Y-%m-%d %H:%M") if r["published_at"] else "-"
                r_copy["growth"] = r["growth"] if r["growth"] is not None else ""
                r_copy["followers"] = r["followers"] if r["followers"] is not None else ""
                w.writerow(r_copy)
            print(buf.getvalue())
        else:
            # 表格 — 按账号分组
            print(f"\n📊 每日运营报表 — {target_date}")
            print(f"   账号数: {len(accounts)} | 昨日发布: {len(rows)} 条\n")
            header = (
                f"  {'发布时间':>16}  {'视频方向':>8}  {'相关剧集':>14}  "
                f"{'浏览量':>10}  {'点赞':>8}  {'点赞率':>7}  "
                f"{'粉丝数':>10}  {'涨粉':>8}  {'账号':>16}  视频内容"
            )
            print(header)
            print(f"  {'-' * (len(header) - 2)}")
            for r in rows:
                pt = r["published_at"].strftime("%m-%d %H:%M") if r["published_at"] else "-"
                gr = f"+{r['growth']:,}" if r["growth"] and r["growth"] > 0 else str(r["growth"]) if r["growth"] is not None else "-"
                fc = f"{r['followers']:,}" if r["followers"] is not None else "-"
                print(
                    f"  {pt:>16}  {r['direction']:>8}  {r['drama']:>14}  "
                    f"{r['views']:>10,}  {r['likes']:>8,}  "
                    f"{r['like_rate']:>7}  {fc:>10}  {gr:>8}  "
                    f"{r['username']:>16}  {r['content']}"
                )

            # 汇总行
            total_views = sum(r["views"] for r in rows)
            total_likes = sum(r["likes"] for r in rows)
            avg_rate = f"{total_likes / total_views * 100:.1f}%" if total_views > 0 else "0.0%"
            print(f"  {'-' * (len(header) - 2)}")
            print(
                f"  {'合计':>16}  {'':>8}  {'':>14}  "
                f"{total_views:>10,}  {total_likes:>8,}  "
                f"{avg_rate:>7}"
            )
            print()
    finally:
        session.close()


def _trending_report(args):
    """推流报告 — 每个账号今日推流 top N 视频。

    推流数 = 目标日期最新 views - 前一天最新 views
    """
    session = get_session()
    try:
        # 1. 确定日期
        if args.date:
            target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
        else:
            target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()

        prev_date = target_date - timedelta(days=1)

        # 日期范围
        target_start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
        target_end = target_start + timedelta(days=1)
        prev_start = datetime(prev_date.year, prev_date.month, prev_date.day, tzinfo=timezone.utc)
        prev_end = prev_start + timedelta(days=1)

        # 2. 获取所有活跃账号
        accounts = session.query(TrackedAccount).filter_by(active=True).all()
        if not accounts:
            logger.info("📭 无活跃账号")
            return

        # 3. 对每个账号，计算其视频的推流数
        results = []  # [(account, [(video_id, title, trending_count, today_views, prev_views), ...])]

        for acct in accounts:
            # 找该账号的所有视频
            videos = (
                session.query(VideoSnapshot.video_id, VideoSnapshot.title)
                .filter(VideoSnapshot.username == acct.username)
                .distinct()
                .all()
            )

            video_trending = []
            for vid, title in videos:
                # 目标日期的最新快照
                today_snap = (
                    session.query(VideoSnapshot)
                    .filter(
                        VideoSnapshot.video_id == vid,
                        VideoSnapshot.fetched_at >= target_start,
                        VideoSnapshot.fetched_at < target_end,
                    )
                    .order_by(VideoSnapshot.fetched_at.desc())
                    .first()
                )
                # 前一天的最新快照
                prev_snap = (
                    session.query(VideoSnapshot)
                    .filter(
                        VideoSnapshot.video_id == vid,
                        VideoSnapshot.fetched_at >= prev_start,
                        VideoSnapshot.fetched_at < prev_end,
                    )
                    .order_by(VideoSnapshot.fetched_at.desc())
                    .first()
                )

                if today_snap and prev_snap:
                    trending = (today_snap.views or 0) - (prev_snap.views or 0)
                    video_trending.append((vid, title or "", trending, today_snap.views or 0, prev_snap.views or 0))

            # 按推流数排序，取 top N
            video_trending.sort(key=lambda x: -x[2])
            top_n = video_trending[:args.top]

            if top_n:
                results.append((acct, top_n))

        if not results:
            logger.info("📭 %s 无推流数据（需要至少两天的采集数据）", target_date)
            return

        # 4. 输出
        if args.format == "csv":
            import io
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["username", "platform", "video_id", "title", "trending", "today_views", "prev_views"])
            for acct, top_n in results:
                for vid, title, trending, today_v, prev_v in top_n:
                    w.writerow([acct.username, acct.platform, vid, title[:50], trending, today_v, prev_v])
            print(buf.getvalue())
        else:
            # 表格输出
            print(f"\n📈 推流报告 — {target_date}\n")
            for acct, top_n in results:
                print(f"  账号: {acct.username} ({acct.platform})")
                for i, (vid, title, trending, today_v, prev_v) in enumerate(top_n, 1):
                    sign = "+" if trending > 0 else ""
                    title_short = title[:40] if title else vid
                    print(f"    #{i}: {title_short:<40} 推流: {sign}{trending:,}  (今日 {today_v:,} - 昨日 {prev_v:,})")
                print()
    finally:
        session.close()


if __name__ == "__main__":
    main()
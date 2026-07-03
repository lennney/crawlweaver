"""
飞书集成调试脚本 — 自己发消息测试，不用麻烦用户。

用法:
    python debug_feishu.py check           # 全面检查
    python debug_feishu.py webhook         # 测试 webhook 端点
    python debug_feishu.py info            # 查 bot 信息
    python debug_feishu.py send "hello"    # 发消息到群/用户
"""
import asyncio
import json
import os
import sys

import httpx

# 从 systemd 环境变量读取（或 fallback）
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "cli_aaca1bb924f85bdb")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
WEBHOOK_URL = "https://crawl.take-a-deep-breath0.com/feishu/webhook"
CRAWLWEAVER_API = "http://localhost:8090"


async def get_token() -> str:
    async with httpx.AsyncClient() as cli:
        r = await cli.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
            timeout=10,
        )
        d = r.json()
        if d.get("code") != 0:
            raise RuntimeError(f"token 获取失败: {d}")
        print(f"[OK] tenant_access_token 获取成功")
        return d["tenant_access_token"]


async def check_bot_info():
    """查机器人信息 — 确认 app 是否已发布/激活"""
    token = await get_token()
    async with httpx.AsyncClient() as cli:
        r = await cli.get(
            "https://open.feishu.cn/open-apis/bot/v3/info",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        d = r.json()
        print(f"[BOT INFO] HTTP {r.status_code}")
        print(json.dumps(d, indent=2, ensure_ascii=False)[:1000])


async def test_webhook():
    """直接调 webhook — 验证路由+SDK 是否正常"""
    async with httpx.AsyncClient() as cli:
        # 1. url_verification
        r = await cli.post(WEBHOOK_URL, json={
            "type": "url_verification", "challenge": "debug123"
        }, timeout=10)
        print(f"[WEBHOOK url_verification] HTTP {r.status_code}")
        print(f"  Body: {r.text[:200]}")

        # 2. 模拟真实消息事件（含正确 token）
        r2 = await cli.post(WEBHOOK_URL, json={
            "schema": "2.0",
            "header": {
                "event_id": "test_001",
                "event_type": "im.message.receive_v1",
                "token": "RNT7lUxT7YEefKmhTwQ7cdEJW0CmhUfm",
            },
            "event": {
                "message": {
                    "chat_id": "oc_test123",
                    "message_id": "om_test123",
                    "message_type": "text",
                    "content": json.dumps({"text": "https://httpbin.org/"}),
                }
            },
        }, timeout=10)
        print(f"[WEBHOOK fake message] HTTP {r2.status_code}")
        print(f"  Body: {r2.text[:300]}")


async def check_health():
    """检查 CrawlWeaver 和隧道"""
    async with httpx.AsyncClient() as cli:
        # 本地
        r = await cli.get(f"{CRAWLWEAVER_API}/api/health", timeout=5)
        print(f"[CRAWLWEAVER local] HTTP {r.status_code} — {r.text}")

        # 公网隧道
        r2 = await cli.get(f"https://crawl.take-a-deep-breath0.com/api/health", timeout=10)
        print(f"[TUNNEL public] HTTP {r2.status_code} — {r2.text}")


async def check_event_permissions(token: str):
    """查 app 权限列表 — 确认 im:message 权限已开"""
    async with httpx.AsyncClient() as cli:
        r = await cli.get(
            "https://open.feishu.cn/open-apis/application/v6/applications",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        d = r.json()
        print(f"[APP INFO] HTTP {r.status_code}")
        print(json.dumps(d, indent=2, ensure_ascii=False)[:500])


async def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"

    print("=" * 55)
    print(f"  飞书集成调试 — 命令: {cmd}")
    print("=" * 55)

    if cmd == "check":
        await check_health()
        print()
        await test_webhook()
        print()
        await check_bot_info()

    elif cmd == "webhook":
        await test_webhook()

    elif cmd == "info":
        await check_bot_info()

    else:
        print(f"未知命令: {cmd}")
        print("可用: check, webhook, info")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

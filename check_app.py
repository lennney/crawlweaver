"""快速诊断飞书集成"""

import asyncio
import json

import httpx

APP_ID = "' + config['FEISHU_APP_ID'] + '"
APP_SECRET = "' + config['FEISHU_APP_SECRET'] + '"


async def main():
    async with httpx.AsyncClient() as cli:
        r = await cli.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": APP_ID, "app_secret": APP_SECRET},
            timeout=10,
        )
        d = r.json()
        assert d.get("code") == 0, f"Token fail: {d}"
        token = d["tenant_access_token"]
        print("1. Token OK")

        r = await cli.get(
            "https://open.feishu.cn/open-apis/bot/v3/info",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        bot = r.json()["bot"]
        print(f"2. Bot: {bot['app_name']} status={bot['activate_status']}")

        r = await cli.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            params={"receive_id_type": "open_id"},
            headers={"Authorization": f"Bearer {token}"},
            json={
                "receive_id": bot["open_id"],
                "msg_type": "text",
                "content": json.dumps({"text": "from check"}),
            },
            timeout=10,
        )
        d = r.json()
        print(f"3. Msg: code={d.get('code')} msg={d.get('msg')}")

        r = await cli.post(
            "https://crawl.take-a-deep-breath0.com/feishu/webhook",
            json={"type": "url_verification", "challenge": "x"},
            timeout=10,
        )
        print(f"4. Webhook: HTTP {r.status_code}")


asyncio.run(main())

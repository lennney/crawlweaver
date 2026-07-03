"""飞书 Bot 消息处理 — 接收消息 → 调 CrawlWeaver API → 回复卡片。

可以通过两种方式接入：
1. 作为 CrawlWeaver 的 FastAPI webhook 路由（直接注册飞书事件）
2. 作为独立函数被 Hermes agent 调用

环境变量:
    FEISHU_APP_ID: 飞书应用 App ID
    FEISHU_APP_SECRET: 飞书应用 App Secret
    CRAWLWEAVER_API: CrawlWeaver API 地址（默认 http://localhost:8090）
"""

import asyncio
import json
import logging
import os
import time
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, Response

from .url_parser import parse_url, URLInfo
from .cards import confirm_card, progress_card, result_card, error_card, timeout_card

logger = logging.getLogger("crawler.bot")
# 确保日志能输出到 systemd journal（uvicorn 默认只显示访问日志）
if not logger.handlers:
    logger.addHandler(logging.StreamHandler())
    logger.setLevel(logging.INFO)
router = APIRouter(prefix="/feishu", tags=["feishu"])

CRAWLWEAVER_API = os.getenv("CRAWLWEAVER_API", "http://localhost:8090")

# --- 飞书客户端（最小化，只用到卡片发送） ---

class FeishuClient:
    """极简飞书客户端 — 只做 token 获取 + 回复卡片."""

    def __init__(self):
        self.app_id = os.getenv("FEISHU_APP_ID", "")
        self.app_secret = os.getenv("FEISHU_APP_SECRET", "")
        self._token: Optional[str] = None
        self._token_expires_at: float = 0

    async def _get_token(self) -> str:
        """获取 tenant_access_token（自动缓存）."""
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={
                    "app_id": self.app_id,
                    "app_secret": self.app_secret,
                },
                timeout=10,
            )
            data = resp.json()
            if data.get("code") != 0:
                raise RuntimeError(f"飞书 token 获取失败: {data}")
            self._token = data["tenant_access_token"]
            self._token_expires_at = time.time() + data.get("expire", 7200)
            logger.info("飞书 token 已刷新")
            return self._token

    async def reply_card(self, message_id: str, card: dict):
        """回复交互卡片."""
        token = await self._get_token()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://open.feishu.cn/open-apis/im/v1/messages/"
                f"{message_id}/reply",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "content": json.dumps(card),
                    "msg_type": "interactive",
                },
                timeout=10,
            )
            data = resp.json()
            if data.get("code") != 0:
                logger.error(f"飞书卡片发送失败: {data}")
                raise RuntimeError(f"卡片发送失败: {data.get('msg', '')}")
            logger.info("飞书卡片已发送")

    async def send_card_to_chat(self, chat_id: str, card: dict):
        """发送卡片到指定群聊."""
        token = await self._get_token()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://open.feishu.cn/open-apis/im/v1/messages",
                params={"receive_id_type": "chat_id"},
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "receive_id": chat_id,
                    "content": json.dumps(card),
                    "msg_type": "interactive",
                },
                timeout=10,
            )
            data = resp.json()
            if data.get("code") != 0:
                logger.error(f"飞书群发失败: {data}")
                raise RuntimeError(f"群发失败: {data.get('msg', '')}")
            return data.get("data", {}).get("message_id", "")

    async def update_card(self, message_id: str, card: dict):
        """更新已发送的卡片（用于进度更新）."""
        token = await self._get_token()
        async with httpx.AsyncClient() as client:
            resp = await client.patch(
                f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "content": json.dumps(card),
                },
                timeout=10,
            )
            data = resp.json()
            if data.get("code") != 0:
                logger.error(f"飞书卡片更新失败: {data}")


_feishu: Optional[FeishuClient] = None


def get_feishu() -> FeishuClient:
    global _feishu
    if _feishu is None:
        _feishu = FeishuClient()
    return _feishu


# --- URL 提取 ---

def extract_urls(text: str) -> list[str]:
    """从文本中提取所有 URL."""
    import re
    urls = re.findall(r"https?://[^\s<>\"']+", text)
    return [u.rstrip(".,;:!?") for u in urls]


# --- 核心：触发爬取流程 ---

async def trigger_crawl(
    url: str,
    chat_id: str = "",
    message_id: str = "",
    reply_to: str = "",
) -> dict:
    """完整爬取流程：解析 URL → 提交任务 → 进度卡片 → 结果卡片。"""
    from .url_parser import parse_url
    from .cards import progress_card, result_card, error_card, timeout_card

    feishu = get_feishu()
    target = reply_to or message_id

    # 1. 解析 URL
    info = parse_url(url)

    # 2. 提交爬取任务
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{CRAWLWEAVER_API}/api/jobs",
            json={
                "url": url,
                "source": info.source,
                "keyword": info.keyword,
                "content_type": info.content_type,
            },
            timeout=10,
        )
        job_data = resp.json()
        job_id = job_data.get("job_id", "")

    if not job_id:
        card = error_card(url, "任务提交失败")
        try:
            if target:
                await feishu.reply_card(target, card)
            elif chat_id:
                await feishu.send_card_to_chat(chat_id, card)
        except Exception:
            pass
        return {"status": "failed"}

    # 3. 发进度卡片
    card = progress_card(url, "extract", 0)
    try:
        if target:
            await feishu.reply_card(target, card)
        elif chat_id:
            await feishu.send_card_to_chat(chat_id, card)
    except Exception as e:
        logger.warning(f"进度卡片发送失败: {e}")

    # 4. 轮询进度
    steps_order = ["extract", "rewrite", "seo", "render", "verify"]
    start = time.time()
    last_progress = -1

    while time.time() - start < 300:
        await asyncio.sleep(3)

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{CRAWLWEAVER_API}/api/jobs/{job_id}",
                    timeout=5,
                )
                if resp.status_code == 404:
                    continue
                job = resp.json()
        except Exception:
            continue

        status = job.get("status", "pending")
        result = job.get("result", {})
        step = result.get("step", "extract") if result else "extract"
        pct = int((steps_order.index(step) + 1) / len(steps_order) * 100) if step in steps_order else 50

        if status == "completed":
            score = result.get("score", 0) if result else 0
            word_count = result.get("word_count", 0) if result else 0
            title = result.get("title", url[:60]) if result else url[:60]
            result_url = result.get("html_path", "") if result else ""
            full_url = f"{CRAWLWEAVER_API}/api/articles/{result_url}" if result_url else ""

            card = result_card(url, title, word_count, score, full_url)
            try:
                if target:
                    await feishu.reply_card(target, card)
                elif chat_id:
                    await feishu.send_card_to_chat(chat_id, card)
            except Exception as e:
                logger.warning(f"结果卡片发送失败: {e}")
            return {"status": "completed", "job_id": job_id}

        if status == "failed":
            card = error_card(url, job.get("error", "未知错误"))
            try:
                if target:
                    await feishu.reply_card(target, card)
                elif chat_id:
                    await feishu.send_card_to_chat(chat_id, card)
            except Exception:
                pass
            return {"status": "failed", "job_id": job_id}

        # 更新进度
        if pct > last_progress:
            last_progress = pct

    # 超时
    card = timeout_card(url, job_id)
    try:
        if target:
            await feishu.reply_card(target, card)
        elif chat_id:
            await feishu.send_card_to_chat(chat_id, card)
    except Exception:
        pass
    return {"status": "timeout", "job_id": job_id}


# --- 便捷函数（供 Hermes agent 直接调用） ---

async def handle_message(text: str, chat_id: str = "", message_id: str = "") -> list[dict]:
    """处理飞书消息 — 提取 URL → 触发爬取 → 返回卡片。

    供 Hermes agent 直接调用。

    Returns:
        [{"status": "completed", ...}, ...] — 每个 URL 一个结果
    """
    urls = extract_urls(text)
    if not urls:
        return []

    results = []
    for url in urls:
        try:
            result = await trigger_crawl(url, chat_id=chat_id, message_id=message_id)
            results.append(result)
        except Exception as e:
            logger.error(f"爬取失败: {url} — {e}")
            results.append({"status": "failed", "error": str(e)})

    return results


# --- 飞书 SDK 事件处理器（自动处理验签/解密/url_verification） ---

_event_handler = None


def _get_event_handler():
    global _event_handler
    if _event_handler is not None:
        return _event_handler

    from lark_oapi.event.dispatcher_handler import EventDispatcherHandler

    encrypt_key = os.getenv("FEISHU_ENCRYPT_KEY", "")
    verification_token = os.getenv("FEISHU_VERIFICATION_TOKEN", "")

    def on_message(data):
        """收到消息事件 — 异步处理，不阻塞 webhook 响应。"""
        logger.info(f"on_message 被调用, event={data.event}")
        if not data.event or not data.event.message:
            logger.warning(f"event 或 message 为空: event={data.event}")
            return
        msg_type = data.event.message.message_type or ""
        chat_id = data.event.message.chat_id or ""
        message_id = data.event.message.message_id or ""
        content_raw = data.event.message.content or ""
        logger.info(f"消息详情: type={msg_type} chat={chat_id} content={content_raw[:200]}")

        text_content = ""
        if msg_type == "text":
            try:
                body = json.loads(content_raw)
                text_content = body.get("text", "")
            except Exception:
                pass

        if text_content and chat_id:
            logger.info(f"收到飞书消息: chat={chat_id}, text={text_content[:60]}")
            asyncio.create_task(handle_message(text_content, chat_id, message_id))

    handler = (
        EventDispatcherHandler.builder(encrypt_key, verification_token)
        .register_p2_im_message_receive_v1(on_message)
        .build()
    )
    _event_handler = handler
    return handler


# --- Webhook 路由 ---

@router.post("/webhook")
async def feishu_webhook(request: Request):
    """飞书事件回调 webhook — 使用 lark-oapi SDK 自动处理。"""
    from lark_oapi.core.model.raw_request import RawRequest
    from lark_oapi.core.model.raw_response import RawResponse

    body = await request.body()
    data = json.loads(body)
    logger.info(f"Webhook event: type={data.get('type','?')} schema={data.get('schema','?')} header_ev={data.get('header',{}).get('event_type','')}")

    raw_req = RawRequest()
    raw_req.body = body
    raw_req.headers = dict(request.headers)
    raw_req.uri = str(request.url)

    handler = _get_event_handler()
    raw_resp: RawResponse = handler.do(raw_req)

    return Response(
        content=raw_resp.content,
        status_code=raw_resp.status_code or 200,
        media_type="application/json",
        headers=raw_resp.headers or {},
    )


def setup_bot_routes(app):
    """注册飞书路由到 FastAPI app."""
    app.include_router(router)

"""Agent 编排路由（含 SSE 流式）"""
import asyncio
import json
import logging
from contextlib import suppress
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..llm_client import LLMClient
from ..schemas.common import ChatRequest, AgentRunRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent"])


def sse_pack(event: str, data) -> str:
    """格式化 SSE 消息"""
    if not isinstance(data, str):
        data = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"


@router.post("/chat")
async def chat_sync(req: ChatRequest):
    """非流式对话（验证 LLMClient 是否通）"""
    client = LLMClient.from_env()
    reply = client.chat(req.prompt, model=req.model, temperature=req.temperature or 0.7)
    last = client.last_usage()
    return {
        "code": 0,
        "msg": "ok",
        "data": {
            "reply": reply,
            "usage": last.__dict__ if last else None,
        },
    }


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """流式对话 - SSE 端点"""

    async def event_gen() -> AsyncGenerator[str, None]:
        client = LLMClient.from_env()
        loop = asyncio.get_event_loop()
        try:
            yield sse_pack("start", {"model": req.model or client.model})

            # 同步生成器丢到线程池，逐个 chunk 取
            stream_iter = client.stream(
                req.prompt, model=req.model, temperature=req.temperature or 0.7
            )
            while True:
                chunk = await loop.run_in_executor(None, lambda: next(stream_iter, None))
                if chunk is None:
                    break
                yield sse_pack("chunk", {"text": chunk})

            last = client.last_usage()
            yield sse_pack("end", {"usage": last.__dict__ if last else {}})
        except Exception as e:
            logger.exception("chat_stream 失败")
            yield sse_pack("error", {"message": str(e)})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/run/stream")
async def agent_run_stream(req: AgentRunRequest):
    """5 子 Agent 真实编排 - SSE 流式返回每步状态 + LLM token"""

    async def event_gen() -> AsyncGenerator[str, None]:
        from ..services.orchestrator import AgentOrchestrator

        client = LLMClient.from_env()
        if req.model:
            client.model = req.model
        orch = AgentOrchestrator(client, data_file=req.data_file)

        # 后台跑编排，主协程消费事件队列
        run_task = asyncio.create_task(orch.run(req.topic))
        try:
            async for event, data in orch.stream_events():
                yield sse_pack(event, data)
        finally:
            if not run_task.done():
                run_task.cancel()
                with suppress(asyncio.CancelledError):
                    await run_task
            else:
                await run_task

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

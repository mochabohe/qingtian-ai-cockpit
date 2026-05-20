"""系统状态路由(P0 演示兜底机制)

提供:
- GET /system/mode  当前是否启用演示兜底模式 + 可用兜底案例清单
- POST /system/mode  运行时切换演示模式(不重启 backend)
- GET /system/llm-model  当前 LLM 模型 profile + 所有可选 profile
- POST /system/llm-model  运行时切换 LLM 模型(不重启 backend)

UI 用途:
- 全局状态栏显示后端服务/数据池/演示模式 3 个 pill
- 演示模式 pill 可点击切换
- 让现场不发生"以为在跑真 LLM 但其实在回放"的认知错位
- 左下角模型切换按钮(不重启 backend 切换 profile)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..core.llm_runtime import (
    current_profile_payload,
    list_profiles,
    set_profile,
)
from ..services.fallback_player import is_offline_mode, set_offline_mode

router = APIRouter(prefix="/system", tags=["system"])


def _build_payload() -> dict:
    from ..core.config import settings
    fallback_dir = Path(settings.report_dir) / "_fallback"
    cases = []
    if fallback_dir.exists():
        for md in sorted(fallback_dir.glob("*.md")):
            stem = md.stem
            if stem.lower().startswith("readme"):
                continue
            cases.append({
                "stem":      stem,
                "has_doc":   (fallback_dir / f"{stem}.json").exists(),
                "has_trace": (fallback_dir / f"{stem}.trace.json").exists(),
            })
    return {
        "offline_mode":   is_offline_mode(),
        "fallback_cases": cases,
    }


@router.get("/mode")
def get_mode():
    return {"code": 0, "msg": "ok", "data": _build_payload()}


class SetModeRequest(BaseModel):
    """运行时切换演示模式。
    - offline_mode=true → 启用演示模式(Agent 走 fallback 缓存)
    - offline_mode=false → 切回真 LLM 模式
    - offline_mode=null → 恢复跟随环境变量
    """
    offline_mode: Optional[bool] = None


@router.post("/mode")
def post_mode(req: SetModeRequest):
    set_offline_mode(req.offline_mode)
    return {"code": 0, "msg": "ok", "data": _build_payload()}


# =============================================================================
# LLM 模型 profile 切换
# =============================================================================

def _build_llm_payload() -> dict:
    return {
        "current": current_profile_payload(),
        "profiles": list_profiles(),
    }


@router.get("/llm-model")
def get_llm_model():
    """获取当前激活的 LLM profile + 所有可切换 profile"""
    return {"code": 0, "msg": "ok", "data": _build_llm_payload()}


class SetLLMModelRequest(BaseModel):
    """切换运行时 LLM profile

    profile_id:
      - 'deepseek' → DeepSeek 官方 /v1/chat/completions
      - 'openai'   → OpenAI 官方 /v1/chat/completions
      - 'custom'   → 跟随 .env 配置
      - null       → 恢复跟随环境变量
    """
    profile_id: Optional[str] = None


@router.post("/llm-model")
def post_llm_model(req: SetLLMModelRequest):
    try:
        set_profile(req.profile_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"code": 0, "msg": "ok", "data": _build_llm_payload()}

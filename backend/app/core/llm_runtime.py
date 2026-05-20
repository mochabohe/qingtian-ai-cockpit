"""LLM 运行时配置 store

支持运行时不重启 backend 切换模型 profile（类似 system/mode 切换演示模式）。

预设 profile（按需扩展）：
  - deepseek    : DeepSeek 官方 /v1/chat/completions

切换流程：
  1. 前端调 POST /system/llm-model {profile: "deepseek"}
  2. 本模块更新 _override
  3. 后续 LLMClient.from_env() 走覆盖值
  4. 已实例化的 default_client 被强制重置（下次 get_default_client 会重建）

并发简化处理：单 worker uvicorn，不加锁。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from typing import Dict, Optional


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


@dataclass
class LLMProfile:
    """单条可切换的模型配置"""
    id: str
    label: str
    description: str
    provider: str
    base_url: str
    api_key: str
    model: str
    api_type: str  # chat_completions | responses | messages


def _build_profiles() -> Dict[str, "LLMProfile"]:
    """每次 list/current 时重新构造，确保 .env 里 key 改了之后能生效"""
    return {
        "deepseek": LLMProfile(
            id="deepseek",
            label="deepseek-chat",
            description="DeepSeek 官方 /v1/chat/completions",
            provider="deepseek",
            base_url="https://api.deepseek.com/v1",
            api_key=_env("LLM_API_KEY"),
            model="deepseek-chat",
            api_type="chat_completions",
        ),
    }


PROFILES: Dict[str, LLMProfile] = _build_profiles()
DEFAULT_PROFILE_ID = "deepseek"

_override: Optional[LLMProfile] = None


def list_profiles() -> list[dict]:
    """供前端列出所有可切换 profile"""
    profiles = _build_profiles()
    PROFILES.update(profiles)
    return [asdict(p) | {"api_key": _mask_key(p.api_key)} for p in profiles.values()]


def _mask_key(key: str) -> str:
    """脱敏：仅露前 6 + 后 4"""
    if not key or len(key) < 12:
        return "****"
    return f"{key[:6]}…{key[-4:]}"


def current_profile() -> LLMProfile:
    """当前激活的 profile（优先 override，其次 env LLM_PROFILE，再次默认）"""
    profiles = _build_profiles()
    PROFILES.update(profiles)
    if _override is not None:
        return profiles.get(_override.id, _override)
    env_id = _env("LLM_PROFILE")
    if env_id and env_id in profiles:
        return profiles[env_id]
    return profiles[DEFAULT_PROFILE_ID]


def current_profile_payload() -> dict:
    """供 /system/llm-model GET 使用，key 脱敏"""
    p = current_profile()
    return asdict(p) | {"api_key": _mask_key(p.api_key)}


def set_profile(profile_id: Optional[str]) -> LLMProfile:
    """切换 profile；传 None 表示恢复跟随环境变量

    返回切换后激活的 profile（脱敏前的真实对象，供 backend 内部使用）
    """
    global _override
    profiles = _build_profiles()
    PROFILES.update(profiles)
    if profile_id is None:
        _override = None
    else:
        if profile_id not in profiles:
            raise ValueError(f"未知的 profile_id: {profile_id!r}, 可选: {list(profiles.keys())}")
        _override = profiles[profile_id]

    # 让模块级 _default_client 失效，下次 get_default_client 会按新 profile 重建
    try:
        from .. import llm_client as _lc
        _lc._default_client = None
    except Exception:
        pass

    return current_profile()

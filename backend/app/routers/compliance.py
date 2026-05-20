"""合规审查路由 - 提供文本扫描与脱敏接口"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ..services import compliance

router = APIRouter(prefix="/compliance", tags=["compliance"])


class ScanRequest(BaseModel):
    text: str
    extra_keywords: Optional[List[str]] = None


class SanitizeRequest(BaseModel):
    text: str
    extra_keywords: Optional[List[str]] = None


@router.post("/scan")
async def scan_text(req: ScanRequest):
    """
    扫描文本,返回完整审计报告:
      - sanitized_text 脱敏后正文
      - findings 命中明细(原文/脱敏后/位置)
      - rule_hit_counts 各规则命中次数
    """
    report = compliance.scan(req.text, extra_keywords=req.extra_keywords)
    return {"code": 0, "msg": "ok", "data": report.to_dict()}


@router.post("/sanitize")
async def sanitize_text(req: SanitizeRequest):
    """快捷接口:只要脱敏后的文本"""
    text = compliance.sanitize(req.text, extra_keywords=req.extra_keywords)
    return {"code": 0, "msg": "ok", "data": {"sanitized_text": text}}


@router.get("/rules")
async def list_rules():
    """列出全部内置规则(给前端展示)"""
    rules = [{"id": rid, "label": label, "pattern": p.pattern} for rid, label, p, _ in compliance.RULES]
    return {
        "code": 0, "msg": "ok",
        "data": {
            "rules": rules,
            "default_keywords": compliance.DEFAULT_SENSITIVE_KEYWORDS,
            "n_rules": len(rules),
        },
    }

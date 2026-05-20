"""飞书群机器人推送(publisher Agent 真实落地)。

设计原则:
- webhook 未配置 → 直接静默跳过(保持原 LLM 模拟语义,演示不翻车)
- 网络/飞书侧任何失败 → 记 error 返回,不让主编排链路挂掉
- 演示场景:演示模式(OFFLINE_MODE)下也跳过,避免离线演示真发出测试消息
"""
import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

# 飞书自定义机器人单条消息最大长度 ~30000 字节, 我们的简报摘要远小于此, 留 4000 字符上限
_FEISHU_TEXT_LIMIT = 4000


def webhook_url() -> str:
    return os.getenv("FEISHU_BOT_WEBHOOK", "").strip()


def is_enabled() -> bool:
    """webhook 已配 + 不在 OFFLINE_MODE 时才真发"""
    if not webhook_url():
        return False
    # 跟 fallback_player.is_offline_mode 等价,避免离线演示真发飞书
    if os.getenv("OFFLINE_MODE", "").lower() in ("1", "true", "yes"):
        return False
    return True


def send_briefing_card(
    title: str,
    summary: str,
    *,
    topic: str = "",
    saved_filename: Optional[str] = None,
) -> Dict[str, Any]:
    """
    把简报推送到飞书群。返回 {"ok": bool, "skipped"?: bool, "error"?: str}。

    - title: 简报标题(显示在卡片头)
    - summary: 简报核心结论摘要(80-200 字, 卡片正文)
    - topic: 原始分析主题(如 "eπ007 月度经营诊断"), 用于卡片副标题
    - saved_filename: 落盘后的简报文件名(用于"查看完整简报"按钮文案)
    """
    if not is_enabled():
        return {"ok": False, "skipped": True}

    summary_clipped = (summary or "").strip()
    if len(summary_clipped) > _FEISHU_TEXT_LIMIT:
        summary_clipped = summary_clipped[:_FEISHU_TEXT_LIMIT] + " …(已截断)"

    # 飞书 interactive 卡片(比 text 消息显示更克制, 演示现场更像企业流程)
    # 关键字"简报"内置, 跟群机器人安全设置里的关键词触发对齐
    card = {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag":     "plain_text",
                    "content": f"📊 {title or '智擎参谋·经营简报'}",
                },
                "template": "turquoise",
            },
            "elements": [
                # 副标题(主题 + 文件名)
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": True,
                            "text": {"tag": "lark_md", "content": f"**主题**\n{topic or '—'}"},
                        },
                        {
                            "is_short": True,
                            "text": {"tag": "lark_md", "content": f"**简报文件**\n{saved_filename or '已存档'}"},
                        },
                    ],
                },
                {"tag": "hr"},
                # 正文摘要
                {
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": summary_clipped or "(暂无摘要)"},
                },
                {"tag": "hr"},
                # 来源标注
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag":     "plain_text",
                            "content": "来自:智擎参谋 · 5 子 Agent 编排链路 · 演示版",
                        },
                    ],
                },
            ],
        },
    }

    try:
        r = httpx.post(webhook_url(), json=card, timeout=8.0)
        if r.status_code != 200:
            logger.warning("feishu webhook HTTP %s: %s", r.status_code, r.text[:200])
            return {"ok": False, "error": f"HTTP {r.status_code}"}
        body = r.json()
        # 飞书成功返回 {"StatusCode": 0, "StatusMessage": "success", ...}
        # (新版本是 {"code": 0, "msg": "success", ...}, 两者都得兜)
        ok = (body.get("StatusCode") == 0) or (body.get("code") == 0)
        if not ok:
            err = body.get("StatusMessage") or body.get("msg") or "unknown error"
            logger.warning("feishu webhook returned non-zero: %s", body)
            return {"ok": False, "error": err}
        return {"ok": True}
    except httpx.HTTPError as e:
        # 演示现场断网 / 代理问题: 静默降级, 不阻塞主链路
        logger.exception("feishu webhook request failed")
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception("feishu webhook unexpected error")
        return {"ok": False, "error": str(e)}

from __future__ import annotations

"""简报管理与导出路由"""
import asyncio
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from ..core.config import settings
from ..llm_client import LLMClient

router = APIRouter(prefix="/report", tags=["report"])
logger = logging.getLogger(__name__)

# 0 = generating, 1 = success, 2 = failed
REPORT_TASKS: Dict[str, dict] = {}


class SaveReportRequest(BaseModel):
    topic: str
    markdown: str
    filename: Optional[str] = None


class SaveRevisionRequest(BaseModel):
    """P1-1 简报最小审阅:把 textarea 编辑后的正文保存为修订版.

    后端纯文件操作,不调 LLM,不重生成。
    """
    original_filename: str
    markdown: str
    note: Optional[str] = None


class GenerateReportRequest(BaseModel):
    topic: str
    data_file: Optional[str] = None
    model: Optional[str] = None


async def _run_report_task(task_id: str, req: GenerateReportRequest):
    """后台运行异步简报任务，复用现有 AgentOrchestrator。"""
    from ..services.orchestrator import AgentOrchestrator

    task = REPORT_TASKS[task_id]
    try:
        client = LLMClient.from_env()
        if req.model:
            client.model = req.model

        orch = AgentOrchestrator(client, data_file=req.data_file)
        run_task = asyncio.create_task(orch.run(req.topic))

        async for event, data in orch.stream_events():
            task["updated_at"] = datetime.now().timestamp()
            if event == "start":
                task["progress"] = {
                    "event": "start",
                    "topic": data.get("topic"),
                    "total_steps": data.get("total_steps"),
                }
            elif event == "data_loaded":
                task["data_loaded"] = data
                task["progress"] = {"event": "data_loaded", **data}
            elif event == "step_start":
                task["current_step"] = {
                    "index": data.get("index"),
                    "name": data.get("name"),
                    "title": data.get("title"),
                }
                task["progress"] = {"event": "step_start", **task["current_step"]}
            elif event == "step_done":
                task["last_step"] = {
                    "index": data.get("index"),
                    "name": data.get("name"),
                    "output_preview": (data.get("output") or "")[:300],
                }
                task["progress"] = {"event": "step_done", **task["last_step"]}
            elif event == "end":
                task["status"] = 1
                task["report"] = data.get("report", "")
                task["saved_as"] = data.get("saved_as")
                task["final"] = data.get("final")
                task["progress"] = {"event": "end", "saved_as": task["saved_as"]}
            elif event == "error":
                task["status"] = 2
                task["error"] = data.get("message", "未知错误")
                task["progress"] = {"event": "error", "message": task["error"]}

        await run_task

        if task["status"] == 0:
            task["status"] = 1
            task["progress"] = {"event": "end", "saved_as": task.get("saved_as")}
    except Exception as e:
        logger.exception("异步简报任务失败: %s", task_id)
        task["status"] = 2
        task["error"] = str(e)
        task["updated_at"] = datetime.now().timestamp()
        task["progress"] = {"event": "error", "message": str(e)}


@router.post("/generate")
async def generate_report(req: GenerateReportRequest):
    """发起异步简报生成任务。"""
    task_id = f"report_{uuid.uuid4().hex[:12]}"
    now = datetime.now().timestamp()
    REPORT_TASKS[task_id] = {
        "id": task_id,
        "status": 0,
        "topic": req.topic,
        "data_file": req.data_file,
        "model": req.model,
        "report": "",
        "saved_as": None,
        "error": None,
        "final": None,
        "progress": {"event": "queued"},
        "current_step": None,
        "last_step": None,
        "data_loaded": None,
        "created_at": now,
        "updated_at": now,
    }
    asyncio.create_task(_run_report_task(task_id, req))
    return {"code": 0, "msg": "ok", "data": {"id": task_id, "status": 0}}


@router.get("/task/{task_id}")
async def get_report_task(task_id: str):
    """获取异步简报任务详情。"""
    task = REPORT_TASKS.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return {"code": 0, "msg": "ok", "data": task}


@router.post("/save")
async def save_report(req: SaveReportRequest):
    """保存简报为 .md 文件"""
    report_dir = Path(settings.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    if req.filename:
        filename = req.filename
        if not filename.endswith('.md'):
            filename += '.md'
    else:
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_topic = "".join(c for c in req.topic if c.isalnum() or c in "_-").strip()[:30]
        filename = f"{ts}_{safe_topic or 'report'}.md"

    filepath = report_dir / filename
    filepath.write_text(req.markdown, encoding='utf-8')

    return {
        "code": 0, "msg": "ok",
        "data": {"filename": filename, "size": len(req.markdown.encode('utf-8'))},
    }


@router.post("/save-revision")
async def save_revision(req: SaveRevisionRequest):
    """P1-1 简报最小审阅:保存当前 markdown 为新的修订版文件。

    - 不覆盖原简报、不调 LLM
    - 复制原 .json / .trace.json 到新 stem(便于卡片视图与全链路追溯仍可用)
    - 新文件名: <原 stem>_revised_<YYYYmmdd_HHMMSS>.md(不以 _ 开头,确保进列表)
    """
    import shutil

    report_dir = Path(settings.report_dir)
    if not report_dir.exists():
        raise HTTPException(404, "简报目录不存在")

    src_md = report_dir / req.original_filename
    if not src_md.exists() or src_md.suffix.lower() != ".md":
        raise HTTPException(404, "原简报不存在或非 .md 文件")

    # 防越权:确认目标路径仍在 report_dir 下
    try:
        src_md.resolve().relative_to(report_dir.resolve())
    except ValueError:
        raise HTTPException(400, "非法的原文件名")

    src_stem = src_md.with_suffix("").stem
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_stem = f"{src_stem}_revised_{ts}"
    new_md_path = report_dir / f"{new_stem}.md"

    # 写新 markdown
    new_md_path.write_text(req.markdown, encoding="utf-8")

    # 复制配套衍生产物(若存在),保留卡片视图与链路追溯
    copied = []
    src_json = src_md.with_suffix(".json")
    if src_json.exists():
        dst_json = report_dir / f"{new_stem}.json"
        shutil.copyfile(src_json, dst_json)
        copied.append(dst_json.name)

    src_trace = src_md.parent / f"{src_stem}.trace.json"
    if src_trace.exists():
        dst_trace = report_dir / f"{new_stem}.trace.json"
        shutil.copyfile(src_trace, dst_trace)
        copied.append(dst_trace.name)

    logger.info(
        "[save-revision] %s -> %s (note=%s, copied=%s)",
        req.original_filename, new_md_path.name, req.note, copied,
    )

    return {
        "code": 0, "msg": "ok",
        "data": {
            "filename": new_md_path.name,
            "path": str(new_md_path),
            "size": len(req.markdown.encode("utf-8")),
            "copied_siblings": copied,
            "note": req.note or "",
        },
    }


@router.get("/list")
async def list_reports():
    """列出所有简报；每项标注是否存在同 stem 的结构化 *.json。"""
    report_dir = Path(settings.report_dir)
    if not report_dir.exists():
        return {"code": 0, "msg": "ok", "data": []}

    items = []
    for p in sorted(report_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        # 过滤内部产物:_latest_e2e.md 等以 _ 开头的脚本副本不进列表
        if p.is_file() and p.suffix.lower() == '.md' and not p.name.startswith('_'):
            stem = p.with_suffix('')
            json_sibling = stem.with_suffix('.json')
            trace_sibling = stem.parent / f"{stem.stem}.trace.json"
            items.append({
                "name": p.name,
                "size": p.stat().st_size,
                "modified": p.stat().st_mtime,
                "has_doc": json_sibling.exists(),
                "has_trace": trace_sibling.exists(),
            })
    return {"code": 0, "msg": "ok", "data": items}


@router.get("/{filename}/markdown")
async def get_markdown(filename: str):
    """读取 markdown 原文"""
    filepath = Path(settings.report_dir) / filename
    if not filepath.exists():
        raise HTTPException(404, "简报不存在")
    return {"code": 0, "msg": "ok", "data": {"markdown": filepath.read_text(encoding='utf-8')}}


@router.get("/compliance-summary")
async def compliance_summary(limit: int = 20):
    """聚合最近 N 份结构化简报的合规统计,供首页 KPI 卡展示真实指标。"""
    import json as _json
    report_dir = Path(settings.report_dir)
    if not report_dir.exists():
        return {"code": 0, "msg": "ok",
                "data": {"masked": 0, "total": 0, "rate": 0.0,
                         "doc_count": 0, "with_compliance": 0}}

    files = sorted(report_dir.glob("*.json"),
                   key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    masked_sum = total_sum = with_compliance = 0
    for p in files:
        try:
            data = _json.loads(p.read_text(encoding="utf-8"))
            comp = data.get("compliance") or {}
            m = int(comp.get("masked_field_count") or 0)
            t = int(comp.get("total_field_count") or 0)
            masked_sum += m
            total_sum += t
            if t > 0 or m > 0:
                with_compliance += 1
        except Exception:
            continue

    rate = round(masked_sum / total_sum, 4) if total_sum else 0.0
    return {"code": 0, "msg": "ok", "data": {
        "masked": masked_sum,
        "total": total_sum,
        "rate": rate,
        "doc_count": len(files),
        "with_compliance": with_compliance,
    }}


@router.get("/{filename}/doc")
async def get_briefing_doc(filename: str):
    """读取结构化 BriefingDoc JSON;filename 传 *.md 名,内部找同 stem 的 *.json。"""
    md_path = Path(settings.report_dir) / filename
    json_path = md_path.with_suffix('.json')
    if not json_path.exists():
        raise HTTPException(404, "结构化简报不存在(可能是历史 markdown 简报)")
    import json as _json
    try:
        doc = _json.loads(json_path.read_text(encoding='utf-8'))
    except _json.JSONDecodeError as e:
        raise HTTPException(500, f"BriefingDoc JSON 损坏: {e}")
    return {"code": 0, "msg": "ok", "data": doc}


@router.get("/{filename}/trace")
async def get_report_trace(filename: str):
    """读取 5 Agent 全链路追溯 JSON;filename 传 *.md 名,内部找同 stem 的 *.trace.json。"""
    md_path = Path(settings.report_dir) / filename
    stem = md_path.with_suffix('').stem
    trace_path = md_path.parent / f"{stem}.trace.json"
    if not trace_path.exists():
        raise HTTPException(404, "全链路追溯不存在(历史简报或保存失败)")
    import json as _json
    try:
        trace = _json.loads(trace_path.read_text(encoding='utf-8'))
    except _json.JSONDecodeError as e:
        raise HTTPException(500, f"trace JSON 损坏: {e}")
    return {"code": 0, "msg": "ok", "data": trace}


@router.get("/{filename}/html", response_class=HTMLResponse)
async def export_html(filename: str):
    """导出为可打印 HTML(优先走结构化 BriefingDoc,缺失时降级到 markdown)。"""
    md_path = Path(settings.report_dir) / filename
    json_path = md_path.with_suffix('.json')
    if not md_path.exists() and not json_path.exists():
        raise HTTPException(404, "简报不存在")

    from ..services.report_exporter import md_to_html, doc_to_html
    from ..services.briefing_schema import parse_briefing
    import json as _json

    if json_path.exists():
        try:
            payload = _json.loads(json_path.read_text(encoding='utf-8'))
            doc = parse_briefing(payload)
            return HTMLResponse(content=doc_to_html(doc))
        except Exception:
            logger.exception("doc_to_html 失败,降级到 md_to_html")
    md = md_path.read_text(encoding='utf-8') if md_path.exists() else ""
    return HTMLResponse(content=md_to_html(md, title=md_path.stem))


@router.get("/{filename}/pptx")
async def export_pptx(filename: str):
    """导出为 PPTX 下载(优先走结构化 BriefingDoc,缺失时降级到 markdown)。"""
    md_path = Path(settings.report_dir) / filename
    json_path = md_path.with_suffix('.json')
    if not md_path.exists() and not json_path.exists():
        raise HTTPException(404, "简报不存在")

    from ..services.report_exporter import md_to_pptx, doc_to_pptx
    from ..services.briefing_schema import parse_briefing
    import json as _json

    out_path = Path(settings.report_dir) / (md_path.stem + ".pptx")
    if json_path.exists():
        try:
            payload = _json.loads(json_path.read_text(encoding='utf-8'))
            doc = parse_briefing(payload)
            doc_to_pptx(doc, out_path)
            return FileResponse(
                out_path,
                media_type='application/vnd.openxmlformats-officedocument.presentationml.presentation',
                filename=out_path.name,
            )
        except Exception:
            logger.exception("doc_to_pptx 失败,降级到 md_to_pptx")
    md = md_path.read_text(encoding='utf-8') if md_path.exists() else ""
    md_to_pptx(md, out_path)
    return FileResponse(
        out_path,
        media_type='application/vnd.openxmlformats-officedocument.presentationml.presentation',
        filename=out_path.name,
    )


@router.get("/{filename}/json")
async def download_briefing_json(filename: str):
    """下载结构化 BriefingDoc 源 JSON 文件。"""
    md_path = Path(settings.report_dir) / filename
    json_path = md_path.with_suffix('.json')
    if not json_path.exists():
        raise HTTPException(404, "结构化简报不存在(可能是历史 markdown 简报)")
    return FileResponse(
        json_path,
        media_type='application/json',
        filename=json_path.name,
    )


@router.delete("/{filename}")
async def delete_report(filename: str):
    """删除简报"""
    filepath = Path(settings.report_dir) / filename
    if not filepath.exists():
        raise HTTPException(404, "简报不存在")
    filepath.unlink()
    # 同 stem 的衍生产物一并清理(.pptx / .json / .trace.json / _doc.html)
    stem = filepath.with_suffix('').stem
    parent = filepath.parent
    for sibling_name in (f"{stem}.pptx", f"{stem}.json", f"{stem}.trace.json", f"{stem}_doc.html"):
        p = parent / sibling_name
        if p.exists():
            p.unlink()
    return {"code": 0, "msg": "ok", "data": None}

"""业务视频自动合成路由"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..core.config import settings
from ..services import video_synth

router = APIRouter(prefix="/video", tags=["video"])
logger = logging.getLogger(__name__)

# 异步任务状态:0 = generating, 1 = success, 2 = failed
# 内存字典 + 每个任务目录下 _task.json 文件双写,backend 重启时自动从磁盘恢复
VIDEO_TASKS: Dict[str, dict] = {}


def _task_meta_path(task_id: str) -> Path:
    """任务元数据文件路径:data/videos/<task_id>/_task.json"""
    return _video_root() / task_id / "_task.json"


def _persist_task(task_id: str) -> None:
    """把当前任务状态写到磁盘(每次状态变更后调用,backend 重启可恢复)"""
    task = VIDEO_TASKS.get(task_id)
    if not task:
        return
    try:
        meta_path = _task_meta_path(task_id)
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(
            json.dumps(task, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("持久化视频任务 %s 失败: %s", task_id, e)


def _restore_video_tasks_from_disk() -> int:
    """backend 启动时扫盘恢复历史任务"""
    root = _video_root()
    if not root.exists():
        return 0
    n = 0
    for d in sorted(root.iterdir()):
        if not d.is_dir() or not d.name.startswith("video_"):
            continue
        meta_path = d / "_task.json"
        if not meta_path.exists():
            continue
        try:
            task = json.loads(meta_path.read_text(encoding="utf-8"))
            VIDEO_TASKS[task["id"]] = task
            n += 1
        except Exception as e:
            logger.warning("恢复视频任务 %s 失败: %s", d.name, e)
    if n > 0:
        logger.info("从磁盘恢复 %d 个历史视频任务", n)
    return n


class GenerateVideoRequest(BaseModel):
    report_filename: str  # 简报 .json 或 .md 文件名(从 report_dir 取)
    do_assemble: bool = True


def _video_root() -> Path:
    """
    所有视频任务的输出根目录(必须返回绝对路径,
    否则 subprocess 调用 ffmpeg 时按 backend 启动 cwd 解析会找不到文件)。
    """
    return (Path(settings.report_dir).parent / "videos").resolve()


def _load_briefing(filename: str) -> dict:
    """从 report_dir 加载简报。优先用 .json,缺失则从 .md 兜底封装。"""
    report_dir = Path(settings.report_dir)
    fp = report_dir / filename

    # 用户可能传 .md 或 .json,统一找 .json
    if fp.suffix.lower() == ".md":
        json_sibling = fp.with_suffix(".json")
        if json_sibling.exists():
            fp = json_sibling

    if not fp.exists():
        raise HTTPException(404, f"简报文件不存在: {filename}")

    if fp.suffix.lower() == ".json":
        return json.loads(fp.read_text(encoding="utf-8"))

    # MD 兜底:抽取摘要/洞察/行动,避免把 Markdown 标题、日期、审计 ID 直接念进视频
    md_text = fp.read_text(encoding="utf-8")
    title = filename.replace(".md", "")
    return video_synth.briefing_from_markdown(title, md_text)


async def _run_video_task(task_id: str, req: GenerateVideoRequest):
    task = VIDEO_TASKS[task_id]
    try:
        briefing = _load_briefing(req.report_filename)
        loop = asyncio.get_event_loop()

        def _do() -> video_synth.VideoArtifacts:
            return video_synth.synth_video(
                briefing,
                out_root=_video_root(),
                task_id=task_id,
                do_assemble=req.do_assemble,
            )

        artifacts = await loop.run_in_executor(None, _do)
        task["status"] = 1
        task["artifacts"] = {
            "workdir":     artifacts.workdir,
            "script_md":   _to_rel(artifacts.script_md),
            "script_json": _to_rel(artifacts.script_json),
            "storyboards": [_to_rel(p) for p in artifacts.storyboards],
            "audios":      [_to_rel(p) for p in artifacts.audios],
            "srt":         _to_rel(artifacts.srt) if artifacts.srt else None,
            "final_mp4":   _to_rel(artifacts.final_mp4) if artifacts.final_mp4 else None,
            "notes":       artifacts.notes,
        }
        task["updated_at"] = datetime.now().timestamp()
    except HTTPException as e:
        task["status"] = 2
        task["error"] = e.detail
        task["updated_at"] = datetime.now().timestamp()
    except Exception as e:
        logger.exception("视频任务失败 %s", task_id)
        task["status"] = 2
        task["error"] = str(e)
        task["updated_at"] = datetime.now().timestamp()
    finally:
        _persist_task(task_id)


def _to_rel(absp: Optional[str]) -> Optional[str]:
    """绝对路径 → 相对 video_root 的相对路径(给前端做下载链接)"""
    if not absp:
        return None
    try:
        rel = Path(absp).resolve().relative_to(_video_root().resolve())
        return rel.as_posix()
    except ValueError:
        return absp


@router.post("/generate")
async def generate_video(req: GenerateVideoRequest):
    # 拍快照:任务创建时的视频后端 + 模型 + 分辨率(用于 UI 列表 tag 与历史可追溯)
    from ..core.config import seedance_settings
    backend_tag = "Seedance" if (seedance_settings.video_backend == "seedance"
                                 and seedance_settings.api_key) else "LocalStub"
    task_id = f"video_{uuid.uuid4().hex[:12]}"
    now = datetime.now().timestamp()
    VIDEO_TASKS[task_id] = {
        "id":              task_id,
        "status":          0,
        "report_filename": req.report_filename,
        "backend":         backend_tag,
        "model":           seedance_settings.model if backend_tag == "Seedance" else "matplotlib",
        "resolution":      seedance_settings.resolution if backend_tag == "Seedance" else "1080p",
        "created_at":      now,
        "updated_at":      now,
        "artifacts":       None,
        "error":           None,
    }
    _persist_task(task_id)  # 任务创建即写盘,backend 重启后能看到 0=生成中 状态
    asyncio.create_task(_run_video_task(task_id, req))
    return {"code": 0, "msg": "ok", "data": {"id": task_id, "status": 0}}


_PLACEHOLDER_REPORT_NAMES = ("历史任务·简报已合并", "历史任务·简报已合并)")


def _lazy_backfill_storyboards(task_id: str) -> bool:
    """历史任务兜底:storyboards 数组为空但磁盘上有 scene_*.mp4 时,
    用 ffmpeg 抽第一帧补齐 storyboard_*.jpg,写回 _task.json。
    """
    task = VIDEO_TASKS.get(task_id)
    if not task or task.get("status") != 1 or not task.get("artifacts"):
        return False
    arts = task["artifacts"]
    if arts.get("storyboards"):
        return False
    workdir = _video_root() / task_id
    if not workdir.exists():
        return False
    scene_mp4s = sorted(workdir.glob("scene_*.mp4"))
    if not scene_mp4s:
        return False

    from ..services.video_synth import extract_first_frame
    new_frames: list[str] = []
    for mp4 in scene_mp4s:
        idx_str = mp4.stem.replace("scene_", "")
        frame_out = workdir / f"storyboard_{idx_str}.jpg"
        if frame_out.exists() and frame_out.stat().st_size > 0:
            new_frames.append(_to_rel(str(frame_out)) or str(frame_out))
            continue
        f = extract_first_frame(mp4, frame_out)
        if f:
            new_frames.append(_to_rel(str(f)) or str(f))
    if not new_frames:
        return False
    arts["storyboards"] = new_frames
    task["artifacts"] = arts
    task["updated_at"] = datetime.now().timestamp()
    _persist_task(task_id)
    logger.info("已为历史任务 %s lazy backfill %d 张分镜帧", task_id, len(new_frames))
    return True


def _lazy_backfill_report_name(task_id: str) -> bool:
    """历史任务兜底 2:report_filename 是占位文案("历史任务·简报已合并"等)时,
    从 script.json 读 title 字段(等于 briefing.cover.headline)替换显示名,
    让历史合成列表里能区分每条视频讲什么。"""
    task = VIDEO_TASKS.get(task_id)
    if not task or not task.get("artifacts"):
        return False
    cur_name = task.get("report_filename", "") or ""
    # 只对占位文案做替换;真实简报文件名(以 .md / .json 结尾)永远不动
    if not any(p in cur_name for p in _PLACEHOLDER_REPORT_NAMES):
        return False
    script_json_rel = task["artifacts"].get("script_json")
    if not script_json_rel:
        return False
    sj_path = _video_root() / script_json_rel
    if not sj_path.exists():
        return False
    try:
        sj = json.loads(sj_path.read_text(encoding="utf-8"))
        title = (sj.get("title") or "").strip()
    except Exception as e:
        logger.warning("读取 %s 失败: %s", sj_path, e)
        return False
    if not title:
        return False
    task["report_filename"] = title
    _persist_task(task_id)
    logger.info("已为历史任务 %s 回填简报名: %s", task_id, title)
    return True


def _compute_progress(task_id: str) -> Optional[dict]:
    """扫工作目录算实时进度,给前端做"已出 N/M 段画面 + 等待时长"展示。

    数据来源:
    - script.json 里 scenes 数组长度 → 总幕数
    - 工作目录里 scene_*.mp4 数量    → 已出画面数
    - 工作目录里 audio_*.mp3 数量   → 已生成 TTS 数
    - final.mp4 / _concat_raw.mp4 是否存在 → 是否进入 ffmpeg 拼接阶段
    - task['created_at'] / 当前时间 → 已等待秒数
    - 已出第一段的耗时 + 剩余幕数 → 预计剩余秒数

    所有判断纯文件 IO,不阻塞 ffmpeg/Seedance 子任务,可以高频轮询。
    """
    task = VIDEO_TASKS.get(task_id)
    if not task:
        return None

    workdir = _video_root() / task_id
    if not workdir.exists():
        return None

    # 1) 总幕数:从 script.json 拿
    script_path = workdir / "script.json"
    total_scenes = 0
    if script_path.exists():
        try:
            sj = json.loads(script_path.read_text(encoding="utf-8"))
            total_scenes = len(sj.get("scenes") or [])
        except Exception:
            total_scenes = 0

    # 2) 实拍画面进度
    scene_mp4s = sorted(workdir.glob("scene_*.mp4"))
    scenes_ready = len(scene_mp4s)

    # 3) TTS 进度
    audio_mp3s = sorted(workdir.glob("audio_*.mp3"))
    audios_ready = len(audio_mp3s)

    # 4) 阶段判定 - 用磁盘标志位反推 backend 跑到哪一步
    final_mp4 = workdir / "final.mp4"
    concat_raw = workdir / "_concat_raw.mp4"
    if final_mp4.exists() and final_mp4.stat().st_size > 0:
        stage = "done"
        stage_label = "合成完成"
    elif concat_raw.exists():
        stage = "burning_subtitles"
        stage_label = "正在烧录字幕"
    elif audios_ready > 0 and scenes_ready >= total_scenes and total_scenes > 0:
        stage = "assembling"
        stage_label = "正在拼接视频"
    elif audios_ready > 0 and scenes_ready < total_scenes:
        # TTS 通常比 Seedance 快得多,实际场景里 audio 都是最后一起出的
        stage = "rendering"
        stage_label = f"正在生成第 {scenes_ready + 1} 段画面"
    elif total_scenes > 0:
        stage = "rendering"
        stage_label = f"正在生成第 {scenes_ready + 1} 段画面" if scenes_ready < total_scenes else "正在生成画面"
    else:
        stage = "preparing"
        stage_label = "正在准备脚本与分镜"

    # 5) 时间统计
    now = datetime.now().timestamp()
    elapsed_s = max(0, int(now - task.get("created_at", now)))

    # 6) 预估剩余:用第一段实际耗时反推平均单段时间
    eta_s: Optional[int] = None
    avg_scene_s: Optional[float] = None
    if scenes_ready >= 1 and total_scenes > 0:
        first_mtime = scene_mp4s[0].stat().st_mtime
        first_scene_cost = max(30.0, first_mtime - task.get("created_at", first_mtime))
        # 用最近一段的耗时(对均值更敏感,Seedance 排队抖动时也准)
        if scenes_ready >= 2:
            last_two_gap = scene_mp4s[-1].stat().st_mtime - scene_mp4s[-2].stat().st_mtime
            avg_scene_s = (first_scene_cost + last_two_gap) / 2
        else:
            avg_scene_s = first_scene_cost
        remaining_scenes = max(0, total_scenes - scenes_ready)
        # Seedance 跑完后还要 TTS(短,~5-10s) + ffmpeg 拼接(10-30s) + 烧字幕(10-30s)
        post_processing_s = 40 if total_scenes > 0 else 0
        eta_s = int(remaining_scenes * avg_scene_s + post_processing_s)
    elif total_scenes > 0:
        # 第一段还没出来 - 用经验值兜底:2.0 单段约 200-300s,1.5 约 100-180s
        model_name = task.get("model", "")
        per_scene = 250 if "2-0" in model_name else 150
        eta_s = total_scenes * per_scene + 40

    return {
        "total_scenes":   total_scenes,
        "scenes_ready":   scenes_ready,
        "audios_ready":   audios_ready,
        "stage":          stage,
        "stage_label":    stage_label,
        "elapsed_s":      elapsed_s,
        "eta_s":          eta_s,
        "avg_scene_s":    int(avg_scene_s) if avg_scene_s else None,
        # 给前端做时间线渲染:每段 mp4 的相对时间
        "scene_timeline": [
            {
                "index":    i + 1,
                "size_kb":  mp4.stat().st_size // 1024,
                "ready_at": int(mp4.stat().st_mtime),
            }
            for i, mp4 in enumerate(scene_mp4s)
        ],
    }


@router.get("/task/{task_id}")
async def get_task(task_id: str):
    task = VIDEO_TASKS.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    # 历史任务无感补齐(都是只跑一次,完成后 _task.json 已写盘):
    # 1) storyboards 分镜画面    2) report_filename 显示名
    _lazy_backfill_storyboards(task_id)
    _lazy_backfill_report_name(task_id)
    # 实时进度(仅生成中状态需要,完成/失败状态不需要扫盘)
    response_task = dict(task)
    if task.get("status") == 0:
        progress = _compute_progress(task_id)
        if progress:
            response_task["progress"] = progress
    return {"code": 0, "msg": "ok", "data": response_task}


@router.get("/list")
async def list_tasks():
    # 列表打开时把所有历史任务的简报名一次性回填(轻操作,只读 script.json title)
    # 抽帧仍然延后到 get_task 按需触发,避免列表加载慢
    for tid in list(VIDEO_TASKS.keys()):
        try:
            _lazy_backfill_report_name(tid)
        except Exception:
            logger.exception("list 阶段回填 %s 失败", tid)
    items = sorted(VIDEO_TASKS.values(), key=lambda t: t["updated_at"], reverse=True)
    return {"code": 0, "msg": "ok", "data": items}


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """删除视频任务:从内存字典移除 + 删除磁盘整个任务目录(含 mp4/音频/分镜)"""
    import shutil
    if task_id not in VIDEO_TASKS:
        # 即使内存里没有,也尝试清磁盘(兼容 backfill 后未恢复成功的情况)
        task_dir = _video_root() / task_id
        if not task_dir.exists():
            raise HTTPException(404, f"任务不存在: {task_id}")
    # 防 path traversal:task_id 必须是 video_ 开头的纯字符串
    if not task_id.startswith("video_") or "/" in task_id or ".." in task_id:
        raise HTTPException(400, f"非法 task_id: {task_id}")

    task_dir = (_video_root() / task_id).resolve()
    root = _video_root().resolve()
    try:
        task_dir.relative_to(root)
    except ValueError:
        raise HTTPException(400, "非法路径")

    VIDEO_TASKS.pop(task_id, None)
    if task_dir.exists():
        try:
            shutil.rmtree(task_dir)
        except Exception as e:
            logger.exception("删除视频任务目录失败 %s", task_id)
            raise HTTPException(500, f"删除目录失败: {e}")
    logger.info("已删除视频任务 %s", task_id)
    return {"code": 0, "msg": "ok", "data": {"id": task_id}}


@router.get("/file/{relpath:path}")
async def get_file(relpath: str):
    """下载 video 产物(分镜图 / mp3 / srt / mp4 / md / json)"""
    target = (_video_root() / relpath).resolve()
    root = _video_root().resolve()
    # 防 path traversal
    try:
        target.relative_to(root)
    except ValueError:
        raise HTTPException(400, "非法路径")
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "文件不存在")
    return FileResponse(target)

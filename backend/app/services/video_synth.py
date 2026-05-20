"""
业务视频自动合成 ─ 完整 pipeline (脚本 → 分镜 → TTS → 字幕 → 拼接)

【设计原则】
- 模块化:每一步独立,缺一步降级而非全失败
- 可插拔画面后端:今天 LocalStubBackend(matplotlib 静态图);
  明天接 Seedance(火山豆包视频)只需新加一个 IVideoBackend 实现

【完整链路】
    Briefing JSON/MD                          ←  data/reports/*.json
        ↓ extract_script()
    VideoScript: [Scene] (开场/数据/痛点/行动 4-5 幕,每幕 prompt + 旁白 + 时长)
        ↓ render_storyboards()                ← matplotlib 占位 (今天)
    storyboard_NN.png × N                     ← Seedance API 输出 mp4 片段 (明天)
        ↓ tts_synth()                         ← edge-tts 中文女声/男声
    audio_NN.mp3 × N
        ↓ build_srt()
    script.srt
        ↓ ffmpeg_assemble()                   ← imageio-ffmpeg 自带二进制
    final.mp4

【画面风格 · 混合】
    开场      → 科技未来(全息屏 / HUD / 蓝色赛博)
    数据段    → 商务写实(展厅 / 大屏 / 数据可视化)
    痛点/口碑 → 商务写实(用户场景 / 4S 店)
    行动建议  → 科技未来(战略沙盘 / 蓝紫色)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

logger = logging.getLogger(__name__)

# imageio-ffmpeg 自带 ffmpeg 二进制
try:
    import imageio_ffmpeg
    FFMPEG_BIN = imageio_ffmpeg.get_ffmpeg_exe()
except Exception as e:
    FFMPEG_BIN = None
    logger.warning("imageio-ffmpeg 不可用,视频合成将降级为仅产出素材: %s", e)


# ============================================================
# 数据契约
# ============================================================

@dataclass
class Scene:
    """单个分镜:对应 Seedance 一次出片(5-10s)"""
    index:        int
    style:        str              # tech_future / business_real
    title:        str              # 分镜标题(供分镜图叠字)
    voiceover:    str              # 旁白文本(TTS 输入)
    prompt:       str              # 画面 prompt(明天给 Seedance)
    duration_s:   float            # 该分镜时长(秒)
    image_path:   Optional[str] = None
    audio_path:   Optional[str] = None
    video_path:   Optional[str] = None  # Seedance 出的 mp4 路径(明天)


@dataclass
class VideoScript:
    title:           str
    total_duration:  float
    scenes:          List[Scene] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title":          self.title,
            "total_duration": self.total_duration,
            "scenes":         [asdict(s) for s in self.scenes],
        }


@dataclass
class VideoArtifacts:
    """合成全过程的产物路径"""
    workdir:        str
    script_md:      str
    script_json:    str
    storyboards:    List[str] = field(default_factory=list)
    audios:         List[str] = field(default_factory=list)
    srt:            Optional[str] = None
    final_mp4:      Optional[str] = None
    notes:          List[str] = field(default_factory=list)


# ============================================================
# 1. 简报 → 脚本切分
# ============================================================

# 风格分配:开场/行动 → tech_future,数据/口碑/痛点 → business_real
_STYLE_FOR_TYPE = {
    "cover":    "tech_future",
    "summary":  "business_real",
    "trend":    "business_real",
    "ranking":  "business_real",
    "distribution": "business_real",
    "alert":    "business_real",
    "actions":  "tech_future",
    "footer":   "tech_future",
}

# 场景级 prompt 模板:按 scene type 维度,用"主体/动作/环境/镜头/光线/画质"五要素
# 关键原则:
#   1. 不要求模型生成中文字 → 文字交给 ffmpeg 字幕烧录
#   2. 每个 type 给出具体主体(车/人/场景物件),拒绝抽象的"科技感画面"
#   3. 每段附加 cinematic / photorealistic / 8k 画质关键词
#   4. 涉及车的场景统一用奕派 eπ007 实车特征描述,让 Seedance 出片更贴近自家车型

# 奕派 eπ007 视觉识别特征 - 核心常量,所有车镜头共用
# 实车特征(对照官方图):纯电中大型轿跑轿车 / 溜背低趴姿态 / 锋利贯穿式日行灯 +
# 矩阵式LED大灯组(L形竖向眼线) / 封闭式前脸无格栅 /
# 隐藏式门把手 / 悬浮式车顶+全景天幕 / 鸭尾翘臀 + 后贯穿式尾灯 / 19寸双色五辐大轮毂
_VEHICLE_SPEC_007 = (
    "东风奕派 eπ007 纯电轿跑型四门轿车,薄荷绿(Tiffany绿松石色)金属漆,"
    "低趴运动姿态,溜背式轿跑车顶,封闭式无格栅前脸,不出现可读车标或虚构徽标,"
    "锋利贯穿式LED日行灯带横贯前脸两侧,矩阵式L形竖向大灯组,"
    "隐藏式门把手,悬浮式黑色车顶+全景天幕,鸭尾翘臀短后悬,"
    "19寸双色五辐大轮毂搭配红色刹车卡钳,车尾贯穿式LED尾灯"
)

_SCENE_PROMPT_TEMPLATES = {
    "cover": (
        f"电影级开场镜头,一辆{_VEHICLE_SPEC_007},缓慢驶入未来感展厅,"
        "车身金属漆面反光强烈,环境是深蓝紫色霓虹氛围、地面湿滑反光,"
        "镜头从低位3/4前侧角度环绕推进,景深浅,体积光穿过淡淡烟雾,"
        "cinematic lighting, photorealistic, ultra detailed, 8k, sharp focus"
    ),
    "summary": (
        "宽阔现代化经营战情室,落地玻璃幕墙外是城市夜景天际线,"
        "中央指挥台前一位西装高管背影站立俯瞰桌面屏幕,"
        "周围多块巨型屏幕亮起冷蓝色数据图表,"
        "镜头从高位缓慢下推过肩,cinematic, photorealistic, ultra detailed, 8k"
    ),
    "trend": (
        f"汽车4S店明亮展厅内一辆{_VEHICLE_SPEC_007},停在旋转展台上缓缓自转,"
        "顶光打亮车身,背景是虚化的客户人群在浏览车型,"
        "镜头围绕车体水平环绕,景深浅,"
        "photorealistic, cinematic, sharp focus, depth of field, 8k"
    ),
    "ranking": (
        f"现代汽车维修车间,一辆{_VEHICLE_SPEC_007}停放在升降机平台,"
        "一名工程师在车前侧操作平板诊断设备,车身金属漆与轮毂泛着冷色调反光,"
        "顶部排灯整齐照射,镜头从工程师后方过肩缓慢推进至车头日行灯特写,"
        "cinematic, hyperrealistic, sharp focus, 8k"
    ),
    "distribution": (
        "汽车4S店服务接待区,一位顾问手持平板与客户面对面讲解,"
        f"身后远景是一辆静止展示的{_VEHICLE_SPEC_007},自然光从落地窗洒入,景深浅,"
        "镜头平移搭配微微推进,photorealistic, cinematic, 8k"
    ),
    "alert": (
        "经营战情室主屏特写,屏幕上数据曲线异常陡降并出现红色警示边框,"
        "前景虚化的西装高管侧脸表情凝重,室内灯光偏暗,屏幕冷光打在脸上,"
        "镜头从屏幕缓慢拉远到人物半身,"
        "cinematic dramatic lighting, photorealistic, 8k, sharp focus"
    ),
    "actions": (
        "未来感战略沙盘俯视特写,沙盘上一座微缩城市,"
        "三道金色光路从中心向外延展并依次被点亮,"
        "环境深蓝紫色,镜头从俯视缓慢转到45度斜视,周围有粒子光效环绕,"
        "cinematic, sci-fi, ultra detailed, sharp focus, 8k"
    ),
    "footer": (
        f"一辆{_VEHICLE_SPEC_007},在山间盘山公路上行驶,"
        "夕阳橙金色光线从侧后方打来,薄荷绿车身光泽强烈,贯穿式日行灯点亮,"
        "镜头从车后3/4跟拍并缓慢拉远到航拍全景,公路两侧林木掠过,"
        "cinematic, photorealistic, golden hour, ultra detailed, 8k"
    ),
}


def _strip_markdown(text: str) -> str:
    """剥除 LLM 简报片段里的 markdown 标记,避免被 TTS 读出"井号"或字幕里出现 # / ** / ` / > 等符号。

    输入往往是 briefing 的 summary / insight / msg 字段,LLM 习惯写带 markdown 的段落:
        '# eπ007 破局服务与信任差\n> 周期:2026-05 · 生成于:2026-05-09\n**eπ007** `销售记录规模` **100,000 条**...'
    上视频后字幕里就出现 "# eπ007 与 Model Y..."、"**eπ007**" 这种碍眼的原文标记。
    本函数只剥**符号**,保留所有正文文字,顺序不变。
    """
    if not text:
        return ""
    # 去掉系统报告名/历史任务里常见的长数字 ID 和元信息,避免 TTS 念出无意义噪声。
    text = re.sub(r"[-_]\d{10,}\b", "", text)
    text = re.sub(r"\b\d{12,}\b", "", text)
    text = re.sub(r"周期[:：]\s*\d{4}[-/]\d{1,2}\s*[·,，;； ]*\s*生成于[:：]\s*\d{4}[-/]\d{1,2}[-/]\d{1,2}", "", text)
    # 1. 行首 ATX 标题(# / ## / ### …)整个行首符号串删掉,留标题文字
    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.MULTILINE)
    # 简报摘要被拼到句中时,井号不一定出现在行首。
    text = re.sub(r"(?<=[。！？\s])#{1,6}\s*", "", text)
    # 2. 行首引用 > / 列表 - * + 1.
    text = re.sub(r"^\s*>+\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    # 3. 粗体 / 斜体 / 删除线 / 行内代码:保留中间文字,只去符号
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"__([^_]+)__", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"_([^_]+)_", r"\1", text)
    text = re.sub(r"~~([^~]+)~~", r"\1", text)
    text = re.sub(r"`+([^`]+)`+", r"\1", text)
    text = text.replace("#", "")
    # 4. 链接 [text](url) → text;图片 ![alt](url) → alt
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    # 5. 围栏代码块 ```...``` 整段去掉
    text = re.sub(r"```[\s\S]*?```", "", text)
    # 6. 多余空白:把连续换行 / 空格压成单空格(SRT 单条字幕通常一行)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tts_safe(text: str, max_chars: int = 95) -> str:
    """清理 TTS 输入:剥 markdown / emoji / 特殊符号,限制长度"""
    text = _strip_markdown(text)
    text = re.sub(r"[\U0001F300-\U0001FAFF]", "", text)  # emoji
    text = re.sub(r"[⭐🔥🔻🔺📊🎬🎥]", "", text)
    text = re.sub(r"[「」『』【】《》]", "", text)
    text = text.strip()
    # 超长时截到最近的中文句号/分号收尾,而不是硬切产生"点点点"
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    for sep in ("。", "；", ";", "，", "."):
        idx = cut.rfind(sep)
        if idx > max_chars * 0.6:
            return cut[: idx + 1]
    return cut + "。"


def _clean_headline(text: str, max_chars: int = 46) -> str:
    """清理报告标题:去掉任务 ID,并把过长标题压成适合视频口播的一句。"""
    cleaned = _strip_markdown(text or "").strip(" -_")
    if len(cleaned) <= max_chars:
        return cleaned or "经营战略简报"
    cut = cleaned[:max_chars]
    for sep in ("，", ",", "；", ";", "。", " "):
        idx = cut.rfind(sep)
        if idx > max_chars * 0.55:
            return cut[:idx].strip(" ，,；;。") or cleaned[:max_chars]
    return cut.rstrip("，,；;。") + "。"


def _scene_prompt(scene_type: str) -> str:
    """根据 scene type 取对应模板,缺省回退到 summary 商务场景。"""
    return _SCENE_PROMPT_TEMPLATES.get(scene_type) or _SCENE_PROMPT_TEMPLATES["summary"]


def briefing_from_markdown(filename: str, md_text: str) -> Dict[str, Any]:
    """把没有同名 JSON 的历史 Markdown 简报转成最小结构化 briefing。

    旧逻辑直接取 Markdown 前 300 字做 executive_summary,会把标题、日期、审计 ID 等噪声念进视频。
    这里只提取演示视频真正需要的标题、摘要、核心洞察和行动建议。
    """
    h1 = re.search(r"^\s*#\s+(.+?)\s*$", md_text, flags=re.MULTILINE)
    title = _clean_headline(h1.group(1) if h1 else filename.replace(".md", ""))

    bold = re.search(r"^\s*\*\*(.+?)\*\*\s*$", md_text, flags=re.MULTILINE)
    headline = _clean_headline(bold.group(1) if bold else title)

    kpi_strip: List[Dict[str, Any]] = []
    kpi_line_match = re.search(r"`([^`]+)`\s*\*\*([^*]+)\*\*.*", md_text)
    if kpi_line_match:
        kpi_line = kpi_line_match.group(0)
        for label, value in re.findall(r"`([^`]+)`\s*\*\*([^*]+)\*\*", kpi_line)[:4]:
            kpi_strip.append({"label": label.strip(), "value": value.strip(), "delta": ""})

    summary = ""
    summary_match = re.search(r"##\s*一[、.．]\s*摘要\s*(.*?)(?=\n##\s)", md_text, flags=re.S)
    if summary_match:
        summary = _strip_markdown(summary_match.group(1))

    sections: List[Dict[str, Any]] = []
    for m in re.finditer(r"###\s*\d+[.．]\s*(.+?)\n(.*?)(?=\n###\s*\d+[.．]|\n##\s|$)", md_text, flags=re.S):
        title_raw = _strip_markdown(m.group(1))
        block = m.group(2)
        insight_match = re.search(r"💡\s*(.+)", block)
        insight = _strip_markdown(insight_match.group(1)) if insight_match else ""
        delta_match = re.search(r"环比[:：]\s*([+-]?\d+(?:\.\d+)?)", block)

        if "趋势" in title_raw:
            data: List[Dict[str, Any]] = []
            data_match = re.search(r"-\s*数据[:：]\s*(.+)", block)
            if data_match:
                for x, y in re.findall(r"([^=/\s]+)\s*=\s*([+-]?\d+(?:\.\d+)?)", data_match.group(1)):
                    try:
                        data.append({"x": x.strip(), "y": float(y)})
                    except ValueError:
                        continue
            sections.append({
                "type": "trend",
                "title": title_raw,
                "data": data,
                "delta": {"baseline": "环比", "value": float(delta_match.group(1))} if delta_match else {},
                "insight": insight,
            })
            continue

        if "HIGH" in block or "WARNING" in block or "风险" in title_raw or "痛点" in title_raw:
            msg_match = re.search(r"(?:HIGH|WARNING)\*\*?:?\s*(.+)", block)
            evidence = [
                _strip_markdown(e)
                for e in re.findall(r"^\s*-\s+(.+)$", block, flags=re.MULTILINE)
                if "证据" not in e
            ][:3]
            sections.append({
                "type": "alert",
                "level": "high" if "HIGH" in block else "warning",
                "title": title_raw,
                "msg": _strip_markdown(msg_match.group(1)) if msg_match else insight,
                "evidence": evidence,
            })
            continue

        if "TOP" in title_raw or "分布" in title_raw:
            # "车型20/车型49"这类内部 ID 对用户没有解释价值,视频里跳过。
            if "车型" in title_raw and re.search(r"车型\d+", block):
                continue
            rows: List[List[str]] = []
            columns: List[str] = []
            table_lines = [line for line in block.splitlines() if line.strip().startswith("|")]
            if len(table_lines) >= 2:
                columns = [c.strip() for c in table_lines[0].strip("|").split("|")]
                for line in table_lines[2:7]:
                    cols = [c.strip() for c in line.strip("|").split("|")]
                    if cols and not set(cols[0]) <= {"-", " "}:
                        rows.append(cols)
            else:
                for name, value in re.findall(r"^\s*-\s*([^:：]+)[:：]\s*([+-]?\d+(?:\.\d+)?)", block, flags=re.MULTILINE):
                    rows.append([name.strip(), value.strip()])
                columns = ["维度", "数值"]
            sections.append({
                "type": "ranking",
                "title": title_raw,
                "columns": columns,
                "rows": rows,
                "insight": insight,
            })

    actions: List[Dict[str, Any]] = []
    action_match = re.search(r"##\s*三[、.．]\s*行动建议\s*(.*?)(?=\n##\s|$)", md_text, flags=re.S)
    if action_match:
        action_block = action_match.group(1)
        for level, owner, action, deadline in re.findall(
            r"^\s*-\s*\[([A-Z]+)\]\s*\*\*([^*]+)\*\*\s*·\s*(.+?)\s*·\s*截止\s*(.+?)\s*$",
            action_block,
            flags=re.MULTILINE,
        )[:5]:
            actions.append({
                "level": level,
                "owner": owner.strip(),
                "action": action.strip(),
                "deadline": deadline.strip(),
            })

    return {
        "meta": {"title": title},
        "cover": {"headline": headline, "kpi_strip": kpi_strip},
        "executive_summary": summary,
        "sections": sections,
        "actions": actions,
    }


# ============================================================
# 旁白口语化辅助
# ============================================================

# TTS(edge-tts XiaoxiaoNeural)中文语速实测 ~3.8 字/秒,留点呼吸 → 取 3.5 字/秒
_TTS_CPS = 3.5


def _estimate_duration(text: str, *, min_s: float = 6.0, max_s: float = 22.0) -> float:
    """根据旁白字数估算分镜时长,避免 12 秒固定窗口里念 60 字念不完 / 念 20 字干等。"""
    n = len(text or "")
    base = n / _TTS_CPS
    # 给画面留 1.2 秒"开场+收尾"缓冲
    return max(min_s, min(max_s, base + 1.2))


def media_duration_s(path: Path, fallback: Optional[float] = None) -> Optional[float]:
    """用 ffmpeg 读取音视频真实时长,供字幕时间轴与分镜拼接对齐。"""
    if not FFMPEG_BIN or not Path(path).exists():
        return fallback
    cmd = [FFMPEG_BIN, "-i", str(Path(path).resolve()), "-f", "null", "-"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
    except Exception:
        return fallback
    text = (proc.stderr or "") + (proc.stdout or "")
    # VBR mp3 的 header Duration 经常偏短;解码到 null 后尾部 time= 更接近真实播放时长。
    times = re.findall(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if times:
        h, minute, sec = times[-1]
        try:
            return int(h) * 3600 + int(minute) * 60 + float(sec)
        except ValueError:
            pass
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not m:
        return fallback
    h, minute, sec = m.groups()
    try:
        return int(h) * 3600 + int(minute) * 60 + float(sec)
    except ValueError:
        return fallback


def _humanize_pct(v: Any) -> str:
    """3.5 → '上涨 3.5%' / -3.5 → '下降 3.5%' / 0 → '基本持平'。"""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(f) < 0.05:
        return "基本持平"
    arrow = "上涨" if f > 0 else "下降"
    return f"{arrow} {abs(f):.1f}%"


def _kpi_to_speech(kpi: Dict[str, Any]) -> str:
    """单个 KPI → 口语短句。'销售记录规模 100,000 条,覆盖8个销售门店'"""
    label = (kpi.get("label") or "").strip()
    value = (kpi.get("value") or "").strip()
    delta = (kpi.get("delta") or "").strip()
    parts = []
    if label and value:
        parts.append(f"{label}{value}")
    elif value:
        parts.append(value)
    if delta:
        parts.append(delta)
    return ",".join(parts)


def _build_cover_voiceover(headline: str, kpi_strip: List[Dict[str, Any]]) -> str:
    """封面旁白:开场吊口 + 4 个 KPI 用"先 / 再 / 还有"串起来,落到 headline 金句"""
    headline = _clean_headline(headline)
    intro = "智擎参谋,本期我们来看奕派 eπ007。"
    if kpi_strip:
        # 取前 3 个 KPI(避免过长),用过门词串成一句口语
        connectors = ["先看", "再看", "还有"]
        kpi_lines = []
        for i, kpi in enumerate(kpi_strip[:3]):
            speech = _kpi_to_speech(kpi)
            if speech:
                kpi_lines.append(f"{connectors[i]}:{speech}")
        kpi_part = ";".join(kpi_lines) + "。" if kpi_lines else ""
    else:
        kpi_part = ""
    closing = f"一句话总结 —— {headline}。"
    return f"{intro}{kpi_part}{closing}"


def _build_summary_voiceover(summary: str) -> str:
    """整体研判:在 LLM 摘要前加"先把整盘看一眼"过门"""
    summary = _strip_markdown(summary)
    return f"先把整盘看一眼。{summary}"


def _trend_voiceover(sec: Dict[str, Any]) -> str:
    """trend 类:抓 delta + 起止数据点,生成"X月到X月,从X降到X,环比下降3.5%"。"""
    title = sec.get("title", "")
    insight = sec.get("insight") or ""
    data = sec.get("data") or []
    delta = sec.get("delta") or {}
    # 起止数据点
    start_end = ""
    if len(data) >= 2:
        first, last = data[0], data[-1]
        fx = first.get("x", "")
        lx = last.get("x", "")
        fy = first.get("y")
        ly = last.get("y")
        if fy is not None and ly is not None:
            try:
                # 销售额数据是"万元"单位,直接读出来
                start_end = f"从{fx}到{lx},数值由{float(fy):,.0f}变化到{float(ly):,.0f}。"
            except Exception:
                start_end = ""
    delta_phrase = ""
    if delta.get("value") is not None:
        baseline = delta.get("baseline") or "环比"
        delta_phrase = f"{baseline}{_humanize_pct(delta.get('value'))},是个明显信号 —— {insight}。"
    elif insight:
        delta_phrase = f"{insight}。"
    head = f"先看{title}。"
    return f"{head}{start_end}{delta_phrase}".strip()


def _ranking_voiceover(sec: Dict[str, Any]) -> str:
    """ranking 类:读 TOP1-2 的具体名字 + 数字,而不是抽象 insight。
    第三列含义按 columns 自适应(可能是占比、可能是金额),不硬编码成"占 X"。"""
    title = sec.get("title", "")
    rows = sec.get("rows") or []
    columns = sec.get("columns") or []
    insight = sec.get("insight") or ""
    if rows and len(rows[0]) >= 2:
        head = f"再看{title}。"
        # 从 columns 拿出"指标"和"附加列"的口播标签
        metric_label = columns[1] if len(columns) > 1 else ""
        extra_label = columns[2] if len(columns) > 2 else ""
        leaders = []
        for idx, row in enumerate(rows[:2]):
            name = str(row[0]) if len(row) > 0 else ""
            metric = str(row[1]) if len(row) > 1 else ""
            extra = str(row[2]) if len(row) > 2 else ""
            if not (name and metric):
                continue
            if idx == 0:
                # TOP1:用"排第一" + 完整标签
                m_part = f"{metric_label}{metric}" if metric_label else metric
                show_extra = extra and extra_label and "金额" not in extra_label and len(extra) <= 16
                e_part = f",{extra_label}{extra}" if show_extra else ""
                leaders.append(f"{name}排第一,{m_part}{e_part}")
            else:
                # TOP2:用"紧随其后" + 单一指标即可,避免太长
                m_part = f"{metric_label}{metric}" if metric_label else metric
                leaders.append(f"紧随其后是{name},{m_part}")
        body = ";".join(leaders) + "。" if leaders else ""
        tail = f"也就是说,{insight}。" if insight else ""
        return f"{head}{body}{tail}"
    return f"再看{title}。{insight}。"


def _alert_voiceover(sec: Dict[str, Any]) -> str:
    """alert 类:用"重点来了 / 注意"提调,evidence 第一条做硬证据"""
    title = sec.get("title", "")
    msg = sec.get("msg") or sec.get("insight") or ""
    evidence = sec.get("evidence") or []
    level = (sec.get("level") or "").lower()
    cue = "重点来了" if level == "high" else "需要注意"
    head = f"{cue},{title}。"
    body = f"{msg}。"
    proof = ""
    if evidence:
        # 拿前 2 条 evidence 拼"具体来说" - 数字最有冲击力
        proof_items = [str(e) for e in evidence[:2] if str(e).strip()]
        if proof_items:
            proof = "具体来说:" + ";".join(proof_items) + "。"
    return f"{head}{body}{proof}"


def _distribution_voiceover(sec: Dict[str, Any]) -> str:
    """distribution 类:类似 ranking,但读 top 维度名"""
    title = sec.get("title", "")
    insight = sec.get("insight") or ""
    return f"再看{title}。{insight}。"


def _section_voiceover(sec: Dict[str, Any]) -> str:
    """按 section type 分发到对应的口语化组装函数"""
    sec_type = sec.get("type", "")
    if sec_type == "trend":
        return _trend_voiceover(sec)
    if sec_type == "ranking":
        return _ranking_voiceover(sec)
    if sec_type == "alert":
        return _alert_voiceover(sec)
    if sec_type == "distribution":
        return _distribution_voiceover(sec)
    title = sec.get("title", "")
    insight = sec.get("insight") or sec.get("msg") or ""
    return f"{title}。{insight}。"


def _build_actions_voiceover(actions: List[Dict[str, Any]]) -> str:
    """行动建议:用"第一 / 第二 / 第三"清晰列点,而不是分号堆砌"""
    if not actions:
        return ""
    intro = "那么接下来怎么办?三件事最紧要。"
    ordinals = ["第一", "第二", "第三"]
    items = []
    for i, a in enumerate(actions[:3]):
        action = (a.get("action") or "").strip()
        owner = (a.get("owner") or "").strip()
        if not action:
            continue
        prefix = ordinals[i] if i < len(ordinals) else f"第{i+1}"
        if owner:
            items.append(f"{prefix},{owner}牵头,{action}")
        else:
            items.append(f"{prefix},{action}")
    body = "。".join(items) + "。" if items else ""
    return f"{intro}{body}"


def _build_footer_voiceover(headline: str) -> str:
    """收尾:回扣主题 + 行动呼号,比"以上为本期简报"更有力度"""
    headline = _clean_headline(headline)
    return f"数据已经把方向指明了。{headline} —— 智擎参谋,陪您把每一个决策做扎实。"


def extract_script_from_briefing(briefing: Dict[str, Any]) -> VideoScript:
    """
    把 BriefingDoc(.json) 切成 5-7 幕分镜脚本,总时长按旁白字数动态估算。

    口语化策略(2026-05-10 重写):
    - 封面:把 KPI 4 项数字念出来,用"先看 / 再看 / 还有"过门 → 落到 headline
    - 数据段:trend 读起止 + 涨跌幅,ranking 读 TOP2 具体名,alert 读 evidence 硬证据
    - 行动:第一 / 第二 / 第三 顺序词,带 owner
    - 收尾:回扣 headline + 行动呼号

    画面 prompt 不依赖文案,继续用场景模板(已带奕派 007 实车特征)。
    """
    cover_data = briefing.get("cover") or {}
    meta = briefing.get("meta") or {}
    headline = _clean_headline(cover_data.get("headline") or meta.get("title", "经营战略简报"))
    kpi_strip = cover_data.get("kpi_strip") or []
    summary = (briefing.get("executive_summary") or "").strip()
    sections = briefing.get("sections") or []
    actions = briefing.get("actions") or []

    scenes: List[Scene] = []

    # ---- 幕 1:封面 + KPI 数字朗读 ----
    cover_voice = _build_cover_voiceover(headline, kpi_strip)
    cover_voice = _tts_safe(cover_voice, max_chars=160)
    scenes.append(Scene(
        index      = 1,
        style      = _STYLE_FOR_TYPE["cover"],
        title      = headline,
        voiceover  = cover_voice,
        prompt     = _scene_prompt("cover"),
        duration_s = _estimate_duration(cover_voice, min_s=8.0, max_s=18.0),
    ))

    # ---- 幕 2:整体研判 ----
    if summary:
        sum_voice = _build_summary_voiceover(summary)
        sum_voice = _tts_safe(sum_voice, max_chars=150)
        scenes.append(Scene(
            index      = 2,
            style      = _STYLE_FOR_TYPE["summary"],
            title      = "整体研判",
            voiceover  = sum_voice,
            prompt     = _scene_prompt("summary"),
            duration_s = _estimate_duration(sum_voice, min_s=8.0, max_s=18.0),
        ))

    # ---- 幕 3+:核心发现(取 trend / ranking / alert / distribution 的前 3 条) ----
    picked_sections = [
        s for s in sections
        if s.get("type") in ("trend", "ranking", "distribution", "alert")
    ][:3]
    for sec in picked_sections:
        sec_type = sec.get("type", "trend")
        title = sec.get("title", "核心发现")
        voice = _section_voiceover(sec)
        voice = _tts_safe(voice, max_chars=160)
        scenes.append(Scene(
            index      = len(scenes) + 1,
            style      = _STYLE_FOR_TYPE.get(sec_type, "business_real"),
            title      = title,
            voiceover  = voice,
            prompt     = _scene_prompt(sec_type),
            duration_s = _estimate_duration(voice, min_s=8.0, max_s=22.0),
        ))

    # ---- 幕 N-1:行动建议(第一 / 第二 / 第三) ----
    if actions:
        act_voice = _build_actions_voiceover(actions)
        act_voice = _tts_safe(act_voice, max_chars=180)
        scenes.append(Scene(
            index      = len(scenes) + 1,
            style      = _STYLE_FOR_TYPE["actions"],
            title      = "行动建议",
            voiceover  = act_voice,
            prompt     = _scene_prompt("actions"),
            duration_s = _estimate_duration(act_voice, min_s=10.0, max_s=22.0),
        ))

    # ---- 幕 N:收尾 ----
    footer_voice = _build_footer_voiceover(headline)
    footer_voice = _tts_safe(footer_voice, max_chars=120)
    scenes.append(Scene(
        index      = len(scenes) + 1,
        style      = _STYLE_FOR_TYPE["footer"],
        title      = "智擎参谋",
        voiceover  = footer_voice,
        prompt     = _scene_prompt("footer"),
        duration_s = _estimate_duration(footer_voice, min_s=6.0, max_s=12.0),
    ))

    total = sum(s.duration_s for s in scenes)
    return VideoScript(title=headline, total_duration=total, scenes=scenes)


def script_to_markdown(script: VideoScript) -> str:
    """把脚本格式化成 markdown,便于审稿"""
    lines = [f"# 视频脚本 · {script.title}", ""]
    lines.append(f"- 总时长: **{script.total_duration:.1f} 秒**")
    lines.append(f"- 分镜数: **{len(script.scenes)}**")
    lines.append(f"- 风格: 混合 (开场/行动=科技未来;数据/痛点=商务写实)\n")

    for s in script.scenes:
        style_cn = "科技未来" if s.style == "tech_future" else "商务写实"
        lines.append(f"## 幕 {s.index} · {s.title}  ({s.duration_s:.0f}s · {style_cn})")
        lines.append(f"**旁白**: {s.voiceover}")
        lines.append("")
        lines.append(f"**画面 prompt**: {s.prompt}")
        lines.append("")
    return "\n".join(lines)


# ============================================================
# 2. 分镜配图(matplotlib 占位,明天换 Seedance)
# ============================================================

def _setup_matplotlib_chinese() -> None:
    """配中文字体,Windows 用 SimHei / 微软雅黑"""
    import matplotlib
    matplotlib.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'sans-serif']
    matplotlib.rcParams['axes.unicode_minus'] = False


def render_storyboard_png(scene: Scene, out_path: Path, size=(1280, 720)) -> Path:
    """
    用 matplotlib 渲染单个分镜静态图。
    tech_future  → 蓝紫色赛博风
    business_real → 浅色商务风
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _setup_matplotlib_chinese()

    fig = plt.figure(figsize=(size[0] / 100, size[1] / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])

    if scene.style == "tech_future":
        # 蓝紫色赛博风渐变背景
        from matplotlib.colors import LinearSegmentedColormap
        import numpy as np
        cmap = LinearSegmentedColormap.from_list("cyber", ["#0f172a", "#1e1b4b", "#312e81", "#4c1d95"])
        gradient = np.linspace(0, 1, 256).reshape(1, -1).repeat(256, axis=0)
        ax.imshow(gradient, aspect="auto", cmap=cmap, extent=[0, 1, 0, 1])
        title_color = "#fbbf24"   # 金色
        body_color = "#cbd5e1"
    else:
        # 商务浅色
        from matplotlib.colors import LinearSegmentedColormap
        import numpy as np
        cmap = LinearSegmentedColormap.from_list("biz", ["#eff6ff", "#dbeafe", "#e0e7ff"])
        gradient = np.linspace(0, 1, 256).reshape(1, -1).repeat(256, axis=0)
        ax.imshow(gradient, aspect="auto", cmap=cmap, extent=[0, 1, 0, 1])
        title_color = "#0f172a"
        body_color = "#475569"

    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # 幕次小字
    ax.text(0.04, 0.92, f"SCENE {scene.index:02d}",
            color=body_color, fontsize=14, family="monospace",
            transform=ax.transAxes, alpha=0.7)

    # 主标题
    ax.text(0.5, 0.55, scene.title,
            color=title_color, fontsize=46, fontweight="bold",
            ha="center", va="center", transform=ax.transAxes,
            wrap=True)

    # 副标题(旁白节选)
    voice_short = scene.voiceover[:60] + ("…" if len(scene.voiceover) > 60 else "")
    ax.text(0.5, 0.34, voice_short,
            color=body_color, fontsize=18,
            ha="center", va="center", transform=ax.transAxes)

    # 底部品牌
    ax.text(0.5, 0.08, "智擎参谋 · 汽车经营全景 AI",
            color=title_color, fontsize=14, fontweight="bold",
            ha="center", va="center", transform=ax.transAxes,
            alpha=0.85)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=100, bbox_inches=None, pad_inches=0)
    plt.close(fig)
    return out_path


# ============================================================
# 3. TTS 配音 (edge-tts 中文女声)
# ============================================================

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"  # 微软小晓,中文女声,自然语速


async def tts_synth_async(text: str, out_path: Path, voice: str = DEFAULT_VOICE) -> Path:
    import edge_tts
    out_path.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(text=text, voice=voice)
    await communicate.save(str(out_path))
    return out_path


def tts_synth(text: str, out_path: Path, voice: str = DEFAULT_VOICE) -> Path:
    """同步包装"""
    return asyncio.run(tts_synth_async(text, out_path, voice))


# ============================================================
# 4. 字幕 SRT 生成
# ============================================================

def _format_srt_time(seconds: float) -> str:
    ms = int(round((seconds - int(seconds)) * 1000))
    total = int(seconds)
    if ms >= 1000:
        total += 1
        ms -= 1000
    h = int(total // 3600)
    m = int((total % 3600) // 60)
    s = int(total % 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _subtitle_chunks(text: str) -> List[str]:
    """把旁白拆成适合字幕停留的口语短句,避免整段太长或切换过快。"""
    text = _tts_safe(text, max_chars=260)
    raw = [p.strip() for p in re.split(r"(?<=[。！？；])", text) if p.strip()]
    chunks: List[str] = []
    for part in raw:
        if len(part) <= 34:
            chunks.append(part)
            continue
        clauses = [p.strip() for p in re.split(r"(?<=[，、：])", part) if p.strip()]
        buf = ""
        for clause in clauses:
            if len(buf + clause) <= 34:
                buf += clause
            else:
                if buf:
                    chunks.append(buf)
                buf = clause
        if buf:
            chunks.append(buf)
    return chunks or [text]


def _wrap_subtitle(text: str, max_chars: int = 24) -> str:
    if len(text) <= max_chars + 6:
        return text
    idx = max(
        (
            i for i in range(10, min(len(text), max_chars + 8))
            if text[i] in "，、：；" and i < len(text) - 4
        ),
        default=-1,
    )
    if idx > 0:
        return text[: idx + 1].strip() + "\n" + text[idx + 1:].strip()
    head = text[:max_chars].strip()
    tail = text[max_chars:].strip()
    if tail in "。！？；":
        return head + tail
    return head + "\n" + tail


def build_srt(script: VideoScript) -> str:
    lines: List[str] = []
    cursor = 0.0
    idx = 1
    for scene in script.scenes:
        chunks = _subtitle_chunks(scene.voiceover)
        weights: List[float] = []
        for chunk in chunks:
            compact = re.sub(r"\s+", "", chunk)
            # 数字、百分比、金额单位在中文 TTS 里会读得比字符数更久一点。
            number_extra = 0.0
            for token in re.findall(r"\d[\d,]*(?:\.\d+)?%?", compact):
                number_extra += 2.0 if token.endswith("%") else 1.0
            weights.append(max(1.0, float(len(compact)) + number_extra))
        total_weight = max(1.0, sum(weights))
        local = cursor
        scene_end = cursor + scene.duration_s
        raw_durations = [scene.duration_s * weight / total_weight for weight in weights]

        # 字幕要覆盖整段旁白,不能因为单条最小时长把最后几句挤没。
        min_dur = 1.8
        if len(raw_durations) * min_dur <= scene.duration_s:
            durations = [max(min_dur, dur) for dur in raw_durations]
            overflow = sum(durations) - scene.duration_s
            if overflow > 0:
                adjustable = sum(max(0.0, dur - min_dur) for dur in durations)
                if adjustable > 0:
                    durations = [
                        dur - overflow * max(0.0, dur - min_dur) / adjustable
                        for dur in durations
                    ]
        else:
            durations = raw_durations

        for pos, (chunk, dur) in enumerate(zip(chunks, durations)):
            end = scene_end if pos == len(chunks) - 1 else min(scene_end, local + dur)
            if end <= local:
                break
            lines.append(str(idx))
            lines.append(f"{_format_srt_time(local)} --> {_format_srt_time(end)}")
            lines.append(_wrap_subtitle(chunk))
            lines.append("")
            local = end
            idx += 1
        cursor = scene_end
    return "\n".join(lines)


# ============================================================
# 5. 画面后端抽象(明天接 Seedance)
# ============================================================

class IVideoBackend(Protocol):
    """画面生成后端抽象。LocalStub 用静态图;Seedance 用真视频片段。"""
    def render_scene(self, scene: Scene, workdir: Path) -> Optional[Path]: ...


class LocalStubBackend:
    """今天用:matplotlib 渲染静态分镜 PNG,作为 ffmpeg 拼接的素材"""
    def render_scene(self, scene: Scene, workdir: Path) -> Optional[Path]:
        out = workdir / f"storyboard_{scene.index:02d}.png"
        return render_storyboard_png(scene, out)


class SeedanceBackend:
    """火山方舟 Seedance(豆包文生视频)真实后端。

    API 流程(异步任务):
        POST  {base}/contents/generations/tasks   → 拿到 task_id
        GET   {base}/contents/generations/tasks/{task_id}  → 轮询 status
        status='succeeded' 后从 content.video_url 下载 mp4
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        resolution: str = "720p",
        duration_s: int = 5,
        poll_interval_s: float = 8.0,
        poll_timeout_s: float = 480.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.resolution = resolution
        self.duration_s = duration_s
        self.poll_interval_s = poll_interval_s
        self.poll_timeout_s = poll_timeout_s

    # ---- HTTP 内部方法 ----
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
        }

    def _build_prompt(self, scene: Scene) -> str:
        """把 scene.prompt 包装成 Seedance 期望的格式;
        参数走 CLI-style 后缀(--resolution / --duration / --ratio / --camerafixed),
        Seedance 文档里的标准约定。
        --camerafixed false:让模型自主运镜,出来的画面更具电影感而非定机位。"""
        # 时长向上取整到接口允许范围
        dur = max(3, min(int(self.duration_s), 12))
        return (
            f"{scene.prompt} "
            "画面中不要出现任何可读文字、品牌 logo、车标特写、虚构徽标、水印或字幕, "
            "no readable text, no logos, no emblems, no watermark, "
            f"--resolution {self.resolution} "
            f"--duration {dur} "
            f"--ratio 16:9 "
            f"--camerafixed false"
        )

    def _create_task(self, prompt: str) -> str:
        import httpx
        url = f"{self.base_url}/contents/generations/tasks"
        body = {
            "model":   self.model,
            "content": [{"type": "text", "text": prompt}],
        }
        r = httpx.post(url, json=body, headers=self._headers(), timeout=30.0)
        if r.status_code >= 400:
            raise RuntimeError(f"Seedance create_task HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        task_id = data.get("id") or data.get("task_id") or (data.get("data") or {}).get("id")
        if not task_id:
            raise RuntimeError(f"Seedance create_task 返回无 task_id: {str(data)[:300]}")
        return task_id

    def _poll_task(self, task_id: str) -> str:
        """轮询直到 succeeded,返回 video_url。"""
        import time as _time
        import httpx
        url = f"{self.base_url}/contents/generations/tasks/{task_id}"
        deadline = _time.time() + self.poll_timeout_s
        last_status = "unknown"
        while _time.time() < deadline:
            r = httpx.get(url, headers=self._headers(), timeout=30.0)
            if r.status_code >= 400:
                raise RuntimeError(f"Seedance poll HTTP {r.status_code}: {r.text[:300]}")
            data = r.json()
            # status 兼容大小写;status 路径有的版本在 data 顶层,有的在 data.data
            status = (
                data.get("status")
                or (data.get("data") or {}).get("status")
                or "unknown"
            ).lower()
            last_status = status
            if status in ("succeeded", "success"):
                # video_url 兼容多种位置
                content = data.get("content") or (data.get("data") or {}).get("content") or {}
                video_url = (
                    content.get("video_url")
                    or content.get("url")
                    or data.get("video_url")
                )
                if not video_url:
                    raise RuntimeError(f"Seedance succeeded 但找不到 video_url: {str(data)[:300]}")
                return video_url
            if status in ("failed", "cancelled", "canceled"):
                err = data.get("error") or (data.get("data") or {}).get("error") or data
                raise RuntimeError(f"Seedance 任务失败 status={status}: {str(err)[:300]}")
            # running / queued / pending → 继续等
            _time.sleep(self.poll_interval_s)
        raise RuntimeError(f"Seedance 任务轮询超时 {self.poll_timeout_s}s,last_status={last_status}")

    def _download(self, video_url: str, out_path: Path) -> Path:
        import httpx
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", video_url, timeout=120.0, follow_redirects=True) as r:
            if r.status_code >= 400:
                raise RuntimeError(f"Seedance 视频下载失败 HTTP {r.status_code}")
            with open(out_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)
        return out_path

    # ---- IVideoBackend ----
    def render_scene(self, scene: Scene, workdir: Path) -> Optional[Path]:
        prompt = self._build_prompt(scene)
        logger.info("[seedance] scene=%d 创建任务 model=%s", scene.index, self.model)
        task_id = self._create_task(prompt)
        logger.info("[seedance] scene=%d task_id=%s, 开始轮询", scene.index, task_id)
        video_url = self._poll_task(task_id)
        out = workdir / f"scene_{scene.index:02d}.mp4"
        self._download(video_url, out)
        logger.info("[seedance] scene=%d 已下载 %s (%d KB)",
                    scene.index, out.name, out.stat().st_size // 1024)
        scene.video_path = str(out)
        return out


def extract_first_frame(video_path: Path, out_path: Path, ts_s: float = 0.5) -> Optional[Path]:
    """
    从 mp4 抽一帧静态图作为分镜缩略。
    - ts_s: 取第 ts_s 秒(默认 0.5s,避开开场黑/白屏的第 0 帧)
    - 输出 jpg(与 LocalStub 的 png 区分,看后缀也能判断画面后端来源)
    抽帧失败返回 None,调用方自行兜底。
    """
    if not FFMPEG_BIN or not video_path.exists():
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        FFMPEG_BIN, "-y",
        "-ss", f"{ts_s:.2f}",
        "-i", str(video_path.resolve()),
        "-frames:v", "1",
        "-q:v", "2",
        str(out_path.resolve()),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=30)
        return out_path if out_path.exists() and out_path.stat().st_size > 0 else None
    except Exception as e:
        logger.warning("extract_first_frame 失败 %s: %s", video_path.name, e)
        return None


def build_video_backend() -> "IVideoBackend":
    """根据环境变量选 backend:
    - VIDEO_BACKEND=seedance + SEEDANCE_API_KEY 非空 → SeedanceBackend
    - 否则                                            → LocalStubBackend
    """
    try:
        from ..core.config import seedance_settings
    except Exception:
        return LocalStubBackend()

    if seedance_settings.video_backend == "seedance" and seedance_settings.api_key:
        try:
            return SeedanceBackend(
                api_key         = seedance_settings.api_key,
                base_url        = seedance_settings.base_url,
                model           = seedance_settings.model,
                resolution      = seedance_settings.resolution,
                duration_s      = seedance_settings.duration_s,
                poll_interval_s = seedance_settings.poll_interval_s,
                poll_timeout_s  = seedance_settings.poll_timeout_s,
            )
        except Exception as e:
            logger.warning("Seedance backend 初始化失败,降级 LocalStub: %s", e)
    return LocalStubBackend()


# ============================================================
# 6. ffmpeg 拼接
# ============================================================

def ffmpeg_assemble(
    scenes: List[Scene],
    workdir: Path,
    output: Path,
    burn_subtitles: Optional[Path] = None,
    error_log: Optional[List[str]] = None,
) -> Optional[Path]:
    """
    把每个 scene 的 image + audio 合成段视频,再首尾相连。
    今天:image (静态图持续 N 秒) + audio (mp3) → segment.mp4 → concat。
    明天:把 image 换成 video(Seedance 5-10s 片段),逻辑不变。
    error_log: 可选 list,追加每次 ffmpeg 错误尾部 200 字给上层暴露。
    """
    if not FFMPEG_BIN:
        logger.warning("ffmpeg 二进制不可用,跳过视频合成")
        if error_log is not None:
            error_log.append("FFMPEG_BIN is None")
        return None

    logger.info("[video] ffmpeg_assemble 开始,scenes=%d, ffmpeg=%s", len(scenes), FFMPEG_BIN)
    if error_log is not None:
        error_log.append(f"ENTER ffmpeg_assemble scenes={len(scenes)}")

    segments: List[Path] = []
    for sc in scenes:
        if not sc.audio_path:
            logger.warning("scene %d 缺 audio,跳过 (audio=%r)", sc.index, sc.audio_path)
            if error_log is not None:
                error_log.append(f"scene={sc.index} 缺音频")
            continue
        if not sc.video_path and not sc.image_path:
            logger.warning("scene %d 缺画面素材(无 video 也无 image),跳过", sc.index)
            if error_log is not None:
                error_log.append(f"scene={sc.index} 缺画面素材")
            continue

        seg = (workdir / f"seg_{sc.index:02d}.mp4").resolve()
        # 路径强制 resolve,防止 backend 启动 cwd 与相对路径不一致
        if sc.video_path:
            # 真视频片段 + 旁白 audio,视频循环至 audio 等长
            # 1080p 输出与 Seedance 输出分辨率对齐;静态图分支也升 1080p
            cmd = [
                FFMPEG_BIN, "-y",
                "-stream_loop", "-1",
                "-i", str(Path(sc.video_path).resolve()),
                "-i", str(Path(sc.audio_path).resolve()),
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-c:a", "aac",
                "-b:a", "128k",
                "-pix_fmt", "yuv420p",
                "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
                "-shortest",
                "-t", f"{sc.duration_s:.3f}",
                str(seg),
            ]
        else:
            # 静态图 + 旁白 audio
            cmd = [
                FFMPEG_BIN, "-y",
                "-loop", "1",
                "-i", str(Path(sc.image_path).resolve()),
                "-i", str(Path(sc.audio_path).resolve()),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "stillimage",
                "-c:a", "aac",
                "-b:a", "128k",
                "-pix_fmt", "yuv420p",
                "-shortest",
                "-t", f"{sc.duration_s:.3f}",
                "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2",
                str(seg),
            ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=120)
            segments.append(seg)
        except subprocess.CalledProcessError as e:
            tail = e.stderr.decode(errors='ignore')[-400:] if e.stderr else "(no stderr)"
            logger.error("ffmpeg 段视频失败 scene=%d: %s", sc.index, tail)
            if error_log is not None:
                error_log.append(f"scene={sc.index} CalledProcessError: {tail}")
        except subprocess.TimeoutExpired:
            logger.error("ffmpeg 段视频超时 scene=%d", sc.index)
            if error_log is not None:
                error_log.append(f"scene={sc.index} timeout")
        except Exception as e:
            logger.exception("ffmpeg 段视频未知异常 scene=%d", sc.index)
            if error_log is not None:
                error_log.append(f"scene={sc.index} {type(e).__name__}: {e}")

    if not segments:
        return None

    # concat - 必须用绝对路径,否则 ffmpeg 从工作目录解析会找不到段文件
    list_file = (workdir / "concat.txt").resolve()
    list_file.write_text(
        "\n".join(f"file '{seg.resolve().as_posix()}'" for seg in segments),
        encoding="utf-8",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output_abs = output.resolve()
    # 是否需要字幕烧录:有 srt 文件就先 concat 到中间产物,再烧字幕到最终输出
    need_subs = burn_subtitles is not None and Path(burn_subtitles).exists()
    concat_target = (workdir / "_concat_raw.mp4").resolve() if need_subs else output_abs

    cmd = [
        FFMPEG_BIN, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(concat_target),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
    except subprocess.CalledProcessError as e:
        tail = e.stderr.decode(errors='ignore')[-400:] if e.stderr else "(no stderr)"
        logger.error("ffmpeg concat 失败: %s", tail)
        if error_log is not None:
            error_log.append(f"concat CalledProcessError: {tail}")
        return None
    except Exception as e:
        logger.exception("ffmpeg concat 未知异常")
        if error_log is not None:
            error_log.append(f"concat {type(e).__name__}: {e}")
        return None

    if not need_subs:
        return output

    # ---- 字幕硬烧录 ----
    # subtitles filter 对路径敏感,Windows 下需要把反斜杠转正斜杠并转义冒号
    srt_abs = Path(burn_subtitles).resolve()
    srt_for_filter = srt_abs.as_posix().replace(":", r"\:")
    # 大字号、白字黑边、底部居中,FontName 用系统自带中文字体
    style = (
        "FontName=Microsoft YaHei,FontSize=22,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,"
        "Alignment=2,MarginV=60"
    )
    burn_cmd = [
        FFMPEG_BIN, "-y",
        "-i", str(concat_target),
        "-vf", f"subtitles='{srt_for_filter}':force_style='{style}'",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-c:a", "copy",
        "-pix_fmt", "yuv420p",
        str(output_abs),
    ]
    try:
        subprocess.run(burn_cmd, check=True, capture_output=True, timeout=300)
    except subprocess.CalledProcessError as e:
        tail = e.stderr.decode(errors='ignore')[-500:] if e.stderr else "(no stderr)"
        logger.error("ffmpeg 字幕烧录失败,降级返回 concat 原片: %s", tail)
        if error_log is not None:
            error_log.append(f"burn_subs CalledProcessError: {tail}")
        # 降级:把 concat 原片重命名为最终输出,字幕没烧但视频还在
        try:
            if concat_target.exists() and not output_abs.exists():
                concat_target.replace(output_abs)
            return output if output_abs.exists() else None
        except Exception:
            return None
    except Exception as e:
        logger.exception("ffmpeg 字幕烧录未知异常")
        if error_log is not None:
            error_log.append(f"burn_subs {type(e).__name__}: {e}")
        return None

    return output


# ============================================================
# 7. 顶层入口
# ============================================================

def synth_video(
    briefing: Dict[str, Any],
    out_root: Path,
    task_id: str,
    backend: Optional[IVideoBackend] = None,
    do_assemble: bool = True,
) -> VideoArtifacts:
    """
    端到端合成入口。
    返回所有产物路径(脚本 md/json + 分镜图 + 配音 + 字幕 + 最终 mp4 if 成功)。
    """
    backend = backend or build_video_backend()
    workdir = out_root / task_id
    workdir.mkdir(parents=True, exist_ok=True)
    notes_backend = type(backend).__name__

    notes: List[str] = []
    artifacts = VideoArtifacts(
        workdir     = str(workdir),
        script_md   = "",
        script_json = "",
    )

    # 1. 抽脚本
    script = extract_script_from_briefing(briefing)
    script_md_path = workdir / "script.md"
    script_md_path.write_text(script_to_markdown(script), encoding="utf-8")
    artifacts.script_md = str(script_md_path)
    script_json_path = workdir / "script.json"
    script_json_path.write_text(
        json.dumps(script.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    artifacts.script_json = str(script_json_path)
    notes.append(f"脚本 {len(script.scenes)} 幕,总时长 {script.total_duration:.1f}s")
    notes.append(f"画面后端: {notes_backend}")

    # 2. 分镜画面(后端可换:LocalStub / Seedance)
    for sc in script.scenes:
        try:
            out = backend.render_scene(sc, workdir)
            if out:
                if str(out).lower().endswith(".mp4"):
                    # Seedance 真视频片段 - render_scene 内部已写 sc.video_path
                    # storyboards 数组里塞静帧 jpg(给 UI 当缩略图),mp4 单独由 sc.video_path 承载
                    frame_out = workdir / f"storyboard_{sc.index:02d}.jpg"
                    frame = extract_first_frame(out, frame_out)
                    if frame:
                        sc.image_path = str(frame)
                        artifacts.storyboards.append(str(frame))
                    else:
                        # 抽帧失败兜底 - 用 LocalStub 静态图占位,保证 UI 不空
                        try:
                            stub = LocalStubBackend().render_scene(sc, workdir)
                            if stub:
                                sc.image_path = str(stub)
                                artifacts.storyboards.append(str(stub))
                        except Exception:
                            logger.exception("scene %d 抽帧+兜底都失败", sc.index)
                else:
                    sc.image_path = str(out)
                    artifacts.storyboards.append(str(out))
        except NotImplementedError as e:
            notes.append(f"画面后端待接入: {e}")
        except Exception as e:
            logger.exception("scene %d 画面渲染失败", sc.index)
            notes.append(f"scene {sc.index} 画面渲染失败: {e}")
            # Seedance 单幕失败时降级:用 LocalStub 生成静态图,保住整片不挂
            if not isinstance(backend, LocalStubBackend):
                try:
                    fallback_img = LocalStubBackend().render_scene(sc, workdir)
                    if fallback_img:
                        sc.image_path = str(fallback_img)
                        artifacts.storyboards.append(str(fallback_img))
                        notes.append(f"  ↳ scene {sc.index} 已用静态图兜底")
                except Exception:
                    logger.exception("scene %d LocalStub 兜底也失败", sc.index)

    # 3. TTS 配音(每幕一个 mp3)
    try:
        for sc in script.scenes:
            audio_path = workdir / f"audio_{sc.index:02d}.mp3"
            tts_synth(sc.voiceover, audio_path)
            sc.audio_path = str(audio_path)
            actual_duration = media_duration_s(audio_path, fallback=sc.duration_s)
            if actual_duration:
                sc.duration_s = actual_duration
            artifacts.audios.append(str(audio_path))
        notes.append(f"TTS 完成 {len(artifacts.audios)} 段")
        script.total_duration = sum(s.duration_s for s in script.scenes)
        script_md_path.write_text(script_to_markdown(script), encoding="utf-8")
        script_json_path.write_text(
            json.dumps(script.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.exception("TTS 失败")
        notes.append(f"TTS 失败,降级为纯素材模式: {e}")

    # 4. SRT 字幕
    srt_path = workdir / "script.srt"
    srt_path.write_text(build_srt(script), encoding="utf-8")
    artifacts.srt = str(srt_path)
    notes.append("字幕 SRT 已生成")

    # 5. ffmpeg 合成 (字幕硬烧录到画面)
    if do_assemble and FFMPEG_BIN:
        final = workdir / "final.mp4"
        ffmpeg_errors: List[str] = []
        out = ffmpeg_assemble(
            script.scenes,
            workdir,
            final,
            burn_subtitles=srt_path,
            error_log=ffmpeg_errors,
        )
        if out and out.exists():
            artifacts.final_mp4 = str(out)
            notes.append(f"final.mp4 合成成功 ({out.stat().st_size // 1024} KB)")
        else:
            notes.append("ffmpeg 合成失败,仅保留素材")
            for err in ffmpeg_errors[:3]:
                notes.append(f"  ⚠️ {err[:200]}")
    elif not FFMPEG_BIN:
        notes.append("ffmpeg 不可用,仅产出脚本/分镜/音频/字幕素材")

    artifacts.notes = notes
    return artifacts

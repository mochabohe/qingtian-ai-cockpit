"""
SchemaInspector ─ 字段角色识别 + 主键格式分析 + 跨源关联键候选

为什么需要这个模块（项目核心创新点）：
- 现场数据集字段更多、规模更大，但结构同源；任何写死字段名的代码都会在现场翻车
- 培训数据已经验证：销售表的 销售id（6 位前导零格式，如 "S040829"）与售后表的
  车辆销售ID（无前导零格式，如 "S40829"）虽是同一笔订单但字面不匹配，
  需要主键格式标准化才能 join。本模块把这条经验沉淀为可复用工具。

核心 API：
    infer_field_roles(df)              字段分类（time / dim / metric / id / text / unknown）
    detect_id_pattern(series)          推断 id 列的"前缀 + 数字位宽"格式
    normalize_id_series(series, width) 补齐前导零至指定位宽
    align_id_columns(s_a, s_b)         对两列做主键格式自动对齐，返回对齐后的列 + 报告
    detect_join_candidates(dfs)        跨源关联键候选检测
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


# ==== 数据结构 ====

@dataclass
class FieldRoles:
    """字段角色分类结果"""
    time_cols:    List[str] = field(default_factory=list)
    id_cols:      List[str] = field(default_factory=list)
    metric_cols:  List[str] = field(default_factory=list)
    dim_cols:     List[str] = field(default_factory=list)
    text_cols:    List[str] = field(default_factory=list)
    unknown_cols: List[str] = field(default_factory=list)
    field_meta:   Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IdPattern:
    """ID 列的格式推断结果"""
    looks_like_id:      bool
    prefix:             str = ""        # 例如 "S"
    digit_width:        int = 0         # 数字部分位数（取最大值）
    has_leading_zero:   bool = False    # 是否带前导零
    sample:             List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ==== 字段角色识别 ====

# 列名提示词（中英混合，命中即加权）
_TIME_HINTS   = ("date", "time", "datetime", "时间", "日期", "年月", "月份")
_ID_HINTS     = ("id", "ID", "编号", "单号", "编码", "代码", "code", "key")
_TEXT_HINTS   = ("内容", "评论", "描述", "备注", "说明", "现象", "原因", "remark", "comment", "desc", "content")


def _is_string_like(series: pd.Series) -> bool:
    """统一判断字符串列：兼容 pandas 旧版 object 与新版 string dtype"""
    return (
        pd.api.types.is_object_dtype(series)
        or pd.api.types.is_string_dtype(series)
    )


def _is_datetime_like(series: pd.Series, sample_size: int = 50) -> bool:
    """判断一列能否被解析为日期时间"""
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    if not _is_string_like(series):
        return False
    sample = series.dropna().astype(str).head(sample_size)
    if sample.empty:
        return False
    try:
        parsed = pd.to_datetime(sample, errors="coerce", format="mixed")
    except (TypeError, ValueError):
        parsed = pd.to_datetime(sample, errors="coerce")
    # 至少 70% 的样本能被解析
    return parsed.notna().mean() >= 0.7


def _is_id_column(name: str, series: pd.Series, n_rows: int) -> bool:
    """
    判断是否是 id 列。
    语义优先：列名命中 id/编号/单号/编码/code/key 提示词，直接认为是 id（无论基数）。
    例：车型id(56 个值)、活动id(12 个值)是低基数外键 id，靠列名命中识别。
    没命中提示词时，靠"高唯一率 + 看起来像 S\\d+ 模式"识别为 id。
    """
    name_l = str(name).lower()
    name_hit = any(h.lower() in name_l for h in _ID_HINTS)

    if name_hit:
        return True

    unique_ratio = series.nunique(dropna=True) / max(n_rows, 1)
    high_unique = unique_ratio >= 0.9
    if high_unique and detect_id_pattern(series).looks_like_id:
        return True
    return False


def _avg_text_len(series: pd.Series, sample_size: int = 200) -> float:
    """估算字符串列的平均长度"""
    sample = series.dropna().astype(str).head(sample_size)
    if sample.empty:
        return 0.0
    return float(sample.str.len().mean())


def infer_field_roles(df: pd.DataFrame) -> FieldRoles:
    """
    把 DataFrame 的列分类为 time / id / metric / dim / text / unknown

    分类优先级：time > id > text(长文本) > metric(数值) > dim(类别) > unknown
    """
    roles = FieldRoles()
    n_rows = len(df)

    for col in df.columns:
        name_l = str(col).lower()
        s = df[col]

        meta = {
            "dtype":          str(s.dtype),
            "n_unique":       int(s.nunique(dropna=True)),
            "null_ratio":     float(s.isna().mean()),
            "unique_ratio":   float(s.nunique(dropna=True) / max(n_rows, 1)),
        }

        # 1. 时间列
        if any(h in name_l for h in _TIME_HINTS) or _is_datetime_like(s):
            roles.time_cols.append(col)
            roles.field_meta[col] = {**meta, "role": "time"}
            continue

        # 2. id 列
        if _is_id_column(col, s, n_rows):
            pattern = detect_id_pattern(s)
            roles.id_cols.append(col)
            roles.field_meta[col] = {**meta, "role": "id", "id_pattern": pattern.to_dict()}
            continue

        # 3. 文本列（字符串 + 平均长度 > 30 + 列名命中或唯一率高）
        if _is_string_like(s):
            avg_len = _avg_text_len(s)
            name_hit_text = any(h in str(col) for h in _TEXT_HINTS)
            if avg_len >= 30 or name_hit_text:
                roles.text_cols.append(col)
                roles.field_meta[col] = {**meta, "role": "text", "avg_len": avg_len}
                continue

        # 4. 数值指标列
        if pd.api.types.is_numeric_dtype(s):
            roles.metric_cols.append(col)
            stats = {}
            try:
                stats = {
                    "min":    float(s.min()),
                    "max":    float(s.max()),
                    "mean":   float(s.mean()),
                }
            except Exception:
                pass
            roles.field_meta[col] = {**meta, "role": "metric", **stats}
            continue

        # 5. 维度列（字符串 + unique 数适中）
        if _is_string_like(s):
            n_uni = meta["n_unique"]
            if 1 < n_uni <= max(50, n_rows * 0.05):
                roles.dim_cols.append(col)
                roles.field_meta[col] = {**meta, "role": "dim"}
                continue

        # 6. 兜底
        roles.unknown_cols.append(col)
        roles.field_meta[col] = {**meta, "role": "unknown"}

    return roles


# ==== 主键格式推断与对齐 ====

_ID_REGEX = re.compile(r"^([A-Za-z]*)(\d+)$")


def detect_id_pattern(series: pd.Series, sample_size: int = 200) -> IdPattern:
    """
    推断 id 列的格式：前缀字符 + 数字位宽
    例：'S000001' → prefix='S', digit_width=6, has_leading_zero=True
        'S40829'  → prefix='S', digit_width=5, has_leading_zero=False
    """
    sample = series.dropna().astype(str).head(sample_size)
    if sample.empty:
        return IdPattern(looks_like_id=False)

    matches = sample.map(_ID_REGEX.match)
    valid = matches.dropna()
    # 至少 80% 的样本匹配 [字母前缀]?[数字]+
    if len(valid) / len(sample) < 0.8:
        return IdPattern(looks_like_id=False)

    prefixes = valid.map(lambda m: m.group(1))
    digits = valid.map(lambda m: m.group(2))

    if prefixes.nunique() != 1:
        # 前缀不一致，不视为单一格式
        return IdPattern(
            looks_like_id=False,
            sample=sample.head(5).tolist(),
        )

    prefix = prefixes.iloc[0]
    digit_widths = digits.map(len)
    max_width = int(digit_widths.max())
    min_width = int(digit_widths.min())

    # 前导零判定：如果固定位宽且最高位是 0 出现，则有前导零
    has_lead = bool(
        max_width == min_width
        and digits.str.startswith("0").any()
    )

    return IdPattern(
        looks_like_id=True,
        prefix=prefix,
        digit_width=max_width,
        has_leading_zero=has_lead,
        sample=sample.head(5).tolist(),
    )


def normalize_id_series(
    series: pd.Series,
    target_width: int,
    prefix: Optional[str] = None,
) -> pd.Series:
    """
    把 id 列规范化到指定数字位宽 (前导零无业务含义)。
    实现:先 lstrip('0') 去掉所有前导零,再 zfill 到 target_width。
    例:
        normalize_id_series(['S40829', 'S5167'], 6)        → ['S040829', 'S005167']
        normalize_id_series(['S00000003', 'S0000003'], 7)  → ['S0000003', 'S0000003']  (现场演示场景)
    设计要点:zfill 单独使用对"已经超过 target_width 的位串"无效,
    必须先去前导零再补零,才能让"S00000003"和"S0000003"这种位宽不一致的 id 对齐。
    """
    def _norm(v: Any) -> Any:
        if pd.isna(v):
            return v
        m = _ID_REGEX.match(str(v))
        if not m:
            return v
        p = prefix if prefix is not None else m.group(1)
        d_stripped = m.group(2).lstrip("0") or "0"  # 全 0 兜底为 "0",不让 lstrip 吃光
        d = d_stripped.zfill(target_width)
        return f"{p}{d}"
    return series.map(_norm)


def _actual_max_digit_width(series: pd.Series) -> int:
    """全量扫描序列,返回 ID 数字部分的实际最大位宽 (用于跨源对齐时确定 target_width)"""
    if series is None or len(series) == 0:
        return 0
    s = series.dropna().astype(str)
    if s.empty:
        return 0
    widths = s.map(lambda x: len(_ID_REGEX.match(x).group(2)) if _ID_REGEX.match(x) else 0)
    return int(widths.max() or 0)


def align_id_columns(
    s_a: pd.Series,
    s_b: pd.Series,
) -> Tuple[pd.Series, pd.Series, Dict[str, Any]]:
    """
    自动对齐两列 id：
    - 如果两列原本能直接 join（交集足够大），保持原值
    - 否则用"双侧实际最大数字位宽"作 target_width,通过 normalize_id_series 对齐
    返回：(对齐后 a, 对齐后 b, 报告)

    现场演示关键修复:
    - 旧逻辑用 detect_id_pattern.digit_width 推断位宽,该函数仅采样前 1000 行,
      售后表前几行恰好是 8 字符 'S0000003' 推断 width=7,但全量 88.5% 是 9 字符
      'S00000003',导致 zfill(7) 不动,匹配率仅 10.2%
    - 新逻辑改用全量扫描的 _actual_max_digit_width,加上 normalize_id_series
      内部"先 lstrip 再 zfill"的修复,可达 100% 对齐
    """
    pa = detect_id_pattern(s_a)
    pb = detect_id_pattern(s_b)

    set_a = set(s_a.dropna().astype(str))
    set_b = set(s_b.dropna().astype(str))
    direct_overlap = len(set_a & set_b)
    direct_overlap_ratio = direct_overlap / max(min(len(set_a), len(set_b)), 1)

    report = {
        "pattern_a":            pa.to_dict(),
        "pattern_b":            pb.to_dict(),
        "direct_overlap":       direct_overlap,
        "direct_overlap_ratio": direct_overlap_ratio,
        "normalized":           False,
        "target_width":         None,
        "after_overlap":        direct_overlap,
        "after_overlap_ratio":  direct_overlap_ratio,
    }

    # 直接关联够好（≥95%），不动
    if direct_overlap_ratio >= 0.95 or not (pa.looks_like_id and pb.looks_like_id):
        return s_a, s_b, report

    # 尝试统一位宽
    if pa.prefix != pb.prefix:
        # 前缀不同，无法对齐
        return s_a, s_b, report

    # 关键: target_width 用全量实际最大值,不要信 detect_id_pattern 的采样推断
    target_width = max(
        _actual_max_digit_width(s_a),
        _actual_max_digit_width(s_b),
        pa.digit_width,
        pb.digit_width,
    )
    s_a_norm = normalize_id_series(s_a, target_width, pa.prefix)
    s_b_norm = normalize_id_series(s_b, target_width, pa.prefix)

    set_an = set(s_a_norm.dropna().astype(str))
    set_bn = set(s_b_norm.dropna().astype(str))
    after_overlap = len(set_an & set_bn)
    after_ratio = after_overlap / max(min(len(set_an), len(set_bn)), 1)

    report.update({
        "normalized":          True,
        "target_width":        target_width,
        "after_overlap":       after_overlap,
        "after_overlap_ratio": after_ratio,
    })
    return s_a_norm, s_b_norm, report


# ==== Schema 自适应:启发式主键检测 ====

def detect_primary_id_column(
    df: pd.DataFrame,
    candidates: Optional[List[str]] = None,
    min_unique_ratio: float = 0.95,
) -> Optional[str]:
    """
    在 df 中识别"业务主键"列(unique_ratio 最高的 id 列)。

    用于 resolve_field_strict 的兜底:当 manifest 没声明 sale_id/repair_id 等别名时,
    退化为"找数据集里的主键 id 列"。

    Args:
        df: 已加载的 DataFrame
        candidates: 可选;限定只在这些列里挑(若 None 则用 infer_field_roles 自动找全部 id 列)
        min_unique_ratio: 阈值(默认 0.95);unique_ratio 低于该值视为非主键(可能是外键)

    Returns:
        最高 unique_ratio 的 id 列名;无候选 / 全部低于阈值则返回 None
    """
    if df is None or len(df) == 0:
        return None

    if candidates:
        id_cols = [c for c in candidates if c in df.columns]
    else:
        roles = infer_field_roles(df)
        id_cols = roles.id_cols

    if not id_cols:
        return None

    n_rows = len(df)
    scored: List[Tuple[str, float]] = []
    for col in id_cols:
        try:
            uniq = df[col].nunique(dropna=True) / max(n_rows, 1)
        except Exception:
            continue
        scored.append((col, float(uniq)))

    if not scored:
        return None

    scored.sort(key=lambda x: x[1], reverse=True)
    top_col, top_uniq = scored[0]
    if top_uniq < min_unique_ratio:
        return None
    return top_col


# ==== 跨源关联键候选 ====

def detect_join_candidates(
    dfs: Dict[str, pd.DataFrame],
    min_overlap_ratio: float = 0.5,
) -> List[Dict[str, Any]]:
    """
    输入多个 DataFrame（{name: df}），返回跨源关联键候选清单。

    匹配逻辑：对每对 (df_a, df_b) 的 id 列两两组合，做 align_id_columns，
    若对齐后 overlap_ratio ≥ min_overlap_ratio，则视为关联键候选。

    返回项格式：
    {
      "left":  {"df": "sales", "col": "销售id"},
      "right": {"df": "after", "col": "车辆销售ID"},
      "needs_normalize": True,
      "overlap_ratio_after": 1.0,
      "report": {...},
    }
    """
    # 先各自识别 id 列
    id_cols_per_df: Dict[str, List[str]] = {}
    for name, df in dfs.items():
        roles = infer_field_roles(df)
        id_cols_per_df[name] = roles.id_cols

    candidates: List[Dict[str, Any]] = []
    names = list(dfs.keys())
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for col_a in id_cols_per_df[a]:
                for col_b in id_cols_per_df[b]:
                    s_a, s_b, report = align_id_columns(dfs[a][col_a], dfs[b][col_b])
                    final_ratio = report["after_overlap_ratio"]
                    if final_ratio >= min_overlap_ratio:
                        candidates.append({
                            "left":                 {"df": a, "col": col_a},
                            "right":                {"df": b, "col": col_b},
                            "needs_normalize":      report["normalized"],
                            "overlap_ratio_after":  final_ratio,
                            "overlap_count_after":  report["after_overlap"],
                            "report":               report,
                        })

    # 按对齐后的 overlap 降序
    candidates.sort(key=lambda x: x["overlap_ratio_after"], reverse=True)
    return candidates


# ============================================================
# P0-2 数据体检中心:健康评分 + 风险扫描
# ============================================================

@dataclass
class HealthDimension:
    """单个体检维度的得分"""
    name:    str      # completeness / uniqueness / consistency / coverage
    label:   str      # 中文显示名
    score:   int      # 0-100
    weight:  int      # 0-100, 加权用
    detail:  str      # 一句话解释为什么这分

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HealthRisk:
    """单条风险提示"""
    level:            str             # high / medium / low
    code:             str             # null_high / id_dup / no_time_col 等(便于前端 i18n)
    message:          str             # 给用户看的中文话术
    affected_fields:  List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class HealthReport:
    """整张数据健康报告(单数据集)"""
    score:         int                       # 0-100 总分
    dimensions:    List[HealthDimension]
    risks:         List[HealthRisk]
    n_rows:        int
    n_cols:        int
    field_summary: List[Dict[str, Any]] = field(default_factory=list)
    # field_summary: [{name, role, role_label, null_ratio, n_unique, role_confidence}]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score":         self.score,
            "dimensions":    [d.to_dict() for d in self.dimensions],
            "risks":         [r.to_dict() for r in self.risks],
            "n_rows":        self.n_rows,
            "n_cols":        self.n_cols,
            "field_summary": self.field_summary,
        }


_ROLE_LABELS = {
    "time":    "时间",
    "id":      "标识",
    "metric":  "指标",
    "dim":     "维度",
    "text":    "文本",
    "unknown": "未知",
}


def _role_confidence(role: str, meta: Dict[str, Any]) -> int:
    """估算字段角色识别置信度(0-100),供 UI 展示"""
    if role == "unknown":
        return 30
    if role == "time":
        # 时间类列名命中且 datetime 解析成功 → 95;只靠提示词 → 80
        return 90
    if role == "id":
        pat = meta.get("id_pattern") or {}
        if pat.get("looks_like_id"):
            return 95
        return 75
    if role == "text":
        avg_len = meta.get("avg_len") or 0
        if avg_len >= 50:
            return 92
        return 78
    if role == "metric":
        return 85
    if role == "dim":
        return 70
    return 50


def compute_health_report(
    df: pd.DataFrame,
    expected_keys: Optional[List[str]] = None,
) -> HealthReport:
    """
    计算单数据集的健康报告。
    - df:           已加载的 DataFrame
    - expected_keys 可选,manifest 声明的关键字段(用于覆盖率维度)
    """
    n_rows = len(df)
    n_cols = len(df.columns)
    if n_rows == 0:
        # 极端兜底:空表给最低分
        return HealthReport(
            score=0,
            dimensions=[],
            risks=[HealthRisk(level="high", code="empty_data",
                              message="数据为空,无法体检")],
            n_rows=0, n_cols=n_cols,
        )

    roles = infer_field_roles(df)
    field_meta = roles.field_meta
    risks: List[HealthRisk] = []

    # ========= 维度 1:完整性(Completeness) =========
    # avg(1 - null_ratio) ∈ [0,1] → score ∈ [0,100]
    null_ratios = [m.get("null_ratio") or 0.0 for m in field_meta.values()]
    avg_null = sum(null_ratios) / max(len(null_ratios), 1)
    completeness_score = int(round((1.0 - avg_null) * 100))
    completeness_score = max(0, min(100, completeness_score))

    # 风险:单列 null 太多
    high_null_cols = [c for c, m in field_meta.items() if (m.get("null_ratio") or 0) >= 0.6]
    mid_null_cols  = [c for c, m in field_meta.items()
                      if 0.3 <= (m.get("null_ratio") or 0) < 0.6]
    if high_null_cols:
        risks.append(HealthRisk(
            level="high", code="null_high",
            message=f"{len(high_null_cols)} 个字段空值率超过 60%,建议确认数据来源是否正确",
            affected_fields=high_null_cols[:10],
        ))
    if mid_null_cols:
        risks.append(HealthRisk(
            level="medium", code="null_medium",
            message=f"{len(mid_null_cols)} 个字段空值率 30%-60%,部分分析可能受影响",
            affected_fields=mid_null_cols[:10],
        ))

    # ========= 维度 2:唯一性(Uniqueness) =========
    # 一张业务表通常只有一个真主键(unique_ratio 接近 1),其他 id 是外键(低基数)。
    # 算法:取所有 id 列中的最高唯一率作为"真主键"分数,避免被外键拖垮。
    # 例:销售表的 销售id(1.0) / 车型id(0.001) / 活动id(0.0002) → 取 1.0 算主键
    if roles.id_cols:
        id_uniq_pairs = [
            (col, field_meta.get(col, {}).get("unique_ratio") or 0)
            for col in roles.id_cols
        ]
        # 找最高唯一率的那一列当真主键
        primary_key_col, primary_key_uniq = max(id_uniq_pairs, key=lambda x: x[1])
        uniqueness_score = int(round(primary_key_uniq * 100))
        if primary_key_uniq < 0.95:
            risks.append(HealthRisk(
                level="high", code="id_dup",
                message=f"主键字段「{primary_key_col}」唯一率仅 {primary_key_uniq * 100:.0f}%,"
                        "可能影响跨源关联与去重,建议确认主键定义",
                affected_fields=[primary_key_col],
            ))
    else:
        primary_key_col = None
        primary_key_uniq = 0.0
        # 没识别到主键 → 60 分(扣分但不致命,可能是非业务表)
        uniqueness_score = 60
        risks.append(HealthRisk(
            level="medium", code="no_id_col",
            message="未识别到主键字段,跨源关联与去重能力受限",
        ))

    # ========= 维度 3:一致性(Consistency) =========
    # 字段角色识别成功率:1 - unknown_cols / n_cols
    n_unknown = len(roles.unknown_cols)
    unknown_ratio = n_unknown / max(n_cols, 1)
    consistency_score = int(round((1.0 - unknown_ratio) * 100))
    if n_unknown > 0 and unknown_ratio >= 0.3:
        risks.append(HealthRisk(
            level="low", code="role_unknown",
            message=f"{n_unknown} 个字段角色未能自动识别,可能影响 Agent 自动化分析",
            affected_fields=roles.unknown_cols[:10],
        ))

    # 没时间列 → 中等风险(影响时序分析)
    if not roles.time_cols:
        risks.append(HealthRisk(
            level="medium", code="no_time_col",
            message="未识别到时间字段,无法进行时序趋势分析",
        ))

    # ========= 维度 4:覆盖率(Coverage) =========
    # manifest 声明的关键字段是否齐全
    if expected_keys:
        actual = set(df.columns)
        missing = [k for k in expected_keys if k not in actual]
        coverage_score = int(round((1 - len(missing) / max(len(expected_keys), 1)) * 100))
        if missing:
            risks.append(HealthRisk(
                level="high" if len(missing) >= len(expected_keys) // 2 else "medium",
                code="missing_keys",
                message=f"manifest 声明的 {len(missing)} 个关键字段缺失,影响主线分析",
                affected_fields=missing,
            ))
    else:
        # 没有 expected_keys 信息 → 给 90 分(假设默认 OK,不严苛)
        coverage_score = 90

    # ========= 总分加权(各 25%) =========
    dimensions = [
        HealthDimension(
            name="completeness", label="完整性",
            score=completeness_score, weight=25,
            detail=f"平均空值率 {avg_null * 100:.1f}%",
        ),
        HealthDimension(
            name="uniqueness", label="唯一性",
            score=uniqueness_score, weight=25,
            detail=(f"主键 {primary_key_col} 唯一率 {uniqueness_score}%"
                    if primary_key_col else "未识别到主键字段"),
        ),
        HealthDimension(
            name="consistency", label="一致性",
            score=consistency_score, weight=25,
            detail=f"{n_cols - n_unknown}/{n_cols} 字段角色识别成功",
        ),
        HealthDimension(
            name="coverage", label="覆盖率",
            score=coverage_score, weight=25,
            detail=("manifest 关键字段齐全" if coverage_score >= 95
                    else f"{coverage_score}% manifest 关键字段就绪"),
        ),
    ]
    total_score = int(round(
        sum(d.score * d.weight for d in dimensions) / max(sum(d.weight for d in dimensions), 1)
    ))

    # 风险按 level 排序: high > medium > low
    level_order = {"high": 0, "medium": 1, "low": 2}
    risks.sort(key=lambda r: level_order.get(r.level, 3))

    # field_summary:给前端列表展示用,合并角色 + 元信息 + 置信度
    field_summary: List[Dict[str, Any]] = []
    for col in df.columns:
        meta = field_meta.get(col, {})
        role = meta.get("role", "unknown")
        field_summary.append({
            "name":            col,
            "role":            role,
            "role_label":      _ROLE_LABELS.get(role, "未知"),
            "role_confidence": _role_confidence(role, meta),
            "null_ratio":      round(meta.get("null_ratio") or 0, 4),
            "n_unique":        meta.get("n_unique") or 0,
            "unique_ratio":    round(meta.get("unique_ratio") or 0, 4),
            "dtype":           str(meta.get("dtype") or ""),
        })

    return HealthReport(
        score=total_score,
        dimensions=dimensions,
        risks=risks,
        n_rows=n_rows,
        n_cols=n_cols,
        field_summary=field_summary,
    )

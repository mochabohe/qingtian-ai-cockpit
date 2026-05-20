"""
VOC 主题聚类 ─ 智擎参谋的算法亮点环节

【流程】10 万条懂车帝评论 →
    1. 文本预处理(物理去重)
        - 去 nan / 长度 < 10 / 重复评论 / 通用问句("大家都怎么看")
    2. TF-IDF 字符级 n-gram 向量化(中文不依赖 jieba)
    3. KMeans 聚类(自动确定 n_clusters by silhouette)
    4. 每个簇提取代表性评论 + 关键词(主题命名锚点)
    5. 情感强度打分(种子词典 + 关键词加权,无外部模型依赖)
    6. 输出每簇:size / 代表词 / 代表评论 / 情感倾向

【设计取舍】
- 不依赖 BGE-zh / Sentence-BERT 模型(离线包大,现场隔离网风险)
- 不调 LLM 主题命名,直接用关键词;LLM 命名是可选 P1.5,通过 enable_llm_naming=True 开启
- 输出严格结构化 dict,可直接进 ANALYZER_PROMPT 与 PPT/视频
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import os
from sklearn.cluster import KMeans, MiniBatchKMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score


# 性能开关:大数据时 (默认 >= 5000 条) 自动切到 MiniBatchKMeans,内存降到 1/10、速度 5-10x
# 也可以 VOC_CLUSTER_BACKEND=minibatch 强制切;=kmeans 强制经典
_CLUSTER_BACKEND_OVERRIDE = os.getenv("VOC_CLUSTER_BACKEND", "auto").strip().lower()
_AUTO_MINIBATCH_THRESHOLD = int(os.getenv("VOC_AUTO_MINIBATCH_THRESHOLD", "5000"))
# 大数据时聚类样本上限,防止 10 万条 × 8000 维稀疏矩阵打爆内存(随机采样后再聚类)
_MAX_CLUSTER_SAMPLES = int(os.getenv("VOC_MAX_CLUSTER_SAMPLES", "8000"))


def _make_kmeans(n_clusters: int, n_samples: int, random_state: int = 42):
    """根据数据量自动挑 KMeans 实现:小数据用经典,大数据用 MiniBatch。"""
    use_minibatch = (
        _CLUSTER_BACKEND_OVERRIDE == "minibatch"
        or (_CLUSTER_BACKEND_OVERRIDE == "auto" and n_samples >= _AUTO_MINIBATCH_THRESHOLD)
    )
    if use_minibatch:
        return MiniBatchKMeans(
            n_clusters=n_clusters,
            random_state=random_state,
            batch_size=min(1024, max(256, n_samples // 20)),
            n_init=3,
        )
    # 经典 KMeans:n_init 从 10 降到 3(性能优化,效果差距小)
    return KMeans(n_clusters=n_clusters, random_state=random_state, n_init=3)

from . import dataset_loader

logger = logging.getLogger(__name__)


# ============================================================
# 情感词典(种子,可扩展)
# ============================================================

NEGATIVE_WORDS = {
    "差": 1.0, "烂": 1.2, "糟": 1.0, "贵": 0.7, "卡": 0.8, "慢": 0.7,
    "故障": 1.2, "失灵": 1.4, "失控": 1.5, "异响": 1.0, "漏": 0.9, "黑屏": 1.2,
    "死机": 1.2, "起火": 1.8, "断": 0.8, "坏": 1.0, "破": 0.7, "脏": 0.5,
    "不好用": 1.0, "不灵": 1.0, "不准": 0.8, "无语": 0.8, "失望": 1.2, "投诉": 1.3,
    "退订": 1.2, "退车": 1.4, "刹不住": 1.5, "顿挫": 0.9, "假": 0.8, "弱": 0.6,
    "差劲": 1.2, "毛病": 1.0, "问题": 0.6, "BUG": 1.0, "bug": 1.0, "颠": 0.6,
}

POSITIVE_WORDS = {
    "好": 0.7, "棒": 1.0, "舒服": 0.9, "省心": 1.0, "稳": 0.7, "快": 0.6,
    "强": 0.7, "推荐": 1.0, "值": 0.8, "满意": 1.0, "牛": 0.9, "爽": 0.9,
    "顺": 0.6, "丝滑": 1.0, "流畅": 0.9, "可靠": 1.0, "耐用": 0.9, "省油": 1.0,
    "省电": 1.0, "好开": 1.0, "好看": 0.7, "高级": 0.8, "豪华": 0.8, "智能": 0.7,
    "优秀": 1.0, "很赞": 1.1, "不错": 0.7, "性价比": 0.9,
}

# 通用水帖/无信息内容,直接过滤
WATER_PATTERNS = [
    r"^大家.{0,15}怎么看",
    r"^求.{0,8}建议",
    r"^[?？!！。.,，\s]+$",
    r"^顶$|^沙发$|^前排$|^好看$|^哈哈+$",
]
_WATER_RE = re.compile("|".join(WATER_PATTERNS))


# ============================================================
# 数据契约
# ============================================================

@dataclass
class ClusterDoc:
    cluster_id:        int
    size:              int
    keywords:          List[str]
    representative:    List[str]                  # 代表性评论(取距簇心最近的 N 条)
    sentiment_label:   str                        # negative / neutral / positive
    sentiment_score:   float                      # -1 ~ +1
    pos_hits:          int = 0
    neg_hits:          int = 0
    suggested_label:   Optional[str] = None       # LLM 命名结果,默认 None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VocClusterResult:
    n_input_total:    int       # 原始评论总数
    n_after_dedup:    int       # 物理去重后
    n_clustered:      int       # 实际进入聚类的(可能再次过滤)
    target_vehicle:   Optional[str]
    n_clusters:       int
    silhouette:       float
    clusters:         List[ClusterDoc] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "n_input_total":  self.n_input_total,
            "n_after_dedup":  self.n_after_dedup,
            "n_clustered":    self.n_clustered,
            "target_vehicle": self.target_vehicle,
            "n_clusters":     self.n_clusters,
            "silhouette":     round(self.silhouette, 4),
            "clusters":       [c.to_dict() for c in self.clusters],
        }


# ============================================================
# 1. 物理去重(预处理)
# ============================================================

def preprocess(df: pd.DataFrame, target_vehicle: Optional[str] = None,
               min_len: int = 10) -> pd.DataFrame:
    """
    物理去重:
    - 去 nan
    - 去空白 / 太短 (< min_len 字)
    - 去重复内容(content 完全相同)
    - 去水帖(命中正则)
    - 可选:按车系过滤

    ★ Schema 自适应: content / vehicle 列名通过 manifest 的 key_fields 别名解析,
      换数据集只改 manifest 即可。
    """
    fields = dataset_loader.resolve_fields_strict(
        "voc_dongchedi", ["content", "vehicle"], df=df,
    )
    content_col = fields["content"]
    vehicle_col = fields["vehicle"]

    df = df.copy()
    df = df[df[content_col].notna()]
    df[content_col] = df[content_col].astype(str).str.strip()
    df = df[df[content_col].str.len() >= min_len]
    df = df[~df[content_col].apply(lambda x: bool(_WATER_RE.search(x)))]
    df = df.drop_duplicates(subset=[content_col], keep="first")
    if target_vehicle:
        df = df[df[vehicle_col] == target_vehicle]
    # 内部规范化:把 content 列改名为 _content,后续聚类只取 _content,与具体中文列名解耦
    df = df.rename(columns={content_col: "_content"})
    return df.reset_index(drop=True)


# ============================================================
# 2. TF-IDF 向量化 + 自动 K 选择
# ============================================================

def vectorize(texts: List[str]) -> Tuple[Any, TfidfVectorizer]:
    vec = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 3),
        min_df=3,
        max_df=0.95,
        sublinear_tf=True,
        max_features=8000,
    )
    matrix = vec.fit_transform(texts)
    return matrix, vec


def select_k(matrix, k_candidates: List[int], random_state: int = 42) -> Tuple[int, float]:
    """对几个候选 k 跑 KMeans + silhouette,选最优。

    性能优化:
    - 大数据(n>=5000) 自动切 MiniBatchKMeans
    - 候选 k 精简由调用方控制(默认只跑 [8, 10] 两个,而不是 [6,8,10,12])
    - silhouette 采样保持 2000
    """
    best_k = k_candidates[0]
    best_score = -1.0
    n_samples = matrix.shape[0]
    for k in k_candidates:
        if k >= n_samples:
            continue
        try:
            km = _make_kmeans(n_clusters=k, n_samples=n_samples, random_state=random_state)
            labels = km.fit_predict(matrix)
            sample = min(2000, n_samples)
            score = silhouette_score(matrix, labels, sample_size=sample, random_state=random_state)
            if score > best_score:
                best_score = score
                best_k = k
        except Exception as e:
            logger.warning("k=%d silhouette 失败: %s", k, e)
    return best_k, best_score


# ============================================================
# 3. 关键词提取(每簇)
# ============================================================

# 中文虚词/高频功能字 — 用于过滤 TF-IDF char-ngram 中的虚词组合
STOP_CHARS = set(
    "的了是在也就都还可以么什样怎为而但和与或则于及对从把被让使其之乎者矣焉"
    "我你他她它我们你们他们这那这个那个一个有没没有不不是要会能可不可"
    "啊呀哦呢吧嘛哈哎喂吗吧呀哇嘿啦呐"
    "上下中前后左右内外里外间"
    "了，"  # 多字标点片段
)
STOP_FRAGMENTS = {
    "还是", "一下", "了，", "了。", "可以", "什么", "怎么", "这个", "那个",
    "我的", "你的", "他的", "我们", "你们", "他们", "为什么", "怎样",
    "已经", "现在", "如果", "因为", "所以", "但是", "不过", "然后",
    "买了", "去了", "来了", "好的", "不错", "应该", "可能", "或者",
    "知道", "感觉", "真的", "确实", "其实", "比较", "非常", "特别",
    "好，", "，我", "，你", "，他", "，但", "，那", "，然", "，不",
    "0公", "公里", "00", "000", "30", "50",  # 纯数字噪声
    # —— 单字动词 / 短语补充(过滤 "要买/国产/开的/提车/置换/改款/新款/老款" 之类用户行为词)
    "要买", "想买", "提车", "置换", "改款", "新款", "老款", "试驾",
    "开的", "买的", "用的", "看的", "选的", "选车", "看车", "买车",
    "比亚", "亚迪",  # "比亚迪" 三字被切成的二字 ngram(单独出现没意义)
    "国产", "进口",  # 单一标签词,几乎所有评论都会出现
    # —— 5/10 演示前观察到的高频低信息泛词(车圈通用,不指向具体痛点)
    "车主", "估计", "喜欢", "受不", "觉得", "认为", "希望", "期待",
    "这种", "那种", "这样", "那样", "这么", "那么", "一些", "几个",
    "原厂", "实线", "变道", "倒车", "加个", "个月",
    "0寸", "1寸", "2寸",  # "20寸/19寸" 切出的残片
    "不买",  # 决策动作,不指向产品具体特性
    # —— 颜色名残片(单独出现没信息量,谁都能买什么色)
    "星空", "空灰", "星空灰", "珍珠", "雅典",
    # —— 品牌名残片
    "大众", "丰田", "本田", "马斯", "斯克", "马斯克",
}

# —— 业务关键词白名单(命中则 TF-IDF 权重 ×3,优先冒泡到 top n)
# 这些是"用户在抱怨/讨论的具体产品特性",出现在 ngram 里就该被优先输出
BOOST_KEYWORDS = {
    # 动力 / 续航 / 充电
    "续航", "虚标", "缩水", "电池", "充电", "快充", "慢充", "加速", "顿挫", "动能", "回收",
    # 制动 / 底盘 / NVH
    "刹车", "异响", "抖动", "顿挫", "悬挂", "底盘", "噪音", "风噪", "胎噪", "共振",
    # 智能 / 车机 / 屏幕
    "卡顿", "黑屏", "死机", "OTA", "车机", "中控", "屏幕", "导航", "语音", "蓝牙",
    "辅助", "智驾", "自动", "驾驶", "雷达", "摄像", "盲区", "并线",
    # 内饰 / 做工 / 用料
    "做工", "异味", "漏水", "漏风", "缝隙", "皮革", "座椅", "方向盘", "内饰", "顶棚",
    "按键", "门把手", "后备", "天窗",
    # 售后 / 服务
    "售后", "保养", "维修", "保修", "三包", "门店", "客服", "服务", "等待",
    # 价格 / 保值
    "降价", "提价", "保值", "二手", "价格", "优惠", "金融",
    # 外观 / 漆面 / 轮毂
    "漆面", "掉漆", "划痕", "轮毂", "轮胎",
    # 空间
    "后排", "腿部", "头部", "储物", "后备箱",
    # 通用产品质量动词
    "故障", "毛病", "问题", "缺陷", "投诉",
}


def _is_meaningful_term(term: str) -> bool:
    """判断 char_wb n-gram 是否值得保留(剔除虚词/标点/数字片段)"""
    if not term or len(term.strip()) < 2:
        return False
    t = term.strip()
    # 黑名单直接 reject
    if t in STOP_FRAGMENTS:
        return False
    # 含逗号/句号/问号等标点直接 reject(常见的"了，""，我"等)
    _punct = "，。?！!？:：;；、…“”‘’[]【】（）()<>《》\""
    if any(c in t for c in _punct):
        return False
    # 全数字片段
    if t.replace(".", "").isdigit():
        return False
    # 含英文字母片段(关键词如 model 等保留,但碎片如 mo / od 过滤)
    if any('a' <= c.lower() <= 'z' for c in t) and len(t) < 4:
        return False
    # 全部由虚词字组成 → reject
    if all(c in STOP_CHARS for c in t):
        return False
    # 至少一半字符是实词字
    real = sum(1 for c in t if c not in STOP_CHARS and ('一' <= c <= '鿿' or c.isalpha()))
    if real / len(t) < 0.5:
        return False
    return True


def extract_keywords(matrix, vectorizer: TfidfVectorizer, labels: np.ndarray,
                     n_keywords: int = 8) -> Dict[int, List[str]]:
    """
    每个簇:取该簇文档的 TF-IDF 平均向量 → 业务关键词加权 boost → 过滤虚词后取 top n_keywords

    Boost 策略:命中 BOOST_KEYWORDS 的 ngram 权重 ×3,确保具体痛点词
    (续航/异响/卡顿/刹车...)优先冒泡到 top n,而不是被泛词淹没。
    """
    feature_names = vectorizer.get_feature_names_out()
    # 预算 boost 权重向量(对每个 feature term 是否包含业务关键词做一次性扫描)
    boost_weights = np.ones(len(feature_names), dtype=np.float32)
    for i, term in enumerate(feature_names):
        t = term.strip()
        if any(kw in t for kw in BOOST_KEYWORDS):
            boost_weights[i] = 3.0

    out: Dict[int, List[str]] = {}
    for cid in sorted(np.unique(labels)):
        mask = labels == cid
        cluster_mean = np.asarray(matrix[mask].mean(axis=0)).ravel()
        # 业务词 boost:命中白名单的 ngram 权重 ×3
        boosted = cluster_mean * boost_weights
        # 多取一些待过滤
        top_indices = boosted.argsort()[::-1][: n_keywords * 10]
        seen = set()
        kws: List[str] = []
        for idx in top_indices:
            term = feature_names[idx].strip()
            if term in seen:
                continue
            if not _is_meaningful_term(term):
                continue
            # 去重:已有关键词的子串不再加(避免"刹车" + "刹车异" + "车异响"重复)
            if any(term in k or k in term for k in kws):
                continue
            seen.add(term)
            kws.append(term)
            if len(kws) >= n_keywords:
                break
        out[int(cid)] = kws
    return out


# ============================================================
# 4. 代表性评论(距簇心最近)
# ============================================================

def representative_docs(matrix, labels: np.ndarray, kmeans: Any,
                        texts: List[str], top_n: int = 10, max_chars: int = 100) -> Dict[int, List[str]]:
    """kmeans: KMeans 或 MiniBatchKMeans,二者都有 .cluster_centers_"""
    out: Dict[int, List[str]] = {}
    centers = kmeans.cluster_centers_
    for cid in sorted(np.unique(labels)):
        idx_in_cluster = np.where(labels == cid)[0]
        if len(idx_in_cluster) == 0:
            out[int(cid)] = []
            continue
        # 距簇心余弦相似度(等价于点积,因为 TF-IDF 已 L2 归一化)
        sub = matrix[idx_in_cluster]
        sims = sub.dot(centers[cid])
        if hasattr(sims, "toarray"):
            sims = np.asarray(sims.toarray()).ravel()
        sims = np.asarray(sims).ravel()
        top = sims.argsort()[::-1][:top_n]
        reps = []
        for j in top:
            t = texts[idx_in_cluster[j]]
            t = t.strip().replace("\n", " ")
            if len(t) > max_chars:
                t = t[:max_chars] + "…"
            reps.append(t)
        out[int(cid)] = reps
    return out


# ============================================================
# 5. 情感强度打分
# ============================================================

def sentiment_score(text: str) -> Tuple[float, int, int]:
    """
    返回 (score, pos_hits, neg_hits)
    score ∈ [-1, +1],基于词典加权命中数
    """
    pos = neg = 0.0
    pos_hits = neg_hits = 0
    for w, weight in POSITIVE_WORDS.items():
        c = text.count(w)
        if c:
            pos += weight * c
            pos_hits += c
    for w, weight in NEGATIVE_WORDS.items():
        c = text.count(w)
        if c:
            neg += weight * c
            neg_hits += c
    total = pos + neg
    if total == 0:
        return 0.0, 0, 0
    return (pos - neg) / total, pos_hits, neg_hits


def cluster_sentiment(texts: List[str], labels: np.ndarray) -> Dict[int, Dict[str, Any]]:
    out: Dict[int, Dict[str, Any]] = {}
    for cid in sorted(np.unique(labels)):
        idx = np.where(labels == cid)[0]
        scores = []
        pos_total = neg_total = 0
        for j in idx:
            s, p, n = sentiment_score(texts[j])
            scores.append(s)
            pos_total += p
            neg_total += n
        avg = float(np.mean(scores)) if scores else 0.0
        # 阈值放宽到 ±0.05,VOC 大量评论本身偏中性,过严会全是 neutral
        if avg <= -0.05:
            label = "negative"
        elif avg >= 0.05:
            label = "positive"
        else:
            label = "neutral"
        out[int(cid)] = {
            "score":       round(avg, 3),
            "label":       label,
            "pos_hits":    pos_total,
            "neg_hits":    neg_total,
        }
    return out


# ============================================================
# 顶层入口
# ============================================================

def cluster_voc(target_vehicle: Optional[str] = "Model Y",
                k_candidates: Optional[List[int]] = None,
                min_text_len: int = 10) -> VocClusterResult:
    """端到端跑一次 VOC 聚类,返回结构化结果"""
    df_raw = dataset_loader.load_csv("voc_dongchedi")
    n_input_total = len(df_raw)

    df = preprocess(df_raw, target_vehicle=target_vehicle, min_len=min_text_len)
    n_after_dedup = len(df)
    if n_after_dedup < 10:
        logger.warning("VOC 聚类样本太少: %d", n_after_dedup)
        return VocClusterResult(
            n_input_total=n_input_total,
            n_after_dedup=n_after_dedup,
            n_clustered=0,
            target_vehicle=target_vehicle,
            n_clusters=0,
            silhouette=0.0,
            clusters=[],
        )

    # 大数据采样:超过 _MAX_CLUSTER_SAMPLES 条则随机抽样,防止内存爆 + 加速
    # 10万条 × 8000 维稀疏矩阵约占 60GB,采样到 8000 后降到 ~50MB
    if n_after_dedup > _MAX_CLUSTER_SAMPLES:
        logger.info("VOC 样本 %d 超过 %d,随机采样到 %d 后聚类",
                    n_after_dedup, _MAX_CLUSTER_SAMPLES, _MAX_CLUSTER_SAMPLES)
        df = df.sample(n=_MAX_CLUSTER_SAMPLES, random_state=42).reset_index(drop=True)

    # preprocess 已把 content 列规范化为 _content,与原始中文列名解耦
    texts = df["_content"].tolist()
    matrix, vec = vectorize(texts)
    n_samples = matrix.shape[0]

    if k_candidates is None:
        # 数据量自适应,候选数量精简(从 5-6 个降到 3 个,加速 50%)
        if n_samples < 60:
            k_candidates = [3, 4, 5]
        elif n_samples < 200:
            k_candidates = [5, 7, 9]
        else:
            k_candidates = [6, 8, 10]

    best_k, best_sil = select_k(matrix, k_candidates)

    # 最终聚类用同一个工厂方法(大数据自动 MiniBatchKMeans)
    km = _make_kmeans(n_clusters=best_k, n_samples=n_samples, random_state=42)
    labels = km.fit_predict(matrix)

    keywords = extract_keywords(matrix, vec, labels, n_keywords=8)
    reps = representative_docs(matrix, labels, km, texts, top_n=10)
    sent = cluster_sentiment(texts, labels)

    clusters: List[ClusterDoc] = []
    for cid in sorted(np.unique(labels)):
        cid_int = int(cid)
        clusters.append(ClusterDoc(
            cluster_id      = cid_int,
            size            = int((labels == cid_int).sum()),
            keywords        = keywords.get(cid_int, []),
            representative  = reps.get(cid_int, []),
            sentiment_label = sent[cid_int]["label"],
            sentiment_score = sent[cid_int]["score"],
            pos_hits        = sent[cid_int]["pos_hits"],
            neg_hits        = sent[cid_int]["neg_hits"],
        ))
    # 按 size 降序
    clusters.sort(key=lambda c: c.size, reverse=True)

    return VocClusterResult(
        n_input_total = n_input_total,
        n_after_dedup = n_after_dedup,
        n_clustered   = n_after_dedup,
        target_vehicle= target_vehicle,
        n_clusters    = best_k,
        silhouette    = best_sil,
        clusters      = clusters,
    )


def top_pain_points(result: VocClusterResult, top_n: int = 5) -> List[ClusterDoc]:
    """挑负面情感最强 + 规模较大的簇,作为 TOP 痛点。

    设计取舍:
    - 优先 sentiment_label == 'negative' 的簇
    - 若全部为 positive/neutral(典型场景:中文情感词典命中偏正面) → 退而求其次,
      取 sentiment_score **最低**(相对最不正面)的 top_n 个簇,内部再按 size 降序展示
    - **不要**用 neg_hits 兜底——绝对值大不代表负面,大簇通常 pos_hits 和 neg_hits 都多
    - **不要**最终再按 size 重排——那会让 pain/praise 退化成同一组(size 主导)
    """
    neg = [c for c in result.clusters if c.sentiment_label == "negative"]
    if neg:
        # 真有负面簇:按 size 降 + 情感越负越靠前
        return sorted(neg, key=lambda c: (-c.size, c.sentiment_score))[:top_n]
    # 兜底:取相对最不正面的 top_n,内部按 size 降序便于展示
    fallback = sorted(result.clusters, key=lambda c: (c.sentiment_score, -c.size))[:top_n]
    return sorted(fallback, key=lambda c: -c.size)


def top_praise_points(
    result: VocClusterResult,
    top_n: int = 5,
    exclude_cluster_ids: Optional[set] = None,
) -> List[ClusterDoc]:
    """挑正面情感最强 + 规模较大的簇,作为 TOP 卖点。

    Args:
        exclude_cluster_ids: 强不重叠 — voc_brief 调用时传入痛点已用的 cluster_id 集合,
            避免痛点和卖点列表展示成完全相同(典型:全正面情感时,sentiment 排序后仍可能
            和痛点 fallback 选到重叠的中段簇)
    """
    exclude = set(exclude_cluster_ids or [])
    candidates = [c for c in result.clusters if c.cluster_id not in exclude]
    pos = [c for c in candidates if c.sentiment_label == "positive"]
    if pos:
        return sorted(pos, key=lambda c: (-c.size, -c.sentiment_score))[:top_n]
    # 兜底:取相对最正面的 top_n,内部按 size 降序便于展示
    fallback = sorted(candidates, key=lambda c: (-c.sentiment_score, -c.size))[:top_n]
    return sorted(fallback, key=lambda c: -c.size)

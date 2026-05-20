"""
RAGStore ─ 故障案例向量检索

设计取舍：
- 主路径用 sklearn TfidfVectorizer + cosine_similarity（零新依赖，已有 scikit-learn）
- 中文不分词，用 char_wb + ngram (2,3) 字符级 n-gram，对 384 条级别的故障案例库足够
- 留 IRagBackend 抽象，后续可一行替换为 BGE-zh + FAISS

API：
    store = get_default_store()              # 默认加载 quality_fault_cases 全表(跨 sheet 合并)
    store.search("座椅无法调节", top_k=3)     # → [{score, fault_id, topic, root_cause, ...}]
    store.rebuild()                          # 强制重建索引

现场演示适配:
- 新数据 quality_fault_cases.xlsx 共 13 个故障案例 sheet(eπ007/AX7/E70/eπ008/...) 共 ~430+ 案例
- build() 改为读取所有故障案例 sheet 合并,RAG 知识库相比阉割版扩张 10 倍
- eπ007 sheet 缺失「故障编号」列 → 用 "{车型}-{行号}" 自动兜底
- 「分类数据」等非案例 sheet(列结构不匹配) 自动跳过
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, asdict
from functools import lru_cache
from typing import Any, Dict, List, Optional

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from . import dataset_loader

logger = logging.getLogger(__name__)


# ==== 数据契约 ====

@dataclass
class FaultCaseDoc:
    """单个故障案例的检索结果"""
    fault_id:       str
    topic:          str
    root_cause:     str
    main_part:      str
    repair_method:  str
    symptoms:       str
    system:         str
    dtc_list:       str
    source_sheet:   str = ""   # 现场演示新增:案例来源 sheet(如 "eπ007故障案例"),便于演示时溯源
    score:          float = 0.0  # 检索时填充

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# 故障案例 sheet 必须含有的最小列集合(用于过滤掉「分类数据」等非案例 sheet)
_REQUIRED_FAULT_CASE_COLS = {"故障主题", "故障原因", "维修方法"}


# ==== TF-IDF 后端 ====

class TfidfRagStore:
    """
    基于 TF-IDF 字符级 n-gram 的轻量向量库。
    每条文档的检索文本 = 故障主题 + 故障原因 + 故障现象 + 维修方法（高权重字段拼接）
    """

    def __init__(self, dataset_key: str = "quality_fault_cases"):
        self.dataset_key = dataset_key
        self._docs:       List[FaultCaseDoc] = []
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._matrix = None
        self._lock = threading.Lock()

    @property
    def n_docs(self) -> int:
        return len(self._docs)

    def build(self) -> None:
        """
        从 manifest 中的故障案例数据集构建索引。
        现场演示改为加载 xlsx 全部 sheet 并合并,跳过列不匹配的非案例 sheet。
        """
        # sheet=None 返回 {sheet_name: df},一次性读全部
        all_sheets = dataset_loader.load_excel(self.dataset_key, sheet=None)
        if not isinstance(all_sheets, dict):
            # 兜底:意外只拿到单个 df 时按老逻辑处理
            all_sheets = {"_default_": all_sheets}

        docs: List[FaultCaseDoc] = []
        texts: List[str] = []
        skipped: List[str] = []

        for sheet_name, df in all_sheets.items():
            if not _REQUIRED_FAULT_CASE_COLS.issubset(set(df.columns)):
                skipped.append(sheet_name)
                continue
            for idx, row in df.iterrows():
                # 故障编号缺失时用 sheet+行号兜底,保证 fault_id 唯一
                raw_fault_id = _safe_str(row.get("故障编号"))
                if not raw_fault_id:
                    raw_fault_id = f"{sheet_name}-{idx + 1:03d}"
                doc = FaultCaseDoc(
                    fault_id      = raw_fault_id,
                    topic         = _safe_str(row.get("故障主题")),
                    root_cause    = _safe_str(row.get("故障原因")),
                    main_part     = _safe_str(row.get("主原因件")),
                    repair_method = _safe_str(row.get("维修方法")),
                    symptoms      = _safe_str(row.get("故障现象")),
                    system        = _safe_str(row.get("系统")),
                    dtc_list      = _safe_str(row.get("DTC列表")),
                    source_sheet  = sheet_name,
                )
                docs.append(doc)
                texts.append(_compose_index_text(doc))

        if not docs:
            raise RuntimeError(
                f"RAG 构建失败:{self.dataset_key} 全部 sheet 都不含故障案例必需列 "
                f"{_REQUIRED_FAULT_CASE_COLS}"
            )

        # 字符级 n-gram (2,3),min_df=1 避免单条目报错
        vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 3),
            min_df=1,
            max_df=1.0,
            sublinear_tf=True,
        )
        matrix = vectorizer.fit_transform(texts)

        with self._lock:
            self._docs = docs
            self._vectorizer = vectorizer
            self._matrix = matrix

        logger.info(
            "[RAG] 索引完成: docs=%d (来自 %d 个 sheet),跳过 %d 个非案例 sheet=%s, n_features=%d",
            len(docs), len(all_sheets) - len(skipped), len(skipped), skipped, matrix.shape[1],
        )

    def rebuild(self) -> None:
        """强制重建索引(数据更新后调用)"""
        with self._lock:
            self._docs = []
            self._vectorizer = None
            self._matrix = None
        self.build()

    def _ensure_built(self) -> None:
        if self._vectorizer is None:
            self.build()

    def search(self, query: str, top_k: int = 3, min_score: float = 0.0) -> List[Dict[str, Any]]:
        """
        检索 query 最相关的 top_k 条故障案例。
        返回按 score 降序,score 是 cosine 相似度(0~1)。
        """
        self._ensure_built()
        if not query or not query.strip():
            return []
        q_vec = self._vectorizer.transform([query])
        sims = cosine_similarity(q_vec, self._matrix)[0]
        # 取 top_k 索引
        order = sims.argsort()[::-1][:top_k]
        out: List[Dict[str, Any]] = []
        for idx in order:
            score = float(sims[idx])
            if score < min_score:
                continue
            doc = self._docs[idx]
            doc_copy = FaultCaseDoc(**{**asdict(doc), "score": round(score, 4)})
            out.append(doc_copy.to_dict())
        return out

    def list_systems(self) -> Dict[str, int]:
        """返回故障案例的"系统"字段分布(用于前端做分组浏览)"""
        self._ensure_built()
        counter: Dict[str, int] = {}
        for d in self._docs:
            k = d.system or "未分类"
            counter[k] = counter.get(k, 0) + 1
        return counter


# ==== 工具函数 ====

def _safe_str(v: Any) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


def _compose_index_text(doc: FaultCaseDoc) -> str:
    """
    构造检索文本：故障主题(权重高,重复 2 次) + 故障现象 + 故障原因 + 维修方法
    复用业务上的"故障现象/根因/修法"三件套,模拟用户提问场景
    """
    parts = [
        doc.topic, doc.topic,           # 主题加权
        doc.symptoms,
        doc.root_cause,
        doc.repair_method,
        doc.main_part,
        doc.system,
    ]
    return " ".join(p for p in parts if p)


# ==== 全局单例 ====

@lru_cache(maxsize=4)
def get_store(dataset_key: str = "quality_fault_cases") -> TfidfRagStore:
    """获取全局共享的 RAGStore 实例(按 dataset_key 缓存)"""
    s = TfidfRagStore(dataset_key=dataset_key)
    s.build()
    return s


def get_default_store() -> TfidfRagStore:
    """主线默认 store(故障案例)"""
    return get_store("quality_fault_cases")

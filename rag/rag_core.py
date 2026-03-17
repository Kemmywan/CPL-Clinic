"""
VectorMemory — 基于 FAISS 的 [病历, 诊断] 二元组记忆存储与检索

存储位置：
  - memory/pairs.jsonl   每行一条 {"record": "...", "diagnostic": "..."}
  - memory/vector.faiss   FAISS 向量索引

功能：
  - add_pair()      添加单条 (病历, 诊断) 二元组
  - batch_import()  批量导入
  - search()        基于文本相似度检索相关病例
  - save_index()    持久化 FAISS 索引
"""

import os
import json
from typing import List, Dict

import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

_RAG_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_RAG_DIR)
_MEMORY_DIR = os.path.join(_PROJECT_ROOT, "memory")


class VectorMemory:
    def __init__(
        self,
        dim: int = 768,
        index_file: str = "",
        pair_file: str = "",
        emb_model_name: str = "shibing624/text2vec-base-chinese",
    ):
        self.dim = dim
        self.index_file = index_file or os.path.join(_MEMORY_DIR, "vector.faiss")
        self.pair_file = pair_file or os.path.join(_MEMORY_DIR, "pairs.jsonl")
        self.emb_model = SentenceTransformer(emb_model_name)
        self.pairs: List[Dict] = []
        self.index: faiss.IndexFlatL2 = faiss.IndexFlatL2(self.dim)
        self._load()

    # -------------------- 初始化 --------------------

    def _load(self):
        os.makedirs(os.path.dirname(self.index_file), exist_ok=True)

        if os.path.exists(self.pair_file):
            with open(self.pair_file, "r", encoding="utf-8") as f:
                self.pairs = [json.loads(line) for line in f if line.strip()]
        else:
            self.pairs = []

        if os.path.exists(self.index_file):
            self.index = faiss.read_index(self.index_file)
        else:
            self.index = faiss.IndexFlatL2(self.dim)

    # -------------------- 编码 --------------------

    @staticmethod
    def _pair_to_text(pair: Dict) -> str:
        """将二元组拼成编码用文本"""
        return f"病历: {pair.get('record', '')}\n诊断: {pair.get('diagnostic', '')}"

    def _encode_texts(self, texts: List[str]) -> np.ndarray:
        emb = self.emb_model.encode(texts)
        emb = np.array(emb, dtype="float32")
        if emb.ndim == 1:
            emb = emb.reshape(1, -1)
        return np.ascontiguousarray(emb)

    # -------------------- 写入 --------------------

    def add_pair(self, record: str, diagnostic: str):
        """添加一条 (病历, 诊断) 二元组"""
        pair = {"record": record, "diagnostic": diagnostic}
        emb = self._encode_texts([self._pair_to_text(pair)])
        self.index.add(emb)
        self.pairs.append(pair)
        with open(self.pair_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    def batch_import(self, pairs: List[Dict]):
        """批量导入 [{"record": ..., "diagnostic": ...}, ...]"""
        if not pairs:
            return
        texts = [self._pair_to_text(p) for p in pairs]
        embs = self._encode_texts(texts)
        self.index.add(embs)
        self.pairs.extend(pairs)
        with open(self.pair_file, "a", encoding="utf-8") as f:
            for p in pairs:
                f.write(json.dumps(p, ensure_ascii=False) + "\n")

    def save_index(self):
        """持久化 FAISS 索引到磁盘"""
        faiss.write_index(self.index, self.index_file)

    # -------------------- 检索 --------------------

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        检索与 query 最相似的病例二元组

        Returns:
            list of {"record": ..., "diagnostic": ..., "score": float}
        """
        if self.index.ntotal == 0:
            return []

        q_emb = self._encode_texts([query])
        actual_k = min(top_k, self.index.ntotal)
        D, I = self.index.search(q_emb, actual_k)

        results = []
        for rank, idx in enumerate(I[0]):
            if 0 <= idx < len(self.pairs):
                hit = dict(self.pairs[idx])
                hit["score"] = float(D[0][rank])
                results.append(hit)
        return results

    # -------------------- 工具方法 --------------------

    def __len__(self) -> int:
        return len(self.pairs)

    def get_pair(self, idx: int) -> Dict:
        if 0 <= idx < len(self.pairs):
            return self.pairs[idx]
        raise IndexError(f"No pair at index {idx}")
    
    
        



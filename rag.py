"""RAG 存储层：LangChain vectorstores + TF-IDF 回退"""

import json
import math
import os
from typing import Optional

from langchain_core.documents import Document
from langchain_core.vectorstores import VectorStore as LCVectorStore


# ============================================================
# TF-IDF 向量存储（LangChain VectorStore ABC 实现）
# ============================================================

def _tokenize(text: str) -> list:
    tokens = []
    english_word = ""
    for ch in text:
        if "一" <= ch <= "鿿":
            if english_word:
                tokens.append(english_word.lower())
                english_word = ""
            tokens.append(ch)
        elif ch.isalpha():
            english_word += ch
        else:
            if english_word:
                tokens.append(english_word.lower())
                english_word = ""
    if english_word:
        tokens.append(english_word.lower())
    bigrams = [tokens[i] + tokens[i + 1] for i in range(len(tokens) - 1)]
    return tokens + bigrams


def _compute_idf(all_token_lists: list) -> dict:
    n_docs = len(all_token_lists)
    doc_freq = {}
    for tokens in all_token_lists:
        for t in set(tokens):
            doc_freq[t] = doc_freq.get(t, 0) + 1
    return {t: math.log(n_docs / (1 + df)) for t, df in doc_freq.items()}


def _tfidf_vector(tokens: list, idf: dict) -> dict:
    tf = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    max_tf = max(tf.values()) if tf else 1
    return {t: (0.5 + 0.5 * count / max_tf) * idf.get(t, 0)
            for t, count in tf.items()}


def _cosine_sparse(a: dict, b: dict) -> float:
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in set(a) & set(b))
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class TfidfVectorStore(LCVectorStore):
    """TF-IDF 向量存储，兼容 LangChain VectorStore 接口"""

    def __init__(self):
        self._documents: list[Document] = []
        self._vectors: list[dict] = []
        self._idf: dict = {}

    def add_texts(self, texts: list, metadatas: list = None, **kwargs) -> list:
        metadatas = metadatas or [{}] * len(texts)
        ids = []
        for text, meta in zip(texts, metadatas):
            doc = Document(page_content=text, metadata=meta)
            self._documents.append(doc)
            ids.append(str(len(self._documents) - 1))
        # 重建索引
        all_tokens = [_tokenize(d.page_content) for d in self._documents]
        if all_tokens:
            self._idf = _compute_idf(all_tokens)
            self._vectors = [_tfidf_vector(tokens, self._idf) for tokens in all_tokens]
        return ids

    def similarity_search_with_score(self, query: str, k: int = 4, **kwargs):
        if not self._vectors:
            self._build_index()
        if not self._vectors:
            return []

        q_tokens = _tokenize(query)
        q_vec = _tfidf_vector(q_tokens, self._idf)
        scored = []
        for i, doc_vec in enumerate(self._vectors):
            sim = _cosine_sparse(q_vec, doc_vec)
            scored.append((i, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [(self._documents[i], s) for i, s in scored[:k]]

    def similarity_search(self, query: str, k: int = 4, **kwargs) -> list:
        results = self.similarity_search_with_score(query, k, **kwargs)
        return [doc for doc, _ in results]

    def _build_index(self):
        if not self._documents:
            return
        all_tokens = [_tokenize(d.page_content) for d in self._documents]
        self._idf = _compute_idf(all_tokens)
        self._vectors = [_tfidf_vector(tokens, self._idf) for tokens in all_tokens]

    @classmethod
    def from_texts(cls, texts: list, embedding=None, metadatas=None, **kwargs):
        instance = cls()
        instance.add_texts(texts, metadatas)
        return instance


# ============================================================
# RAGStore — 统一管理书籍和记忆的向量索引
# ============================================================

class RAGStore:
    """RAG 管理器：统一管理书籍和记忆两个 Collection"""

    def __init__(self, backend: str = "milvus", embeddings=None):
        self.backend = backend
        self.embeddings = embeddings
        self.book_store: Optional[LCVectorStore] = None
        self.memory_store: Optional[LCVectorStore] = None

    def index_books(self, books: list):
        texts = []
        metadatas = []
        for b in books:
            text = " ".join(str(v) for v in b.values())
            texts.append(text)
            metadatas.append({
                "title": b.get("title", ""),
                "author": b.get("author", ""),
                "publish_date": b.get("publish_date", ""),
                "category": b.get("category", ""),
            })

        if self.backend == "milvus" and self.embeddings:
            try:
                from langchain_community.vectorstores import Milvus
                self.book_store = Milvus.from_texts(
                    texts=texts,
                    metadatas=metadatas,
                    embedding=self.embeddings,
                    collection_name="books",
                    connection_args={
                        "host": os.environ.get("MILVUS_HOST", "127.0.0.1"),
                        "port": os.environ.get("MILVUS_PORT", "19530"),
                    },
                )
                return
            except Exception as e:
                print(f"  ⚠️ Milvus 不可用({e})，回退到 TF-IDF")
                self.backend = "tfidf"

        # TF-IDF 回退
        self.book_store = TfidfVectorStore.from_texts(texts, metadatas=metadatas)

    def index_memories(self, memories: list):
        texts = [str(m) if not isinstance(m, str) else m for m in memories]
        metadatas = [{"index": i} for i in range(len(texts))]

        if self.backend == "milvus" and self.embeddings:
            try:
                from langchain_community.vectorstores import Milvus
                self.memory_store = Milvus.from_texts(
                    texts=texts,
                    metadatas=metadatas,
                    embedding=self.embeddings,
                    collection_name="memories",
                    connection_args={
                        "host": os.environ.get("MILVUS_HOST", "127.0.0.1"),
                        "port": os.environ.get("MILVUS_PORT", "19530"),
                    },
                )
                return
            except Exception:
                self.backend = "tfidf"

        self.memory_store = TfidfVectorStore.from_texts(texts, metadatas=metadatas)

    def search_books(self, query: str, top_k: int = 3) -> list:
        if not self.book_store:
            return []
        try:
            results = self.book_store.similarity_search_with_score(query, k=top_k)
            return [(doc.page_content, score, doc.metadata) for doc, score in results]
        except Exception:
            return []

    def search_memories(self, query: str, top_k: int = 5) -> list:
        if not self.memory_store:
            return []
        try:
            results = self.memory_store.similarity_search_with_score(query, k=top_k)
            return [(doc.page_content, score, doc.metadata) for doc, score in results]
        except Exception:
            return []

    def add_memories(self, new_memories: list):
        if not new_memories:
            return
        if not self.memory_store:
            self.memory_store = TfidfVectorStore()
        texts = [str(m) if not isinstance(m, str) else m for m in new_memories]
        self.memory_store.add_texts(texts)


# ============================================================
# 全局 RAG 实例
# ============================================================

_rag_store: Optional[RAGStore] = None


def init_rag_store(memory_list: list = None) -> RAGStore:
    """初始化 RAG 存储（Milvus 优先，TF-IDF 回退）"""
    global _rag_store

    from tools.core import _load_books

    embeddings = None
    backend = "milvus"

    try:
        from langchain_openai import OpenAIEmbeddings
        embed_base_url = os.environ.get("EMBEDDINGS_BASE_URL")
        if embed_base_url:
            embeddings = OpenAIEmbeddings(
                model=os.environ.get("EMBEDDINGS_MODEL", "BAAI/bge-large-zh-v1.5"),
                openai_api_base=embed_base_url,
                openai_api_key=os.environ.get("EMBEDDINGS_API_KEY") or os.environ.get("OPENAI_API_KEY"),
            )
        else:
            embeddings = OpenAIEmbeddings(
                model="text-embedding-3-small",
                openai_api_base=os.environ.get("OPENAI_BASE_URL"),
                openai_api_key=os.environ.get("OPENAI_API_KEY"),
            )
    except Exception as e:
        print(f"  ⚠️ Embeddings 初始化失败({e})，使用 TF-IDF")
        backend = "tfidf"

    store = RAGStore(backend=backend, embeddings=embeddings)
    store.index_books(_load_books())
    if memory_list:
        store.index_memories(memory_list)

    _rag_store = store
    print(f"  🔍 RAG 系统已启动（{backend}）")
    return store


def get_rag_store() -> Optional[RAGStore]:
    return _rag_store

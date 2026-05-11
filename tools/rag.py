"""RAG 语义检索工具"""

from langchain_core.tools import tool


@tool
def search_books_semantic(query: str, top_k: int = 3) -> str:
    """用自然语言语义搜索书籍，支持模糊描述查询，如'关于宇宙文明兴衰的科幻'"""
    from rag import get_rag_store
    rag = get_rag_store()
    if rag and rag.book_store:
        try:
            results = rag.search_books(query, top_k)
            if results:
                lines = []
                for text, score, meta in results:
                    title = meta.get("title", "?")
                    author = meta.get("author", "?")
                    category = meta.get("category", "?")
                    lines.append(f"《{title}》- {author} ({category}, 相似度:{score:.2f})")
                return "\n".join(lines)
        except Exception:
            pass

    # 回退：TF-IDF
    from rag import TfidfVectorStore
    from tools.core import _load_books
    books = _load_books()
    if not books:
        return "书库为空"

    texts = [" ".join(str(v) for v in b.values()) for b in books]
    metadatas = [
        {"title": b.get("title", ""), "author": b.get("author", ""),
         "category": b.get("category", ""), "publish_date": b.get("publish_date", "")}
        for b in books
    ]
    store = TfidfVectorStore()
    store.add_texts(texts, metadatas)
    results = store.similarity_search_with_score(query, k=top_k)
    if not results:
        return "未找到语义匹配的书籍"
    lines = []
    for doc, score in results:
        meta = doc.metadata
        lines.append(f"《{meta.get('title', '?')}》- {meta.get('author', '?')} ({meta.get('category', '?')}, 相似度:{score:.2f})")
    return "\n".join(lines)


@tool
def rag_search(query: str, source: str = "books") -> str:
    """RAG 语义检索：从书籍库或记忆中检索相关信息，比关键词搜索更能理解语义"""
    from rag import get_rag_store
    rag = get_rag_store()
    if not rag:
        return "RAG 系统未初始化"
    if source == "memories":
        results = rag.search_memories(query, top_k=5)
    else:
        results = rag.search_books(query, top_k=3)
    if not results:
        return "未找到相关内容"
    return "\n".join(f"[相似度:{score:.2f}] {text}" for text, score, _ in results)


RAG_TOOLS = [search_books_semantic, rag_search]

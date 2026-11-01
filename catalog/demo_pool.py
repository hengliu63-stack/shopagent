"""本地 demo 商品池（Week1 兜底）：Channel3 API 不通时 demo 不翻车。

全部 USD 标价（Sandbox 对 USD 支持最完整）。每件商品：
    {"id", "name", "name_cn", "price", "currency", "rating", "sales", "url"}

Week2：catalog/search.py 优先调 Channel3，失败自动降级到这里。
"""
from __future__ import annotations

from typing import Any, Dict, List

POOL: List[Dict[str, Any]] = [
    {
        "id": "demo-book-001",
        "name": "Python Crash Course, 3rd Edition",
        "name_cn": "Python 编程：从入门到实践（第3版）",
        "price": 29.99, "currency": "USD",
        "rating": 4.8, "sales": 12000,
        "url": "https://example.com/demo/python-crash-course",
        "tags": ["python", "书", "book", "编程", "programming"],
    },
    {
        "id": "demo-book-002",
        "name": "Fluent Python, 2nd Edition",
        "name_cn": "流畅的 Python（第2版）",
        "price": 42.50, "currency": "USD",
        "rating": 4.9, "sales": 8000,
        "url": "https://example.com/demo/fluent-python",
        "tags": ["python", "书", "book", "编程", "进阶"],
    },
    {
        "id": "demo-book-003",
        "name": "Automate the Boring Stuff with Python, 2nd Edition",
        "name_cn": "Python 编程快速上手（第2版）",
        "price": 24.95, "currency": "USD",
        "rating": 4.7, "sales": 15000,
        "url": "https://example.com/demo/automate-boring",
        "tags": ["python", "书", "book", "自动化", "入门"],
    },
    {
        "id": "demo-mouse-001",
        "name": "Logitech MX Master 3S",
        "name_cn": "罗技 MX Master 3S 无线鼠标",
        "price": 99.99, "currency": "USD",
        "rating": 4.8, "sales": 20000,
        "url": "https://example.com/demo/mx-master-3s",
        "tags": ["鼠标", "mouse", "罗技", "logitech", "办公"],
    },
    {
        "id": "demo-mouse-002",
        "name": "Logitech M650 Wireless Mouse",
        "name_cn": "罗技 M650 无线鼠标",
        "price": 19.99, "currency": "USD",
        "rating": 4.6, "sales": 30000,
        "url": "https://example.com/demo/m650",
        "tags": ["鼠标", "mouse", "罗技", "logitech", "便宜"],
    },
    {
        "id": "demo-shoe-001",
        "name": "Nike Pegasus 41 Running Shoes",
        "name_cn": "耐克 Pegasus 41 跑鞋",
        "price": 89.99, "currency": "USD",
        "rating": 4.7, "sales": 9000,
        "url": "https://example.com/demo/pegasus-41",
        "tags": ["跑鞋", "鞋", "shoe", "nike", "耐克", "跑步"],
    },
    {
        "id": "demo-laptop-001",
        "name": "ThinkPad E14 Gen 5 (Ryzen 7, 16GB)",
        "name_cn": "ThinkPad E14 Gen5（R7/16G）",
        "price": 749.00, "currency": "USD",
        "rating": 4.6, "sales": 3000,
        "url": "https://example.com/demo/thinkpad-e14",
        "tags": ["笔记本", "电脑", "laptop", "thinkpad", "办公"],
    },
]


def _score(item: Dict[str, Any], keywords: List[str]) -> int:
    parts = [
        item.get("name", ""), item.get("name_cn", ""),
        *item.get("tags", []),
    ]
    hay = " ".join(parts).lower()
    words = [w for w in hay.split() if len(w) >= 2]
    s = 0
    for kw in keywords:
        k = kw.lower().strip()
        if not k:
            continue
        if k in hay:
            s += 1
        elif any(w in k for w in words):
            # 反向：商品词是 query 的子串（如"笔记本" ⊂ "的笔记本电脑"）
            s += 1
    return s


def search_pool(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """关键词模糊搜 demo 池，按匹配度 + 评分排序。"""
    keywords = [k for k in query.replace("，", " ").split() if k]
    if not keywords:
        keywords = [query]
    scored = [( _score(it, keywords), it["rating"], it) for it in POOL]
    scored = [s for s in scored if s[0] > 0]
    scored.sort(key=lambda s: (-s[0], -s[1]))
    return [it for _, _, it in scored[:limit]]

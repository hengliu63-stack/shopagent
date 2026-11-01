"""规则式意图解析（Week1）：中文购物指令 → 结构化意图。

    输入："帮我买一本 200 块以内的 Python 书"
    输出：{"query": "Python 书", "budget_max": 200.0, "currency": "CNY",
           "quantity": 1, "preferences": []}

Week2 换 LLM（OpenAI-compatible endpoint）时保持输出 schema 不变，
orchestrator 无需改动。

注意：PayPal Sandbox 演示用 USD；这里如实解析用户说的币种，
换算由 catalog/ 在 Week2 处理（demo 池本身就是 USD 标价）。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

_CN_NUM = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}

_VERBS = r"(?:帮我|请|麻烦)?(?:买|购买|下单|订|来|搞|整|拿下)"
_BUDGET_RES = [
    # "200块以内" / "200元以下" / "200块钱之内"
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:块钱|块|元|人民币|rmb|RMB)\s*(?:以内|以下|之内|之下)"), "CNY", 1),
    # "不超过200块" / "别超过200"
    (re.compile(r"(?:不超过|别超过|不要超过|最多)\s*(\d+(?:\.\d+)?)\s*(?:块钱|块|元|人民币|rmb|RMB)?"), "CNY", 1),
    # "$20以内" / "20美元以下" / "20刀以内"
    (re.compile(r"(?:\$|USD|usd)?\s*(\d+(?:\.\d+)?)\s*(?:美元|美金|刀)\s*(?:以内|以下|之内|之下)"), "USD", 1),
    (re.compile(r"\$\s*(\d+(?:\.\d+)?)\s*(?:以内|以下|之内|之下|左右)?"), "USD", 1),
    # "预算200" / "200预算"
    (re.compile(r"预算\s*(\d+(?:\.\d+)?)"), "CNY", 1),
]

_QTY_RES = [
    re.compile(r"([一二两三四五六七八九十]|\d+)\s*(?:本|个|台|件|只|部|套|双|箱|瓶)"),
]


def _parse_quantity(text: str) -> int:
    for rx in _QTY_RES:
        m = rx.search(text)
        if m:
            raw = m.group(1)
            if raw.isdigit():
                return int(raw)
            return _CN_NUM.get(raw, 1)
    return 1


def _parse_budget(text: str) -> tuple:
    for rx, currency, group in _BUDGET_RES:
        m = rx.search(text)
        if m:
            return float(m.group(group)), currency
    return None, "CNY"


# 偏好关键词 → 结构化偏好（Week2：catalog 排序据此调整策略）
_PREFERENCE_RES = [
    ("price_first", re.compile(r"便宜点?|性价比|省钱|实惠|划算")),
    ("rating_first", re.compile(r"评分高|口碑|质量好|品质")),
    ("sales_first", re.compile(r"销量|热门|卖得好|大家都在买")),
]


def _parse_preferences(text: str) -> List[str]:
    return [name for name, rx in _PREFERENCE_RES if rx.search(text)]


def _clean_query(text: str) -> str:
    q = text
    q = re.sub(_VERBS, "", q)                       # 去动词
    for rx, _, _ in _BUDGET_RES:                    # 去预算片段
        q = rx.sub("", q)
    for rx in _QTY_RES:                             # 去数量片段
        q = rx.sub("", q)
    for _, rx in _PREFERENCE_RES:                   # 去偏好词
        q = rx.sub("", q)
    q = re.sub(r"[，,。！!？?\s]+", " ", q).strip()   # 归一空白
    q = re.sub(r"^(?:一|一个)\s*", "", q)
    q = re.sub(r"^(?:[的个只台件本部套双]\s*)+", "", q)  # 残留量词/助词（可叠加，如"的鼠标"前的"个的"）
    return q


def parse(instruction: str) -> Dict[str, Any]:
    """解析单条购物指令。解析失败抛 ValueError（orchestrator 转 FAILED）。"""
    text = (instruction or "").strip()
    if not text:
        raise ValueError("空指令")

    budget_max, currency = _parse_budget(text)
    quantity = _parse_quantity(text)
    query = _clean_query(text)
    if not query:
        raise ValueError(f"没解析出商品关键词：{instruction!r}")

    return {
        "query": query,
        "budget_max": budget_max,   # None = 没说预算
        "currency": currency,
        "quantity": quantity,
        "preferences": _parse_preferences(text),
        "parser": "rule",
        "raw": instruction,
    }


# 简单自检：python -m nlu.parser
if __name__ == "__main__":
    cases = [
        "帮我买一本 200 块以内的 Python 书",
        "买两台 3000 元以下的笔记本电脑",
        "来一双不超过500块的跑鞋",
        "帮我买个 $20 以内的鼠标",
        "买一本 Python 书",
    ]
    for c in cases:
        print(c, "→", parse(c))

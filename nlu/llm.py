"""LLM 意图解析（Week2）：自然语言购物需求 → 结构化意图。

设计原则（免 key 可跑）：
- 有 LLM 端点配置（SHOPAGENT_LLM_API_KEY）→ 走 LLM，输出与规则版同一 schema；
- 没配置 / 端点报错 / 返回不是合法 JSON → 抛 LLMUnavailable，
  `parse_auto()` 自动降级到规则版 `nlu.parser.parse`，demo 永不翻车；
- transport 可注入：测试用桩 transport 离线验证 LLM 路径，不碰网络。

环境变量：
    SHOPAGENT_LLM_API_KEY    OpenAI-compatible 端点 key（缺失 = 不启用 LLM）
    SHOPAGENT_LLM_BASE_URL   默认 https://api.openai.com/v1
    SHOPAGENT_LLM_MODEL      默认 gpt-4o-mini

注意：这里的 key 是 LLM 端点的，与 PayPal 凭证无关、互不混用。
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Dict, List, Optional

from .parser import parse as rule_parse

SYSTEM_PROMPT = """你是一个购物助手的意图解析器。把用户的购物指令解析成 JSON，只输出 JSON，不要任何解释或代码围栏。

字段：
- query: 商品关键词（去掉动词、预算、数量、偏好词后的纯商品名，如 "Python 书"）
- budget_max: 预算上限数字；用户没提预算时为 null
- currency: "CNY" 或 "USD"（块/元/人民币→CNY；$/美元/刀→USD），没提预算时默认 "CNY"
- quantity: 购买数量整数，默认 1
- preferences: 偏好数组，可含 "price_first"（便宜/性价比优先）、"rating_first"（评分/口碑优先）、"sales_first"（销量/热门优先），没有则为 []

示例：
输入：帮我买一本 200 块以内的 Python 书
输出：{"query": "Python 书", "budget_max": 200, "currency": "CNY", "quantity": 1, "preferences": []}
输入：来两双便宜点的跑鞋，不超过 500 块
输出：{"query": "跑鞋", "budget_max": 500, "currency": "CNY", "quantity": 2, "preferences": ["price_first"]}
输入：买个 $20 以内的无线鼠标，要口碑好的
输出：{"query": "无线鼠标", "budget_max": 20, "currency": "USD", "quantity": 1, "preferences": ["rating_first"]}"""


class LLMUnavailable(RuntimeError):
    """LLM 未配置或调用失败：调用方应降级到规则解析。"""


def build_messages(instruction: str) -> List[Dict[str, str]]:
    """组装 chat messages（提示词本体，测试可直接断言）。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": instruction},
    ]


def parse_llm_response(text: str, raw_instruction: str) -> Dict[str, Any]:
    """解析 LLM 返回文本 → 意图 dict。非法输出抛 LLMUnavailable。"""
    if not text:
        raise LLMUnavailable("LLM 返回为空")
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMUnavailable(f"LLM 返回不是合法 JSON：{exc}") from exc
    if not isinstance(data, dict) or not str(data.get("query", "")).strip():
        raise LLMUnavailable("LLM 返回缺少 query")

    budget = data.get("budget_max")
    return {
        "query": str(data["query"]).strip(),
        "budget_max": float(budget) if budget is not None else None,
        "currency": str(data.get("currency") or "CNY").upper(),
        "quantity": int(data.get("quantity") or 1),
        "preferences": [str(p) for p in (data.get("preferences") or [])],
        "parser": "llm",
        "raw": raw_instruction,
    }


# transport 签名：messages -> 模型回复文本
Transport = Callable[[List[Dict[str, str]]], str]


def _openai_transport(api_key: str, base_url: str, model: str) -> Transport:
    """默认 transport：OpenAI-compatible chat completions（懒加载 SDK）。"""

    def call(messages: List[Dict[str, str]]) -> str:
        try:
            from openai import OpenAI  # 懒加载：没装/没 key 时不影响规则路径
        except ImportError as exc:
            raise LLMUnavailable("缺少 openai SDK") from exc
        client = OpenAI(api_key=api_key, base_url=base_url)
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or ""

    return call


class LLMParser:
    """LLM 意图解析器。无 key/transport 时 parse() 抛 LLMUnavailable。"""

    def __init__(
        self,
        transport: Optional[Transport] = None,
        environ: Optional[Dict[str, str]] = None,
    ) -> None:
        env = environ if environ is not None else os.environ
        self._transport = transport
        self._api_key = (env.get("SHOPAGENT_LLM_API_KEY") or "").strip()
        self._base_url = (
            env.get("SHOPAGENT_LLM_BASE_URL") or "https://api.openai.com/v1"
        ).strip()
        self._model = (env.get("SHOPAGENT_LLM_MODEL") or "gpt-4o-mini").strip()

    @property
    def configured(self) -> bool:
        return self._transport is not None or bool(self._api_key)

    def parse(self, instruction: str) -> Dict[str, Any]:
        text = (instruction or "").strip()
        if not text:
            raise ValueError("空指令")
        transport = self._transport
        if transport is None:
            if not self._api_key:
                raise LLMUnavailable(
                    "未配置 SHOPAGENT_LLM_API_KEY，LLM 解析不可用"
                )
            transport = _openai_transport(self._api_key, self._base_url, self._model)
        try:
            reply = transport(build_messages(text))
        except LLMUnavailable:
            raise
        except Exception as exc:  # 网络/端点任何错误都降级，不让 demo 翻车
            raise LLMUnavailable(f"LLM 调用失败：{exc}") from exc
        return parse_llm_response(reply, text)


def parse_auto(
    instruction: str,
    transport: Optional[Transport] = None,
    environ: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Week2 默认入口：LLM 可用则用 LLM，否则规则版。schema 与 parser.parse 一致。"""
    try:
        return LLMParser(transport=transport, environ=environ).parse(instruction)
    except LLMUnavailable:
        return rule_parse(instruction)

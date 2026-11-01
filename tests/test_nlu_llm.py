"""Week2 NLU：LLM 提示词/桩路径/降级 + 规则版偏好与 query 清洗。"""
import json

from nlu.llm import LLMParser, LLMUnavailable, build_messages, parse_auto
from nlu.parser import parse


def test_prompt_messages_shape():
    msgs = build_messages("帮我买一本 Python 书")
    assert msgs[0]["role"] == "system"
    assert "preferences" in msgs[0]["content"]
    assert msgs[1] == {"role": "user", "content": "帮我买一本 Python 书"}


def _stub_transport(reply: str):
    return lambda messages: reply


def test_llm_path_with_stub_transport():
    reply = json.dumps({
        "query": "无线鼠标", "budget_max": 20, "currency": "USD",
        "quantity": 1, "preferences": ["rating_first"],
    })
    r = LLMParser(transport=_stub_transport(reply), environ={}).parse(
        "买个 $20 以内的无线鼠标，要口碑好的")
    assert r["parser"] == "llm"
    assert r["query"] == "无线鼠标"
    assert r["budget_max"] == 20.0
    assert r["preferences"] == ["rating_first"]


def test_llm_unavailable_without_key():
    try:
        LLMParser(environ={}).parse("买一本 Python 书")
    except LLMUnavailable:
        return
    raise AssertionError("无 key 无 transport 应抛 LLMUnavailable")


def test_parse_auto_falls_back_on_garbage_llm_output():
    r = parse_auto("帮我买一本 200 块以内的 Python 书",
                   transport=_stub_transport("我不是 JSON"), environ={})
    assert r["parser"] == "rule"
    assert r["budget_max"] == 200.0


def test_parse_auto_falls_back_on_transport_error():
    def boom(messages):
        raise ConnectionError("endpoint down")

    r = parse_auto("买一本 Python 书", transport=boom, environ={})
    assert r["parser"] == "rule"
    assert "Python" in r["query"]


def test_rule_preferences_and_quantity():
    r = parse("来两双便宜点的跑鞋")
    assert r["quantity"] == 2
    assert r["preferences"] == ["price_first"]
    assert r["query"] == "跑鞋"


def test_rule_query_no_leading_particle():
    """Week1 遗留瑕疵：'帮我买个 $20 以内的鼠标' 曾解析出 query='的鼠标'。"""
    r = parse("帮我买个 $20 以内的鼠标")
    assert r["query"] == "鼠标"

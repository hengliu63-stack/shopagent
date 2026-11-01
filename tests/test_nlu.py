"""NLU 规则解析测试：python -m pytest tests/ -v"""
from nlu.parser import parse


def test_book_with_budget():
    r = parse("帮我买一本 200 块以内的 Python 书")
    assert r["budget_max"] == 200.0
    assert r["currency"] == "CNY"
    assert r["quantity"] == 1
    assert "Python" in r["query"]


def test_laptop_cn_quantity():
    r = parse("买两台 3000 元以下的笔记本电脑")
    assert r["quantity"] == 2
    assert r["budget_max"] == 3000.0
    assert "笔记本" in r["query"]


def test_no_budget():
    r = parse("帮我买一本 Python 书")
    assert r["budget_max"] is None
    assert "Python" in r["query"]


def test_usd_budget():
    r = parse("帮我买个 $20 以内的鼠标")
    assert r["budget_max"] == 20.0
    assert r["currency"] == "USD"


def test_empty_raises():
    try:
        parse("   ")
    except ValueError:
        return
    raise AssertionError("空指令应抛 ValueError")

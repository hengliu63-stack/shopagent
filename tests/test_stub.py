"""pay/stub.py 离线桩测试：形状对齐真实回执，且 stub 标注不可丢。"""
from pay.stub import stub_capture_order, stub_create_order

_DECISION = {"id": "demo-book-001", "name": "Python Crash Course",
             "total_price": 24.95}


def test_stub_create_order_is_labeled():
    order = stub_create_order(_DECISION)
    assert order["stub"] is True
    assert order["order_id"].startswith("STUB-")
    assert order["approve_url"] is None
    assert order["amount"] == "24.95"
    assert order["currency"] == "USD"


def test_stub_capture_receipt_shape_and_label():
    order = stub_create_order(_DECISION)
    receipt = stub_capture_order(order["order_id"])
    # 字段形状与 pay.client 的真实回执一致（order_id/capture_id/status/
    # amount/currency/captured_at/sandbox），并额外带 stub 标注
    for key in ("order_id", "capture_id", "status", "amount",
                "currency", "captured_at", "sandbox"):
        assert key in receipt
    assert receipt["stub"] is True
    assert receipt["sandbox"] is True
    assert receipt["capture_id"].startswith("STUBCAP-")
    assert receipt["order_id"] == order["order_id"]
    assert receipt["amount"] == "24.95"

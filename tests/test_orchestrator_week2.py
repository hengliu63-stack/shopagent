"""Week2 orchestrator：批准/扣款走通 DONE、挂起+resume、JSONL 结构。"""
import json
import os
import tempfile

from catalog.search import compare, search
from nlu.parser import parse
from orchestrator.engine import Engine
from orchestrator.run_log import read_log, summarize
from orchestrator.states import State
from pay.stub import stub_create_order


def _order(decision):
    return {"order_id": "TEST-ORDER-1",
            "approve_url": "https://example.com/approve",
            "status": "CREATED"}


def _capture(order_id):
    return {"order_id": order_id, "capture_id": "CAP-1",
            "status": "COMPLETED", "amount": "24.95",
            "currency": "USD", "sandbox": True}


def test_full_path_to_done_with_stubs():
    """注入 approve+capture（测试替身）→ 一路走到 DONE 出回执。"""
    with tempfile.TemporaryDirectory() as logdir:
        engine = Engine(parse=parse, search=search, compare=compare,
                        create_order=_order, approve=lambda ctx: True,
                        capture=_capture, log_dir=logdir)
        ctx = engine.run("帮我买一本 200 块以内的 Python 书")
        assert ctx.state == State.DONE
        assert ctx.receipt and ctx.receipt["capture_id"] == "CAP-1"
        events = read_log(os.path.join(logdir, f"{ctx.run_id}.jsonl"))
        kinds = [e["event"] for e in events]
        for expected in ("approved", "captured", "receipt_ready", "run_finished"):
            assert expected in kinds
        # JSONL 结构化：seq 单调递增、每条带 ts/elapsed_ms
        seqs = [e["seq"] for e in events]
        assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)
        assert all("ts" in e and "elapsed_ms" in e for e in events)
        log_path = os.path.join(logdir, f"{ctx.run_id}.jsonl")
        assert summarize(log_path)["final_state"] == "DONE"


def test_approval_suspend_then_resume_to_done():
    """未注入 approve → 建单后挂起；resume('approve') → 扣款 DONE。"""
    with tempfile.TemporaryDirectory() as logdir:
        engine = Engine(parse=parse, search=search, compare=compare,
                        create_order=_order, capture=_capture,
                        log_dir=logdir)
        ctx = engine.run("帮我买一本 200 块以内的 Python 书")
        assert ctx.state == State.SUSPENDED
        assert ctx.pending and ctx.pending["type"] == "approval"
        # 快照落盘
        snap = os.path.join(logdir, f"{ctx.run_id}.ctx.json")
        assert os.path.exists(snap)

        ctx2 = engine.resume(ctx.run_id, "approve")
        assert ctx2.state == State.DONE
        assert ctx2.receipt and ctx2.receipt["capture_id"] == "CAP-1"


def test_budget_suspend_then_resume_confirm():
    """超预算挂起 → resume('confirm') 放行 → 继续走到 pay 未接入挂起。"""
    with tempfile.TemporaryDirectory() as logdir:
        engine = Engine(parse=parse, search=search, compare=compare,
                        log_dir=logdir)
        ctx = engine.run("帮我买一台 10 块以内的笔记本电脑")
        assert ctx.state == State.SUSPENDED
        assert ctx.pending["type"] == "budget_confirm"

        ctx2 = engine.resume(ctx.run_id, "confirm")
        assert ctx2.decision is not None
        assert ctx2.state == State.SUSPENDED
        assert ctx2.pending["type"] == "pay_not_wired"


def test_resume_cancel_fails_run():
    with tempfile.TemporaryDirectory() as logdir:
        engine = Engine(parse=parse, search=search, compare=compare,
                        log_dir=logdir)
        ctx = engine.run("帮我买一台 10 块以内的笔记本电脑")
        ctx2 = engine.resume(ctx.run_id, "cancel")
        assert ctx2.state == State.FAILED


def test_pay_stub_is_marked():
    order = stub_create_order({"id": "x", "name": "n", "total_price": 9.5})
    assert order["stub"] is True
    assert order["order_id"].startswith("STUB-")
    assert order["amount"] == "9.50"

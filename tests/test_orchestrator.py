"""orchestrator 状态机 + 引擎骨架测试（demo 数据，不碰 PayPal）。"""
import os
import tempfile

from nlu.parser import parse
from catalog.search import search, compare
from orchestrator.engine import Engine
from orchestrator.states import RunContext, State, IllegalTransition
from orchestrator.run_log import read_log


def test_state_machine_happy_path_skeleton():
    """Week1 骨架：parse→search→compare 跑通，止于 SUSPENDED（pay 未接）。"""
    with tempfile.TemporaryDirectory() as logdir:
        engine = Engine(parse=parse, search=search, compare=compare,
                        log_dir=logdir)
        ctx = engine.run("帮我买一本 200 块以内的 Python 书")
        assert ctx.state == State.SUSPENDED
        assert ctx.intent and ctx.intent["budget_max"] == 200.0
        assert ctx.decision and ctx.decision["price"] <= 200 / 7.2 + 1
        assert "reason" in ctx.decision  # 自主决策理由必须有
        # 日志落盘
        events = read_log(os.path.join(logdir, f"{ctx.run_id}.jsonl"))
        kinds = [e["event"] for e in events]
        assert "intent_parsed" in kinds and "decision_made" in kinds


def test_illegal_transition():
    ctx = RunContext(run_id="t", user_instruction="x")
    try:
        ctx.transition(State.CAPTURED)  # IDLE → CAPTURED 非法
    except IllegalTransition:
        return
    raise AssertionError("非法迁移应抛 IllegalTransition")


def test_over_budget_suspends_for_confirmation():
    """Week2 行为变更：预算过低 → 挂起等用户确认（架构定的异常分支），
    不再 FAILED。pending 里带结构化超预算细节。"""
    with tempfile.TemporaryDirectory() as logdir:
        engine = Engine(parse=parse, search=search, compare=compare,
                        log_dir=logdir)
        ctx = engine.run("帮我买一台 10 块以内的笔记本电脑")
        assert ctx.state == State.SUSPENDED
        assert ctx.pending and ctx.pending["type"] == "budget_confirm"
        assert "超预算" in ctx.pending["message"]

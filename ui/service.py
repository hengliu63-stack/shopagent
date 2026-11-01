"""聊天界面服务层（Week3）：把 orchestrator 的离线 demo 流程
包装成界面可直接渲染的视图模型（JSON 可序列化）。

接法与 demo.py 一致并补齐 capture：
    parse_auto → catalog.search/compare → pay.stub 建单（桩）
    → SUSPENDED 等批准 → resume("approve") → pay.stub 扣款（桩）→ 回执

全程离线零 key；支付层是离线桩，视图模型里 payment_mode="stub" 明示，
order / receipt 均带 "stub": True，绝不冒充真实 PayPal Sandbox 交易。
真实链路等 Sandbox 凭证到位后，把 create_order / capture 换成
pay.client.PayClient 即可，本层不动。

本层不依赖任何 Web 框架：ui/app.py（标准库 http.server）只是它的薄壳，
测试可直接测本层。
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from catalog.search import OverBudgetError, compare, rank, search
from nlu.llm import parse_auto
from orchestrator.engine import Engine
from orchestrator.run_log import read_log
from orchestrator.states import RunContext
from pay.stub import stub_capture_order, stub_create_order

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS_DIR = os.path.join(_REPO_ROOT, "runs")


def build_demo_engine(log_dir: Optional[str] = None) -> Engine:
    """离线 demo 引擎：付款走 pay.stub 桩（建单 + 扣款），批准靠 resume。"""
    return Engine(
        parse=parse_auto,
        search=search,
        compare=compare,
        create_order=stub_create_order,   # 演示桩，order 带 stub: True
        capture=stub_capture_order,        # 演示桩，receipt 带 stub: True
        # approve 不注入：建单后挂起等用户在界面点「批准」（合规环节）
        log_dir=log_dir or RUNS_DIR,
    )


class ChatService:
    """一次多轮聊天 = 多个 run；每个 run 的状态以 engine 快照/日志为准。"""

    def __init__(self, engine: Optional[Engine] = None,
                 log_dir: Optional[str] = None) -> None:
        self.log_dir = log_dir or RUNS_DIR
        self.engine = engine or build_demo_engine(log_dir=self.log_dir)

    # ---------- 对外动作 ----------

    def start_run(self, instruction: str) -> Dict[str, Any]:
        instruction = (instruction or "").strip()
        if not instruction:
            raise ValueError("指令不能为空")
        ctx = self.engine.run(instruction)
        return self._view(ctx)

    def act(self, run_id: str, action: str,
            new_budget: Optional[float] = None) -> Dict[str, Any]:
        """对挂起的 run 执行动作：confirm / approve / cancel（见 engine.resume）。"""
        ctx = self.engine.resume(run_id, action, new_budget=new_budget)
        return self._view(ctx)

    # ---------- 视图模型 ----------

    def _view(self, ctx: RunContext) -> Dict[str, Any]:
        events = self._events(ctx.run_id)
        return {
            "run_id": ctx.run_id,
            "instruction": ctx.user_instruction,
            "state": ctx.state.value,
            "payment_mode": "stub",  # 离线演示桩，非真实 PayPal
            "intent": ctx.intent,
            "ranked": self._ranked_view(ctx),
            "decision": ctx.decision,
            "order": ctx.order,
            "pending": ctx.pending,
            "receipt": ctx.receipt,
            "error": ctx.error,
            "trajectory": [
                {"from": h["from"], "to": h["to"], "note": h["note"]}
                for h in ctx.history
            ],
            "states_path": " → ".join(
                [h["from"] for h in ctx.history]
                + ([ctx.history[-1]["to"]] if ctx.history else [ctx.state.value])
            ) if ctx.history else ctx.state.value,
            "events": events,
        }

    def _ranked_view(self, ctx: RunContext) -> List[Dict[str, Any]]:
        """比价候选展示行：预算内走 rank() 排名；全超预算时退化为
        按总价升序的全量展示（over_budget 标记），保证界面有据可看。"""
        if not ctx.intent or not ctx.candidates:
            return []
        try:
            result = rank(ctx.candidates, ctx.intent)
            return [self._row(c, over=False) for c in result["ranked"]]
        except OverBudgetError:
            qty = int(ctx.intent.get("quantity") or 1)
            rows = []
            for c in ctx.candidates:
                total = round(float(c["price"]) * qty, 2)
                rows.append(self._row(
                    {**c, "unit_price": float(c["price"]),
                     "quantity": qty, "total_price": total},
                    over=True))
            rows.sort(key=lambda r: r["total_price"])
            for i, r in enumerate(rows, start=1):
                r["rank"] = i
            return rows

    @staticmethod
    def _row(c: Dict[str, Any], over: bool) -> Dict[str, Any]:
        return {
            "rank": c.get("rank"),
            "id": c.get("id"),
            "name": c.get("name"),
            "name_cn": c.get("name_cn"),
            "unit_price": c.get("unit_price", c.get("price")),
            "quantity": c.get("quantity", 1),
            "total_price": c.get("total_price"),
            "rating": c.get("rating"),
            "sales": c.get("sales"),
            "score": c.get("score"),
            "over_budget": over,
        }

    def _events(self, run_id: str) -> List[Dict[str, Any]]:
        path = os.path.join(self.log_dir, f"{run_id}.jsonl")
        if not os.path.exists(path):
            return []
        return [
            {
                "seq": e.get("seq"),
                "elapsed_ms": e.get("elapsed_ms"),
                "state": e.get("state"),
                "event": e.get("event"),
                "detail": e.get("detail") or {},
            }
            for e in read_log(path)
        ]

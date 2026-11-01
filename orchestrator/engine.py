"""编排引擎：把 nlu → catalog → pay 按状态机串起来。

Week 2 完善（相对 Week1 骨架）：
- 批准/扣款接通：注入 approve + capture 后可走完
  COMPARED → ORDER_CREATED → APPROVED → CAPTURED → DONE；
- 超预算不再 FAILED：catalog 抛 OverBudgetError 时转 SUSPENDED
  （pending=budget_confirm），等用户确认后 resume() 继续；
- 等批准挂起同样落 pending=approval + 上下文快照（<run_id>.ctx.json），
  resume(run_id, "approve") 后接着扣款出回执；
- 每次 run 结束写 run_finished 事件（JSONL 审计轨迹收尾）。

各步骤仍以 callable 注入：真实 pay.Client、演示桩、测试替身都可插。
批准是合规必需的人工环节：未注入 approve 时，建单后一律挂起等批准，
绝不自动扣款。
"""
from __future__ import annotations

import dataclasses
import json
import os
import uuid
from typing import Any, Callable, Dict, Optional

from catalog.search import OverBudgetError

from .run_log import RunLogger
from .states import RunContext, State


class Engine:
    """可插拔的编排引擎：各步骤以 callable 注入，方便测试与替换实现。"""

    def __init__(
        self,
        parse: Callable[[str], Dict[str, Any]],
        search: Callable[[Dict[str, Any]], list],
        compare: Callable[[list, Dict[str, Any]], Dict[str, Any]],
        create_order: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
        approve: Optional[Callable[[RunContext], bool]] = None,
        capture: Optional[Callable[[str], Dict[str, Any]]] = None,
        log_dir: Optional[str] = None,
    ) -> None:
        self.parse = parse
        self.search = search
        self.compare = compare
        self.create_order = create_order
        self.approve = approve
        self.capture = capture
        self.log_dir = log_dir

    # ---------- 对外入口 ----------

    def run(self, instruction: str) -> RunContext:
        run_id = uuid.uuid4().hex[:12]
        ctx = RunContext(run_id=run_id, user_instruction=instruction)
        logger = RunLogger(run_id, log_dir=self.log_dir)
        try:
            logger.log(ctx.state.value, "run_started",
                       {"instruction": ctx.user_instruction})
            self._run(ctx, logger)
            return ctx
        finally:
            self._finish(ctx, logger)
            logger.close()

    def resume(self, run_id: str, action: str,
               new_budget: Optional[float] = None) -> RunContext:
        """从挂起快照恢复一次 run。

        action:
        - "confirm"：pending=budget_confirm 时确认继续（可带 new_budget，
          币种沿用原意图；不带 = 取消预算上限）；
        - "approve"：pending=approval 时买家已批准，继续扣款；
        - "cancel"：放弃本次 run → FAILED。
        """
        logger = RunLogger(run_id, log_dir=self.log_dir)
        ctx: Optional[RunContext] = None
        try:
            ctx = self._load_snapshot(logger.log_dir, run_id)
            logger.log(ctx.state.value, "run_resumed",
                       {"action": action, "pending": ctx.pending})
            if ctx.state != State.SUSPENDED:
                raise ValueError(f"run {run_id} 不在挂起态（当前 {ctx.state}）")
            ptype = (ctx.pending or {}).get("type")

            if action == "cancel":
                ctx.pending = None
                return self._fail(ctx, logger, "用户取消本次购物")

            if ptype == "budget_confirm" and action == "confirm":
                assert ctx.intent is not None
                ctx.intent["budget_max"] = new_budget  # None = 不限预算
                ctx.pending = None
                ctx.transition(State.PARSED, "用户确认预算，重新比价")
                logger.log(ctx.state.value, "intent_parsed", ctx.intent)
                if self._search_compare(ctx, logger):
                    self._order_flow(ctx, logger)
                return ctx

            if ptype == "approval" and action == "approve":
                ctx.pending = None
                ctx.transition(State.ORDER_CREATED, "买家已批准，恢复扣款")
                logger.log(ctx.state.value, "order_created",
                           {"resumed": True, **(ctx.order or {})})
                self._approve_capture(ctx, logger, approved=True)
                return ctx

            raise ValueError(
                f"pending={ptype} 不支持 action={action}"
            )
        finally:
            if ctx is not None:
                self._finish(ctx, logger)
            logger.close()

    # ---------- 主流程 ----------

    def _run(self, ctx: RunContext, logger: RunLogger) -> None:
        # 1. 意图解析
        try:
            ctx.intent = self.parse(ctx.user_instruction)
            ctx.transition(State.PARSED, f"意图：{ctx.intent}")
            logger.log(ctx.state.value, "intent_parsed", ctx.intent)
        except Exception as exc:
            self._fail(ctx, logger, f"意图解析失败：{exc}")
            return
        # 2-3. 搜索 + 比价
        if not self._search_compare(ctx, logger):
            return
        # 4-6. 建单 → 批准 → 扣款
        self._order_flow(ctx, logger)

    def _search_compare(self, ctx: RunContext, logger: RunLogger) -> bool:
        """搜索 + 比价。成功 True；失败/挂起已处理则 False。"""
        try:
            ctx.candidates = self.search(ctx.intent)
            ctx.transition(State.SEARCHED, f"搜到 {len(ctx.candidates)} 个候选")
            logger.log(ctx.state.value, "products_searched",
                       {"count": len(ctx.candidates),
                        "ids": [c.get("id") for c in ctx.candidates]})
        except Exception as exc:
            self._fail(ctx, logger, f"商品搜索失败：{exc}")
            return False
        try:
            ctx.decision = self.compare(ctx.candidates, ctx.intent)
            ctx.transition(
                State.COMPARED,
                f"选中：{ctx.decision.get('name')}，理由：{ctx.decision.get('reason')}")
            logger.log(ctx.state.value, "decision_made", ctx.decision)
            return True
        except OverBudgetError as exc:
            # 架构定的异常分支：超预算回问用户 → 挂起，不算失败
            self._suspend(ctx, logger, {
                "type": "budget_confirm",
                "budget_usd": exc.budget_usd,
                "cheapest_total_usd": exc.cheapest_total,
                "message": str(exc),
            }, f"超预算，等用户确认：{exc}")
            return False
        except Exception as exc:
            self._fail(ctx, logger, f"比价决策失败：{exc}")
            return False

    def _order_flow(self, ctx: RunContext, logger: RunLogger) -> None:
        """建单 → 批准 → 扣款（ctx 须已 COMPARED）。"""
        if self.create_order is None:
            self._suspend(ctx, logger,
                          {"type": "pay_not_wired"},
                          "pay 未接入，止于比价决策")
            return
        try:
            ctx.order = self.create_order(ctx.decision)
            ctx.transition(State.ORDER_CREATED,
                           f"order_id={ctx.order.get('order_id')}")
            logger.log(ctx.state.value, "order_created", ctx.order)
        except Exception as exc:
            self._fail(ctx, logger, f"建单失败：{exc}")
            return
        self._approve_capture(ctx, logger, approved=None)

    def _approve_capture(self, ctx: RunContext, logger: RunLogger,
                         approved: Optional[bool]) -> None:
        """批准 + 扣款（ctx 须已 ORDER_CREATED）。

        approved=None 表示走注入的 approve callable；未注入则挂起等批准。
        """
        if approved is None:
            if self.approve is None:
                self._suspend(ctx, logger, {
                    "type": "approval",
                    "approve_url": (ctx.order or {}).get("approve_url"),
                }, "等待买家批准（合规环节）")
                logger.log(ctx.state.value, "waiting_approval",
                           {"approve_url": (ctx.order or {}).get("approve_url")})
                return
            try:
                approved = bool(self.approve(ctx))
            except Exception as exc:
                self._fail(ctx, logger, f"批准环节失败：{exc}")
                return
        if not approved:
            self._suspend(ctx, logger, {
                "type": "approval",
                "approve_url": (ctx.order or {}).get("approve_url"),
            }, "买家未批准/批准超时，挂起")
            return

        ctx.transition(State.APPROVED, "买家批准完成")
        logger.log(ctx.state.value, "approved",
                   {"order_id": (ctx.order or {}).get("order_id")})
        if self.capture is None:
            self._fail(ctx, logger, "capture 未接入，无法扣款")
            return
        try:
            ctx.receipt = self.capture((ctx.order or {}).get("order_id"))
            ctx.transition(State.CAPTURED,
                           f"capture_id={ctx.receipt.get('capture_id')}")
            logger.log(ctx.state.value, "captured", ctx.receipt)
        except Exception as exc:
            self._fail(ctx, logger, f"扣款失败：{exc}")
            return
        ctx.transition(State.DONE, "回执已生成")
        logger.log(ctx.state.value, "receipt_ready", ctx.receipt)

    # ---------- 挂起 / 失败 / 收尾 ----------

    def _suspend(self, ctx: RunContext, logger: RunLogger,
                 pending: Dict[str, Any], note: str) -> None:
        ctx.pending = pending
        ctx.transition(State.SUSPENDED, note)
        logger.log(ctx.state.value, "suspended",
                   {"pending": pending, "note": note})

    @staticmethod
    def _fail(ctx: RunContext, logger: RunLogger, error: str) -> RunContext:
        ctx.error = error
        ctx.transition(State.FAILED, error)
        logger.log(ctx.state.value, "failed", {"error": error})
        return ctx

    def _finish(self, ctx: RunContext, logger: RunLogger) -> None:
        """每次 run/resume 收尾：run_finished 事件 + 上下文快照落盘。"""
        try:
            logger.log(ctx.state.value, "run_finished", {
                "final_state": ctx.state.value,
                "error": ctx.error,
                "has_receipt": ctx.receipt is not None,
            })
        except Exception:
            pass
        try:
            data = dataclasses.asdict(ctx)
            data["state"] = ctx.state.value
            path = os.path.join(logger.log_dir, f"{ctx.run_id}.ctx.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1)
        except Exception:
            pass  # 快照失败不拖垮主流程

    @staticmethod
    def _load_snapshot(log_dir: str, run_id: str) -> RunContext:
        path = os.path.join(log_dir, f"{run_id}.ctx.json")
        if not os.path.exists(path):
            raise ValueError(f"找不到 run {run_id} 的挂起快照")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        data["state"] = State(data["state"])
        return RunContext(**data)

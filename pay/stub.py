"""离线演示桩（Week2 建单 / Week3 补 capture）：没有 PayPal Sandbox 凭证时，
让端到端流程跑完「建单 → 等批准挂起 → 批准 → 扣款出回执」，
全程不碰 PayPal、不碰网络、不碰真钱。

返回的 order / receipt 都带 "stub": True —— 回执/界面/日志必须如实标注
为演示桩，绝不冒充真实 Sandbox 订单。凭证到位后，engine 改注入
pay.client.PayClient 的 create_order/capture_order 即可，
本文件不参与真实链路。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

# 进程内登记表：capture 时按 order_id 回查金额/商品（仅演示，重启即清）
_STUB_ORDERS: Dict[str, Dict[str, Any]] = {}


def stub_create_order(decision: Dict[str, Any]) -> Dict[str, Any]:
    """engine 的 create_order 桩：按比价决策生成一张假订单（仅演示）。"""
    total = decision.get("total_price", decision.get("price"))
    order = {
        "order_id": f"STUB-{uuid.uuid4().hex[:10].upper()}",
        "approve_url": None,  # 桩没有真实批准页，引擎会挂起等待
        "status": "STUB_CREATED",
        "stub": True,
        "item_id": decision.get("id"),
        "item_name": decision.get("name"),
        "amount": f"{float(total):.2f}" if total is not None else None,
        "currency": "USD",
    }
    _STUB_ORDERS[order["order_id"]] = order
    return order


def stub_capture_order(order_id: str) -> Dict[str, Any]:
    """engine 的 capture 桩：回执形状对齐 pay.client 的真实回执，
    额外带 "stub": True + "sandbox": True，capture_id 以 STUBCAP- 开头，
    一眼可辨不是真实 PayPal 扣款。"""
    order = _STUB_ORDERS.get(order_id, {})
    return {
        "order_id": order_id,
        "capture_id": f"STUBCAP-{uuid.uuid4().hex[:10].upper()}",
        "status": "STUB_COMPLETED",
        "amount": order.get("amount"),
        "currency": order.get("currency", "USD"),
        "item_name": order.get("item_name"),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "sandbox": True,
        "stub": True,
    }

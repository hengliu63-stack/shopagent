"""PayPal Sandbox 付款客户端：建单 → 取 approve 链接 → 查单 → capture。

基于官方当前 SDK `paypal-server-sdk`（PyPI），Orders API v2。
全程 Sandbox，建单带 PayPal-Request-Id 幂等键（agent 重试场景必需）。

返回的回执（receipt）即"链下交易哈希"，演示界面直接展示：
    order_id / capture_id / 金额 / 币种 / 状态 / 时间戳
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .config import PayConfig, PayConfigError


def _sdk():
    try:
        from paypalserversdk.paypal_serversdk_client import PaypalServersdkClient
        from paypalserversdk.configuration import Environment
        from paypalserversdk.http.auth.o_auth_2 import ClientCredentialsAuthCredentials
        from paypalserversdk.models.order_request import OrderRequest
        from paypalserversdk.models.purchase_unit_request import PurchaseUnitRequest
        from paypalserversdk.models.amount_with_breakdown import AmountWithBreakdown
        from paypalserversdk.models.item import Item
        from paypalserversdk.models.checkout_payment_intent import CheckoutPaymentIntent
    except ImportError as exc:  # pragma: no cover
        raise PayConfigError(
            "缺少 paypal-server-sdk：pip install -r requirements.txt"
        ) from exc
    return (
        PaypalServersdkClient,
        Environment,
        ClientCredentialsAuthCredentials,
        OrderRequest,
        PurchaseUnitRequest,
        AmountWithBreakdown,
        Item,
        CheckoutPaymentIntent,
    )


class PayClient:
    """Sandbox 付款客户端。所有金额均为 USD 测试币，无真钱。"""

    def __init__(self, config: Optional[PayConfig] = None) -> None:
        self.config = config or PayConfig.from_env()
        (
            Client,
            Environment,
            Credentials,
            OrderRequest,
            PurchaseUnitRequest,
            AmountWithBreakdown,
            Item,
            CheckoutPaymentIntent,
        ) = _sdk()
        self._client = Client(
            client_credentials_auth_credentials=Credentials(
                self.config.client_id, self.config.client_secret
            ),
            environment=Environment.SANDBOX,  # 写死 sandbox，防生产
        )
        # 模型类存实例上，方法里直接用
        self._OrderRequest = OrderRequest
        self._PurchaseUnitRequest = PurchaseUnitRequest
        self._AmountWithBreakdown = AmountWithBreakdown
        self._Item = Item
        self._CheckoutPaymentIntent = CheckoutPaymentIntent

    # ---------- 建单 ----------

    def create_order(
        self,
        name: str,
        value: str,
        currency: str = "USD",
        quantity: str = "1",
        reference_id: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """建单（intent=CAPTURE），返回 order_id + approve_url。"""
        request_id = str(uuid.uuid4())  # 幂等键
        body = self._OrderRequest(
            intent=self._CheckoutPaymentIntent.CAPTURE,
            purchase_units=[
                self._PurchaseUnitRequest(
                    reference_id=reference_id or f"shopagent-{uuid.uuid4().hex[:8]}",
                    description=description or name,
                    amount=self._AmountWithBreakdown(
                        currency_code=currency, value=value
                    ),
                    items=[
                        self._Item(
                            name=name,
                            unit_amount=self._AmountWithBreakdown(
                                currency_code=currency, value=value
                            ),
                            quantity=quantity,
                        )
                    ],
                )
            ],
        )
        resp = self._client.orders.create_order(
            options={"body": body, "paypal_request_id": request_id}
        )
        order = resp.body
        order_id = getattr(order, "id", None)
        approve_url = self._extract_approve_url(order)
        return {
            "order_id": order_id,
            "approve_url": approve_url,
            "status": str(getattr(order, "status", "")),
            "request_id": request_id,
        }

    # ---------- 查单 ----------

    def get_order(self, order_id: str) -> Dict[str, Any]:
        resp = self._client.orders.get_order(options={"id": order_id})
        order = resp.body
        return {
            "order_id": getattr(order, "id", order_id),
            "status": str(getattr(order, "status", "")),
            "approve_url": self._extract_approve_url(order),
        }

    # ---------- 扣款 ----------

    def capture_order(self, order_id: str) -> Dict[str, Any]:
        """capture：买家批准后扣款，返回付款回执。"""
        resp = self._client.orders.capture_order(
            options={"id": order_id, "paypal_request_id": str(uuid.uuid4())}
        )
        order = resp.body
        return self._build_receipt(order)

    # ---------- 内部 ----------

    @staticmethod
    def _extract_approve_url(order: Any) -> Optional[str]:
        for link in getattr(order, "links", None) or []:
            if getattr(link, "rel", "") == "approve":
                return getattr(link, "href", None)
        return None

    @staticmethod
    def _build_receipt(order: Any) -> Dict[str, Any]:
        capture_id: Optional[str] = None
        amount_value: Optional[str] = None
        currency: Optional[str] = None
        units: List[Any] = getattr(order, "purchase_units", None) or []
        if units:
            payments = getattr(units[0], "payments", None)
            captures = getattr(payments, "captures", None) or [] if payments else []
            if captures:
                cap = captures[0]
                capture_id = getattr(cap, "id", None)
                amt = getattr(cap, "amount", None)
                if amt:
                    amount_value = getattr(amt, "value", None)
                    currency = getattr(amt, "currency_code", None)
        return {
            "order_id": getattr(order, "id", None),
            "capture_id": capture_id,
            "status": str(getattr(order, "status", "")),
            "amount": amount_value,
            "currency": currency,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "sandbox": True,  # 测试币标记，回执上写清楚
        }

"""PayPal Sandbox 配置：只从环境变量读凭证，绝不 hardcode。

必需：
    PAYPAL_CLIENT_ID       Sandbox 应用的 Client ID
    PAYPAL_CLIENT_SECRET   Sandbox 应用的 Secret
可选：
    PAYPAL_ENV             只能是 "sandbox"（默认）。任何其它值直接拒绝启动，
                           防止误连生产环境碰真钱。
"""
from __future__ import annotations

import os
from dataclasses import dataclass


class PayConfigError(RuntimeError):
    """凭证缺失或环境非法时抛出。"""


@dataclass(frozen=True)
class PayConfig:
    client_id: str
    client_secret: str
    environment: str = "sandbox"

    @classmethod
    def from_env(cls) -> "PayConfig":
        # 允许项目根目录的 .env（python-dotenv），但环境变量优先
        try:
            from dotenv import load_dotenv  # type: ignore
            load_dotenv()
        except Exception:
            pass

        client_id = (os.environ.get("PAYPAL_CLIENT_ID") or "").strip()
        client_secret = (os.environ.get("PAYPAL_CLIENT_SECRET") or "").strip()
        env = (os.environ.get("PAYPAL_ENV") or "sandbox").strip().lower()

        if env != "sandbox":
            raise PayConfigError(
                f"PAYPAL_ENV={env!r} 被拒绝：ShopAgent 只允许 sandbox，"
                "绝不连接生产环境（防真钱）。"
            )
        if not client_id or not client_secret:
            raise PayConfigError(
                "缺少 PayPal Sandbox 凭证：请复制 .env.example 为 .env 并填写 "
                "PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET（来自 "
                "https://developer.paypal.com Dashboard → Sandbox 应用）。"
            )
        return cls(client_id=client_id, client_secret=client_secret, environment=env)

"""Week 1 里程碑脚本：PayPal Sandbox 全链路冒烟测试。

流程：
    1. 建单（$1.00 测试币，intent=CAPTURE）
    2. 打印 approve 链接 → 你用浏览器打开，用 Sandbox Personal 测试账号登录批准
    3. 回车继续 → 自动 capture → 打印付款回执（第一张 sandbox 收据）

用法：
    cp .env.example .env   # 填好 PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET
    python -m pay.sandbox_smoke

注意：Sandbox Personal 测试账号的邮箱/密码在
https://developer.paypal.com Dashboard → Sandbox → Accounts 里看。
"""
from __future__ import annotations

import json
import sys
import time

from .client import PayClient
from .config import PayConfigError


def main() -> int:
    try:
        client = PayClient()
    except PayConfigError as exc:
        print(f"[配置缺失] {exc}")
        return 2

    print("== 1/3 建单（Sandbox，$1.00 测试币） ==")
    order = client.create_order(
        name="ShopAgent smoke test item",
        value="1.00",
        currency="USD",
        description="ShopAgent Week1 冒烟测试（Sandbox 测试币）",
    )
    print(json.dumps(order, indent=2, ensure_ascii=False))
    if not order.get("approve_url"):
        print("[失败] 没拿到 approve 链接")
        return 1

    print()
    print("== 2/3 批准 ==")
    print("浏览器打开下面链接，用 Sandbox Personal 测试账号登录并批准：")
    print(order["approve_url"])
    input("批准完成后回车继续…")

    print()
    print("== 3/3 扣款（capture） ==")
    for attempt in range(3):
        try:
            receipt = client.capture_order(order["order_id"])
            break
        except Exception as exc:  # 批准可能还在传播，重试
            print(f"[重试 {attempt + 1}/3] {exc}")
            time.sleep(5)
    else:
        print("[失败] capture 未成功，请确认已在浏览器里点批准")
        return 1

    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    if receipt.get("status") == "COMPLETED" and receipt.get("capture_id"):
        print()
        print("🎉 第一张 Sandbox 收据到手：capture_id =", receipt["capture_id"])
        return 0
    print("[未完成] 状态：", receipt.get("status"))
    return 1


if __name__ == "__main__":
    sys.exit(main())

"""ui/ 界面服务层测试（Week3）：全离线、stub 支付，接通 orchestrator。

覆盖界面要展示的四样东西：比价候选、状态轨迹、待批准卡片、收据卡片，
以及超预算确认分支。HTTP 路由只测纯函数 handle()，不起真服务器。
"""
import os

import pytest

from ui.app import handle
from ui.service import ChatService


@pytest.fixture()
def service(tmp_path):
    return ChatService(log_dir=str(tmp_path))


def test_start_run_shows_candidates_trajectory_and_pending(service):
    view = service.start_run("帮我买一本 200 块以内的 Python 书")
    assert view["payment_mode"] == "stub"
    assert view["state"] == "SUSPENDED"
    assert view["pending"]["type"] == "approval"
    # 比价候选：有排名、Top1 与决策一致
    assert view["ranked"], "界面要能展示比价候选"
    assert view["ranked"][0]["id"] == view["decision"]["id"]
    assert view["decision"]["total_price"] == 24.95
    # 订单是桩，必须带标注
    assert view["order"]["stub"] is True
    assert view["order"]["order_id"].startswith("STUB-")
    # 轨迹与事件日志齐全
    assert "COMPARED" in view["states_path"]
    events = [e["event"] for e in view["events"]]
    assert "decision_made" in events and "waiting_approval" in events
    assert view["receipt"] is None


def test_approve_produces_stub_receipt_card(service):
    view = service.start_run("帮我买个 $20 以内的鼠标")
    done = service.act(view["run_id"], "approve")
    assert done["state"] == "DONE"
    receipt = done["receipt"]
    assert receipt is not None
    assert receipt["stub"] is True
    assert receipt["capture_id"].startswith("STUBCAP-")
    assert receipt["amount"] == "19.99"
    assert "CAPTURED" in done["states_path"]


def test_over_budget_confirm_then_approve(service):
    view = service.start_run("买两本 100 块以内便宜点的 Python 书")
    assert view["state"] == "SUSPENDED"
    assert view["pending"]["type"] == "budget_confirm"
    # 候选仍可展示（全超预算标记）
    assert view["ranked"] and all(r["over_budget"] for r in view["ranked"])
    # 确认（不限预算）→ 重新比价 → 建单 → 等批准
    view2 = service.act(view["run_id"], "confirm")
    assert view2["state"] == "SUSPENDED"
    assert view2["pending"]["type"] == "approval"
    assert view2["decision"]["total_price"] == 49.90
    # 批准 → 出 stub 收据
    done = service.act(view["run_id"], "approve")
    assert done["state"] == "DONE"
    assert done["receipt"]["amount"] == "49.90"


def test_cancel_ends_run(service):
    view = service.start_run("帮我买一本 200 块以内的 Python 书")
    cancelled = service.act(view["run_id"], "cancel")
    assert cancelled["state"] == "FAILED"
    assert cancelled["receipt"] is None


def test_empty_instruction_rejected(service):
    with pytest.raises(ValueError):
        service.start_run("   ")


def test_http_routes(tmp_path):
    svc = ChatService(log_dir=str(tmp_path))
    status, ctype, body = handle("GET", "/", {}, svc)
    assert status == 200 and b"ShopAgent" in body
    status, _, body = handle("GET", "/api/health", {}, svc)
    assert status == 200 and b'"payment_mode": "stub"' in body
    import json
    status, _, body = handle(
        "POST", "/api/run",
        {"instruction": "帮我买一本 200 块以内的 Python 书"}, svc)
    assert status == 200
    view = json.loads(body)
    assert view["state"] == "SUSPENDED" and view["run_id"]
    status, _, body = handle(
        "POST", "/api/resume",
        {"run_id": view["run_id"], "action": "approve"}, svc)
    assert status == 200
    assert json.loads(body)["state"] == "DONE"
    status, _, _ = handle("GET", "/nope", {}, svc)
    assert status == 404
    # runs/ 日志落在指定目录（界面/测试互不污染仓库 runs/）
    assert os.path.exists(os.path.join(str(tmp_path),
                                       f"{view['run_id']}.jsonl"))

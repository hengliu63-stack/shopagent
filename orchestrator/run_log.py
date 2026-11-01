"""执行日志：agent 每一步的审计轨迹（JSONL）。

每行一条事件：
    {"ts": ..., "run_id": ..., "state": ..., "event": ..., "detail": {...}}

UI 把它渲染成"思考轨迹"；评审看到的是 agent 自主决策的完整证据链。
日志只追加不修改，跑完即审计记录。
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class RunLogger:
    def __init__(self, run_id: str, log_dir: Optional[str] = None) -> None:
        self.run_id = run_id
        self.log_dir = log_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "..", "runs"
        )
        os.makedirs(self.log_dir, exist_ok=True)
        self.path = os.path.join(self.log_dir, f"{run_id}.jsonl")
        self._fh = open(self.path, "a", encoding="utf-8")
        self._seq = 0
        self._t0 = time.monotonic()
        # resume 追加同一文件时，seq 接着已有行数走（保持单调）
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as fh:
                self._seq = sum(1 for line in fh if line.strip())

    def log(self, state: str, event: str, detail: Optional[Dict[str, Any]] = None) -> None:
        self._seq += 1
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "seq": self._seq,
            "elapsed_ms": int((time.monotonic() - self._t0) * 1000),
            "run_id": self.run_id,
            "state": state,
            "event": event,
            "detail": detail or {},
        }
        self._fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._fh.flush()

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass

    def __enter__(self) -> "RunLogger":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


def read_log(path: str) -> list:
    """读回 JSONL（UI 渲染用）。"""
    events = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def summarize(path: str) -> Dict[str, Any]:
    """把一条 run 的 JSONL 汇总成轨迹摘要（UI 轨迹条/演示输出用）。"""
    events = read_log(path)
    states: list = []
    for e in events:
        if not states or states[-1] != e.get("state"):
            states.append(e.get("state"))
    decision = None
    for e in events:
        if e.get("event") == "decision_made":
            decision = e.get("detail")
    return {
        "run_id": events[0]["run_id"] if events else None,
        "events": [e.get("event") for e in events],
        "states": states,
        "final_state": events[-1].get("state") if events else None,
        "decision": decision,
        "event_count": len(events),
    }

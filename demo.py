"""端到端演示（Week2，免 key）：一句话 → 意图 → 比价 → 建单（桩）→ 挂起等批准。

    python demo.py                      # 跑 3 条内置示例指令
    python demo.py "帮我买两本 100 块以内便宜点的 Python 书"

全程离线：NLU 走 LLM（配置了 SHOPAGENT_LLM_API_KEY 时）或规则版兜底；
商品走本地 demo 池；付款是 pay.stub 演示桩（标注 stub），
engine 在等批准处 SUSPENDED —— 真实 PayPal 链路等 Sandbox 凭证到位后
把 create_order/capture 换成 pay.client.PayClient 即可。
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from catalog.search import compare, search
from nlu.llm import parse_auto
from orchestrator.engine import Engine
from orchestrator.run_log import summarize
from pay.stub import stub_create_order

EXAMPLES = [
    "帮我买一本 200 块以内的 Python 书",
    "买两本 100 块以内便宜点的 Python 书",
    "帮我买个 $20 以内的鼠标",
]

RUNS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runs")


def build_engine() -> Engine:
    return Engine(
        parse=parse_auto,
        search=search,
        compare=compare,
        create_order=stub_create_order,  # 演示桩；真实链路换 PayClient
        # approve/capture 不注入：建单后挂起等批准（合规环节 + 免 key）
    )


def run_one(engine: Engine, instruction: str) -> None:
    ctx = engine.run(instruction)
    print("=" * 72)
    print(f"指令：{instruction}")
    print(f"run_id：{ctx.run_id}　最终状态：{ctx.state.value}")
    if ctx.intent:
        print(f"意图：{json.dumps(ctx.intent, ensure_ascii=False)}")
    if ctx.decision:
        d = ctx.decision
        print(f"决策：{d.get('name_cn') or d.get('name')} "
              f"${d.get('unit_price')} ×{d.get('quantity')} = ${d.get('total_price')}")
        print(f"理由：{d.get('reason')}")
    if ctx.order:
        print(f"建单（桩）：{json.dumps(ctx.order, ensure_ascii=False)}")
    if ctx.pending:
        print(f"挂起：{json.dumps(ctx.pending, ensure_ascii=False)}")
    if ctx.error:
        print(f"错误：{ctx.error}")
    log_path = os.path.join(RUNS_DIR, f"{ctx.run_id}.jsonl")
    summary = summarize(log_path)
    print(f"轨迹：{' → '.join(s for s in summary['states'] if s)}")
    print(f"日志：{log_path}（{summary['event_count']} 条事件）")
    print()


def main() -> int:
    engine = build_engine()
    instructions = sys.argv[1:] or EXAMPLES
    for ins in instructions:
        run_one(engine, ins)
    return 0


if __name__ == "__main__":
    sys.exit(main())

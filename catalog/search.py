"""商品搜索与比价（Week2）：本地 demo 池 + 自主比价排序。

Week2 完善点（相对 Week1）：
- rank()：输出完整排序（Top-N），每件带单价/数量/总价 + 分项得分，
  不再只给 Top1——UI/日志能展示 agent 的完整决策过程；
- 预算按「总价 = 单价 × 数量」判定（Week1 只看单价，两台笔记本会误判）；
- 排序策略 honoring NLU preferences：price_first / rating_first（默认）/
  sales_first；
- 超预算抛 OverBudgetError（带结构化细节），orchestrator 据此转
  SUSPENDED 等用户确认，而不是笼统 FAILED。

Channel3 仍未接入：search() 走 demo 池（架构定的兜底），
接入时在本文件加优先分支、失败降级 search_pool 即可，rank/compare 不动。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from .demo_pool import search_pool

# CNY→USD 粗换算（演示用；demo 池本身 USD 标价）
CNY_PER_USD = 7.2


class OverBudgetError(ValueError):
    """候选全部超预算：携带结构化细节，供 orchestrator 挂起回问用户。"""

    def __init__(self, budget_usd: Optional[float], cheapest_total: float,
                 intent: Dict[str, Any]) -> None:
        self.budget_usd = budget_usd
        self.cheapest_total = cheapest_total
        self.intent = intent
        super().__init__(
            f"超预算：预算 {intent.get('budget_max')}{intent.get('currency')} "
            f"(≈${budget_usd})，最便宜的组合也要 ${cheapest_total}。"
        )


def _to_usd(amount: Optional[float], currency: str) -> Optional[float]:
    if amount is None:
        return None
    if currency.upper() == "CNY":
        return round(amount / CNY_PER_USD, 2)
    return amount


def search(intent: Dict[str, Any], limit: int = 10) -> List[Dict[str, Any]]:
    """按意图 query 搜候选商品（demo 池）。"""
    return search_pool(intent.get("query", ""), limit=limit)


def _value_score(c: Dict[str, Any]) -> float:
    """默认性价比得分：评分 70% + 销量对数 30%（确定性可复现）。"""
    return c["rating"] * 0.7 + math.log10(c["sales"] + 1) * 0.3 * 2


def rank(
    candidates: List[Dict[str, Any]], intent: Dict[str, Any]
) -> Dict[str, Any]:
    """比价排序：预算（总价）过滤 → 按策略排序 → 完整排名 + 元信息。

    返回 {"ranked": [...], "budget_usd": ..., "strategy": ...,
          "affordable_count": ...}
    ranked 每项是候选副本，附加 unit_price / quantity / total_price /
    score。全部超预算抛 OverBudgetError；无候选抛 ValueError。
    """
    if not candidates:
        raise ValueError("没搜到候选商品")

    quantity = int(intent.get("quantity") or 1)
    budget_usd = _to_usd(intent.get("budget_max"), intent.get("currency", "CNY"))

    enriched: List[Dict[str, Any]] = []
    for c in candidates:
        total = round(float(c["price"]) * quantity, 2)
        enriched.append({
            **c,
            "unit_price": float(c["price"]),
            "quantity": quantity,
            "total_price": total,
            "score": round(_value_score(c), 4),
        })

    affordable = [
        c for c in enriched
        if budget_usd is None or c["total_price"] <= budget_usd
    ]
    if not affordable:
        cheapest_total = min(c["total_price"] for c in enriched)
        raise OverBudgetError(budget_usd, cheapest_total, intent)

    prefs = intent.get("preferences") or []
    if "price_first" in prefs:
        strategy = "price_first"
        affordable.sort(key=lambda c: (c["total_price"], -c["rating"]))
    elif "sales_first" in prefs:
        strategy = "sales_first"
        affordable.sort(key=lambda c: (-c["sales"], -c["rating"]))
    else:
        strategy = "rating_first"
        affordable.sort(key=lambda c: (-c["score"], -c["rating"]))

    for i, c in enumerate(affordable, start=1):
        c["rank"] = i

    return {
        "ranked": affordable,
        "budget_usd": budget_usd,
        "strategy": strategy,
        "affordable_count": len(affordable),
        "compared_count": len(candidates),
    }


def compare(
    candidates: List[Dict[str, Any]], intent: Dict[str, Any]
) -> Dict[str, Any]:
    """自主比价决策：rank() 的 Top1 + 选择理由（写进执行日志给评审看）。"""
    result = rank(candidates, intent)
    top = result["ranked"][0]
    budget_usd = result["budget_usd"]
    qty_note = f"×{top['quantity']} 件，总价 ${top['total_price']}" \
        if top["quantity"] > 1 else f"价格 ${top['unit_price']}"
    strategy_note = {
        "price_first": "按你的偏好（便宜优先）选了总价最低的",
        "sales_first": "按你的偏好（热门优先）选了销量最高的",
        "rating_first": "按评分×销量综合最优选出",
    }[result["strategy"]]
    return {
        **top,
        "reason": (
            f"预算内（≤${budget_usd}）{result['affordable_count']} 个候选中，"
            f"{strategy_note}：{top.get('name_cn') or top['name']}，"
            f"评分 {top['rating']}/5.0，销量 {top['sales']}，{qty_note}。"
            if budget_usd else
            f"未设预算，{result['affordable_count']} 个候选中，"
            f"{strategy_note}：{top.get('name_cn') or top['name']}，"
            f"评分 {top['rating']}/5.0，销量 {top['sales']}，{qty_note}。"
        ),
        "budget_usd": budget_usd,
        "compared_count": result["compared_count"],
        "strategy": result["strategy"],
        "ranked_ids": [c["id"] for c in result["ranked"]],
    }

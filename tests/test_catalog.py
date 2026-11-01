"""Week2 catalog：rank 排序策略 + 数量感知预算 + compare 理由。"""
import pytest

from catalog.search import OverBudgetError, compare, rank, search
from nlu.parser import parse


def _intent(text: str):
    return parse(text)


def test_rank_budget_filters_by_unit_price():
    intent = _intent("帮我买一本 200 块以内的 Python 书")
    result = rank(search(intent), intent)
    # 预算 ≈$27.78：只有 $24.95 的《Python 编程快速上手》在预算内
    assert result["affordable_count"] == 1
    assert result["ranked"][0]["id"] == "demo-book-003"
    assert result["ranked"][0]["total_price"] == 24.95


def test_rank_quantity_aware_over_budget():
    """两台笔记本：总价 $1498 远超预算 ≈$416 → OverBudgetError（Week1 只看单价会误判）。"""
    intent = _intent("买两台 3000 元以下的笔记本电脑")
    with pytest.raises(OverBudgetError) as ei:
        rank(search(intent), intent)
    assert ei.value.cheapest_total == 1498.0


def test_rank_strategies_change_winner():
    intent = _intent("帮我买个鼠标")
    cands = search(intent)
    default = rank(cands, intent)
    assert default["strategy"] == "rating_first"
    assert default["ranked"][0]["id"] == "demo-mouse-001"  # MX Master 综合分最高

    cheap = rank(cands, {**intent, "preferences": ["price_first"]})
    assert cheap["ranked"][0]["id"] == "demo-mouse-002"  # M650 最便宜

    hot = rank(cands, {**intent, "preferences": ["sales_first"]})
    assert hot["ranked"][0]["id"] == "demo-mouse-002"  # M650 销量最高


def test_compare_reason_mentions_total_for_quantity():
    intent = _intent("买两本 400 块以内便宜点的 Python 书")
    decision = compare(search(intent), intent)
    assert decision["quantity"] == 2
    assert decision["total_price"] == decision["unit_price"] * 2
    assert "总价" in decision["reason"]
    assert decision["strategy"] == "price_first"
    assert decision["ranked_ids"][0] == decision["id"]

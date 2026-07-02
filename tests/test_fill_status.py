import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from create_appointments import classify_fill_status, missing_product_codes


def test_complete_when_subgrid_matches_planned():
    status, verified = classify_fill_status(planned=2, ok=2, subgrid_count=2)
    assert status == "complete"
    assert verified is True


def test_partial_when_subgrid_below_planned_even_if_flow_reported_ok():
    # 核心案例: 填寫流程沒報錯，但 CRM 實際只存進 1 筆 → 必須被抓出來
    status, verified = classify_fill_status(planned=2, ok=2, subgrid_count=1)
    assert status == "partial"
    assert verified is True


def test_subgrid_takes_priority_over_flow_failures():
    # 流程回報有失敗，但 subgrid 顯示數量足夠 (例如重試後其實存成功) → 以 CRM 為準
    status, verified = classify_fill_status(planned=2, ok=1, subgrid_count=2)
    assert status == "complete"
    assert verified is True


def test_falls_back_to_flow_results_when_subgrid_unreadable():
    status, verified = classify_fill_status(planned=2, ok=1, subgrid_count=None)
    assert status == "partial"
    assert verified is False

    status, verified = classify_fill_status(planned=2, ok=2, subgrid_count=None)
    assert status == "complete"
    assert verified is False


def test_no_planned_products_is_complete():
    status, verified = classify_fill_status(planned=0, ok=0, subgrid_count=None)
    assert status == "complete"
    assert verified is False


def test_missing_product_codes_lists_failed_only():
    results = [
        {"code": "ELI", "ok": True, "error": None},
        {"code": "ABC", "ok": False, "error": "儲存異常: timeout"},
        {"code": "XYZ", "ok": False, "error": "無法解析產品編號"},
    ]
    assert missing_product_codes(results) == ["ABC", "XYZ"]


def test_missing_product_codes_empty_when_all_ok():
    results = [
        {"code": "ELI", "ok": True, "error": None},
        {"code": "ABC", "ok": True, "error": None},
    ]
    assert missing_product_codes(results) == []

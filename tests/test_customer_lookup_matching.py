import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from create_appointments import choose_customer_candidate, customer_candidate_score
from visit_list_parser import VisitEntry


def _entry(**overrides):
    values = {
        "customer_name": "吳書雨",
        "hospital_name": "慈濟",
        "department_code": "URO",
        "department_name_zh": "泌尿科",
    }
    values.update(overrides)
    return VisitEntry(**values)


def test_customer_candidate_requires_name_and_hospital_when_available():
    entry = _entry()
    assert customer_candidate_score("吳書雨_HIN231004A_慈濟台北_泌尿外科", entry) == 140
    assert customer_candidate_score("吳書雨_HIN999999A_新光_泌尿外科", entry) is None
    assert customer_candidate_score("王小明_HIN231004A_慈濟台北_泌尿外科", entry) is None


def test_customer_candidate_accepts_name_only_when_input_has_no_hospital():
    entry = _entry(hospital_name="", department_code="OTHER", department_name_zh="其他")
    assert customer_candidate_score("吳書雨_HIN231004A_任意院所", entry) == 100


def test_choose_customer_candidate_uses_hospital_to_disambiguate_same_name():
    entry = _entry()
    candidates = [
        "吳書雨_HIN999999A_新光_泌尿外科",
        "吳書雨_HIN231004A_慈濟台北_泌尿外科",
    ]
    assert choose_customer_candidate(candidates, entry) == 1


def test_choose_customer_candidate_rejects_ambiguous_name_only_results():
    entry = _entry(hospital_name="", department_code="OTHER", department_name_zh="其他")
    with pytest.raises(ValueError, match="多筆相同候選"):
        choose_customer_candidate(["吳書雨_A", "吳書雨_B"], entry)


def test_choose_customer_candidate_accepts_identical_duplicate_results():
    entry = _entry()
    duplicate = "吳書雨_HIN231004A_慈濟台北_泌尿外科"
    assert choose_customer_candidate([duplicate, duplicate], entry) == 0


def test_choose_customer_candidate_ignores_duplicate_hidden_details():
    entry = _entry()
    title = "吳書雨_HIN231004A_慈濟台北_泌尿外科"
    assert choose_customer_candidate(
        [f"{title}\n擁有者甲", f"{title}\n擁有者乙"], entry
    ) == 0


def test_choose_customer_candidate_rejects_wrong_hospital():
    entry = _entry()
    with pytest.raises(ValueError, match="找不到符合客戶"):
        choose_customer_candidate(["吳書雨_HIN999999A_新光_泌尿外科"], entry)

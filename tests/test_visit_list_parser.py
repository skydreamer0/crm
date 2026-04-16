"""
Unit tests for visit_list_parser.py
"""
import pytest
import sys
from pathlib import Path

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from visit_list_parser import (
    parse_single_entry,
    parse_visit_list,
    select_products,
    VisitEntry,
)


# ── Standard format ──────────────────────────────────────────────────────────

class TestParseSingleEntry:

    def test_standard_format(self):
        e = parse_single_entry("慈濟/URO/吳書雨/B")
        assert e.customer_name == "吳書雨"
        assert e.department_code == "URO"
        assert e.department_name_zh == "泌尿科"

    def test_chinese_department(self):
        e = parse_single_entry("耕莘/泌尿科/王小明/A")
        assert e.customer_name == "王小明"
        assert e.department_code == "URO"

    def test_obs_department(self):
        e = parse_single_entry("慈濟/OBS/祝春紅/B")
        assert e.customer_name == "祝春紅"
        assert e.department_code == "OBS"
        assert e.department_name_zh == "婦產科"

    def test_ped_department(self):
        e = parse_single_entry("新光/PED/林小明/C")
        assert e.customer_name == "林小明"
        assert e.department_code == "PED"

    def test_fm_chinese(self):
        e = parse_single_entry("馬偕/家醫科/陳大華/A")
        assert e.customer_name == "陳大華"
        assert e.department_code == "FM"

    def test_missing_grade(self):
        """Grade is optional — should still parse fine."""
        e = parse_single_entry("慈濟/URO/吳書雨")
        assert e.customer_name == "吳書雨"
        assert e.department_code == "URO"

    def test_extra_tokens(self):
        """Extra info after grade — should still extract name + dept."""
        e = parse_single_entry("慈濟/URO/吳書雨/B/備註")
        assert e.customer_name == "吳書雨"
        assert e.department_code == "URO"

    def test_blank_line_returns_none(self):
        assert parse_single_entry("") is None
        assert parse_single_entry("   ") is None

    def test_lowercase_department(self):
        e = parse_single_entry("慈濟/uro/吳書雨/B")
        assert e.department_code == "URO"
        assert e.customer_name == "吳書雨"


# ── Multi-line parsing ───────────────────────────────────────────────────────

class TestParseVisitList:

    def test_multi_line(self):
        text = """慈濟/URO/吳書雨/B
耕莘/URO/姜秉均/A
慈濟/OBS/祝春紅/B"""
        entries = parse_visit_list(text)
        assert len(entries) == 3
        assert entries[0].customer_name == "吳書雨"
        assert entries[1].customer_name == "姜秉均"
        assert entries[2].customer_name == "祝春紅"

    def test_blank_lines_ignored(self):
        text = """慈濟/URO/吳書雨/B

慈濟/OBS/祝春紅/B
"""
        entries = parse_visit_list(text)
        assert len(entries) == 2


# ── Product matching ─────────────────────────────────────────────────────────

class TestProductMatching:

    def test_uro_products(self):
        e = parse_single_entry("慈濟/URO/吳書雨/B")
        assert e.matched_products == ["uri", "eli", "oxb"]

    def test_obs_products(self):
        e = parse_single_entry("慈濟/OBS/祝春紅/B")
        assert e.matched_products == ["ysl", "esv", "lmn", "oxb"]

    def test_ped_products(self):
        e = parse_single_entry("新光/PED/林小明/C")
        assert e.matched_products == ["eli", "oxb"]

    def test_fm_products(self):
        e = parse_single_entry("馬偕/FM/陳大華/A")
        assert e.matched_products == ["uri", "oxb"]

    def test_select_two_products(self):
        e = parse_single_entry("慈濟/URO/吳書雨/B")
        selected = select_products(e, count=2)
        assert len(selected) == 2
        assert selected == ["uri", "eli"]

class TestEligardRestriction:

    def test_eli_allowed_in_uro(self):
        e = VisitEntry(customer_name="Test", department_code="URO", matched_products=["uri", "eli", "oxb"])
        selected = select_products(e, count=3)
        assert "eli" in selected

    def test_eli_allowed_in_ped(self):
        e = VisitEntry(customer_name="Test", department_code="PED", matched_products=["eli", "oxb"])
        selected = select_products(e, count=2)
        assert "eli" in selected

    def test_eli_blocked_in_obs(self):
        # Even if 'eli' is manually added to matched_products for OBS, it should be filtered
        e = VisitEntry(customer_name="Test", department_code="OBS", matched_products=["ysl", "eli", "oxb"])
        selected = select_products(e, count=3)
        assert "eli" not in selected
        assert selected == ["ysl", "oxb"]

    def test_eli_blocked_in_fm(self):
        e = VisitEntry(customer_name="Test", department_code="FM", matched_products=["uri", "eli", "oxb"])
        selected = select_products(e, count=3)
        assert "eli" not in selected
        assert selected == ["uri", "oxb"]


# ── Edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_fullwidth_slash(self):
        """Full-width slash ／ as delimiter."""
        e = parse_single_entry("慈濟／URO／吳書雨／B")
        assert e.customer_name == "吳書雨"
        assert e.department_code == "URO"

    def test_chinese_dept_alias(self):
        """Use 婦產科 instead of OBS."""
        e = parse_single_entry("慈濟/婦產科/祝春紅/B")
        assert e.customer_name == "祝春紅"
        assert e.department_code == "OBS"

    def test_no_department(self):
        """Line without recognisable department."""
        e = parse_single_entry("慈濟/吳書雨/B")
        assert e.customer_name == "吳書雨"
        assert e.department_code == "OTHER"
        assert e.matched_products == ["uri", "oxb"]

    def test_raw_line_preserved(self):
        raw = "慈濟/URO/吳書雨/B"
        e = parse_single_entry(raw)
        assert e.raw_line == raw

    def test_fm_abbreviation(self):
        """Bug fix: '家醫' abbreviation should map to FM department."""
        e = parse_single_entry("新光/家醫/陳仲達/C")
        assert e.customer_name == "陳仲達"
        assert e.department_code == "FM"
        assert e.department_name_zh == "家醫科"

    def test_reverse_fuzzy_department(self):
        """Token shorter than alias should still match (bidirectional fuzzy)."""
        e = parse_single_entry("馬偕/家醫/王小明/A")
        assert e.department_code == "FM"
        assert e.matched_products == ["uri", "oxb"]

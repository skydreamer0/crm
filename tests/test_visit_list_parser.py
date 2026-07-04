"""
Unit tests for visit_list_parser.py
"""
import pytest
import sys
from pathlib import Path

# Ensure src/ is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from visit_list_parser import (
    apply_hospital_product_rules,
    collect_hospital_aliases,
    parse_single_entry,
    parse_visit_list,
    resolve_crm_product_id,
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

    def test_uro_uses_explicit_eli_sku_default(self):
        e = parse_single_entry("慈濟/URO/吳書雨/B")
        assert e.matched_products == ["uri", "eli_22_5", "oxb"]
        assert "eli" not in e.matched_products

    def test_obs_products(self):
        e = parse_single_entry("慈濟/OBS/祝春紅/B")
        assert e.matched_products == ["ysl", "esv", "lmn", "oxb"]

    def test_ped_uses_explicit_eli_45_default(self):
        e = parse_single_entry("新光/PED/林小明/C")
        assert e.matched_products == ["eli_45", "oxb"]

    def test_fm_products(self):
        e = parse_single_entry("馬偕/FM/陳大華/A")
        assert e.matched_products == ["uri", "oxb"]

    def test_select_two_products(self):
        e = parse_single_entry("慈濟/URO/吳書雨/B")
        selected = select_products(e, count=2)
        assert len(selected) == 2
        assert selected == ["uri", "eli_22_5"]

class TestEligardRestriction:

    def test_eli_allowed_in_uro(self):
        e = VisitEntry(customer_name="Test", department_code="URO", matched_products=["uri", "eli_22_5", "oxb"])
        selected = select_products(e, count=3)
        assert "eli_22_5" in selected

    def test_eli_allowed_in_ped(self):
        e = VisitEntry(customer_name="Test", department_code="PED", matched_products=["eli_45", "oxb"])
        selected = select_products(e, count=2)
        assert "eli_45" in selected

    def test_eli_blocked_in_obs(self):
        # Even if an ELI SKU is manually added to matched_products for OBS, it should be filtered
        e = VisitEntry(customer_name="Test", department_code="OBS", matched_products=["ysl", "eli_22_5", "oxb"])
        selected = select_products(e, count=3)
        assert "eli_22_5" not in selected
        assert selected == ["ysl", "oxb"]

    def test_eli_blocked_in_fm(self):
        e = VisitEntry(customer_name="Test", department_code="FM", matched_products=["uri", "eli_45", "oxb"])
        selected = select_products(e, count=3)
        assert "eli_45" not in selected
        assert selected == ["uri", "oxb"]

    def test_locked_rule_bypasses_eli_restriction(self):
        # 鎖定規則是使用者明確指定，不套 ELI 科別限制
        e = VisitEntry(
            customer_name="Test",
            department_code="OBS",
            hospital_name="新光",
            matched_products=["ysl", "esv"],
        )
        rules = {
            "skh": {
                "name": "新光醫院",
                "aliases": ["新光"],
                "departments": {
                    "OBS": {"mode": "locked", "products": ["eli_45"], "note": ""}
                },
            }
        }
        assert select_products(e, count=2, hospital_product_rules=rules) == ["eli_45"]


# ── Hospital extraction & locked rules ───────────────────────────────────────

HOSPITAL_RULES = {
    "skh": {
        "name": "新光醫院",
        "aliases": ["新光"],
        "departments": {
            "URO": {"mode": "locked", "products": ["uri", "eli_45"], "note": ""}
        },
    },
    "ak": {
        "name": "耕莘安康",
        "aliases": ["安康", "耕莘安康"],
        "departments": {
            "URO": {"mode": "locked", "products": ["uri"], "note": "只跑 Urief"}
        },
    },
    "cth": {
        "name": "耕莘永和",
        "aliases": ["耕莘"],
        "departments": {
            "URO": {"mode": "locked", "products": ["uri", "eli_22_5"], "note": ""}
        },
    },
}


class TestHospitalExtraction:

    def test_standard_format_extracts_hospital(self):
        e = parse_single_entry("慈濟/URO/吳書雨/B")
        assert e.hospital_name == "慈濟"

    def test_long_hospital_alias_wins(self):
        e = parse_single_entry("耕莘安康/URO/彭崇信/B")
        assert e.hospital_name == "耕莘安康"

    def test_unknown_hospital_defaults_empty(self):
        e = parse_single_entry("光田/URO/王小明/A")
        assert e.hospital_name == ""

    def test_extra_hospitals_prevent_name_misparse(self):
        # 使用者自訂醫院（不在內建清單）不應被誤判成客戶姓名
        e = parse_single_entry("光田/URO/王小明/A", extra_hospitals={"光田"})
        assert e.hospital_name == "光田"
        assert e.customer_name == "王小明"

    def test_collect_hospital_aliases(self):
        aliases = collect_hospital_aliases(HOSPITAL_RULES)
        assert {"新光醫院", "新光", "安康", "耕莘安康", "耕莘永和", "耕莘"} <= aliases


class TestLockedRules:

    def test_locked_hospital_department_rule_wins(self):
        e = parse_single_entry("新光/URO/蔡醫師/A")
        assert select_products(e, count=2, hospital_product_rules=HOSPITAL_RULES) == ["uri", "eli_45"]

    def test_fallback_used_when_no_rule(self):
        e = parse_single_entry("馬偕/URO/王小明/A")
        assert select_products(e, count=2, hospital_product_rules=HOSPITAL_RULES) == ["uri", "eli_22_5"]

    def test_longest_alias_wins_over_prefix(self):
        # 耕莘安康 應命中安康規則，而不是 耕莘(永和) 的規則
        e = parse_single_entry("耕莘安康/URO/彭崇信/B")
        assert select_products(e, count=2, hospital_product_rules=HOSPITAL_RULES) == ["uri"]

    def test_apply_rules_marks_entries_locked(self):
        entries = parse_visit_list("新光/URO/蔡醫師/A\n馬偕/URO/王小明/A")
        apply_hospital_product_rules(entries, HOSPITAL_RULES)
        assert entries[0].products_locked is True
        assert entries[0].matched_products == ["uri", "eli_45"]
        assert entries[1].products_locked is False
        assert entries[1].matched_products == ["uri", "eli_22_5", "oxb"]


class TestCrmProductIdResolution:

    def test_resolve_crm_product_id_uses_sku_directly(self):
        e = VisitEntry(customer_name="蔡醫師", department_code="URO", matched_products=["eli_45"])
        assert resolve_crm_product_id("eli_45", e) == "T5EL2"

    def test_each_eli_sku_has_fixed_id(self):
        e = VisitEntry(customer_name="任何人", department_code="OTHER")
        assert resolve_crm_product_id("eli_7_5", e) == "T5EL0"
        assert resolve_crm_product_id("eli_22_5", e) == "T5EL1"
        assert resolve_crm_product_id("uri", e) == "21363"

    def test_unknown_product_resolves_empty(self):
        e = VisitEntry(customer_name="任何人")
        assert resolve_crm_product_id("nope", e) == ""


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

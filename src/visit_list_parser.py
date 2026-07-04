"""
待訪名單解析器 — Visit List Parser
===================================

解析格式如:
    慈濟/URO/吳書雨/B
    耕莘/泌尿科/王小明/A

擷取:
    1. 客戶姓名 (最重要，用於 CRM 表單的拜訪對象欄位)
    2. 科別 (用於自動匹配應該展示的產品)

忽略: 醫院名稱、客戶等級

本模組被 app.py 與 create_appointments.py 共同使用。
"""
# === 標準庫 ===
import os
import random
import re
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# === 第三方套件 ===
import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def _resource_path(relative_path: str) -> Path:
    """Resolve files both from source and from a PyInstaller bundle."""
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        return Path(bundle_dir) / relative_path
    return Path(__file__).resolve().parent.parent / relative_path


_CONFIG_DIR = _resource_path("config")


def _load_yaml(filename: str) -> dict:
    filepath = _CONFIG_DIR / filename
    if not filepath.exists():
        logger.warning("Config file not found: %s", filepath)
        return {}
    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_department_map() -> dict:
    """
    Build lookup tables from department_mapping.yaml.

    Returns a dict keyed by normalised alias → {code, name_zh, products}.
    """
    raw = _load_yaml("department_mapping.yaml")
    lookup: dict[str, dict] = {}
    for code, info in raw.get("departments", {}).items():
        entry = {
            "code": code,
            "name_zh": info.get("name_zh", ""),
            "products": info.get("products", []),
        }
        # Index by code (case-insensitive)
        lookup[code.upper()] = entry
        lookup[code.lower()] = entry
        # Index by every alias (case-insensitive)
        for alias in info.get("aliases", []):
            lookup[alias.upper()] = entry
            lookup[alias.lower()] = entry
            lookup[alias] = entry
    return lookup


def load_product_catalog() -> dict:
    """Load product_catalog.yaml into a dict keyed by product code."""
    raw = _load_yaml("product_catalog.yaml")
    return raw.get("products", {})


# Module-level singletons (loaded once on import)
DEPARTMENT_MAP: dict = load_department_map()
PRODUCT_CATALOG: dict = load_product_catalog()
# Raw ordered department config (code → {name_zh, aliases, products}) for API listing
DEPARTMENT_CONFIG: dict = _load_yaml("department_mapping.yaml").get("departments", {})

# ---------------------------------------------------------------------------
# Known hospital names (used to exclude from name detection)
# ---------------------------------------------------------------------------

KNOWN_HOSPITALS = {
    "慈濟", "耕莘", "新光", "台大", "榮總", "北榮", "長庚", "馬偕",
    "三總", "國泰", "亞東", "雙和", "萬芳", "振興", "書田", "彰基",
    "義大", "奇美", "成大", "高醫", "中山", "署立", "聯合", "仁愛",
    "台北慈濟", "花蓮慈濟", "大林慈濟", "台中慈濟",
    "新光醫院", "耕莘醫院", "台大醫院", "榮總醫院",
    "Cardinal Tien", "Shin Kong", "Tzu Chi", "永耕",
    # 分院 / 院區
    "耕莘安康", "安康", "安康院區", "耕莘安康院區",
}

# Pre-compiled: matches 2-4 consecutive CJK characters (typical Chinese name)
_CJK_NAME_RE = re.compile(r"^[\u4e00-\u9fff]{2,4}$")

# Single-character grade tokens to ignore
_GRADE_RE = re.compile(r"^[A-Ea-e]$")

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class VisitEntry:
    """Parsed result from a single visit-list line."""
    customer_name: str
    department_code: str = ""
    department_name_zh: str = ""
    matched_products: list[str] = field(default_factory=list)
    raw_line: str = ""
    hospital_name: str = ""
    # True when matched_products comes from a hospital+department locked rule
    products_locked: bool = False


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _normalise_token(token: str) -> str:
    """Strip whitespace and common punctuation."""
    return token.strip().strip(".,;:!?，。；：")


def _identify_department(token: str) -> Optional[dict]:
    """Try to match a token to a known department."""
    normed = _normalise_token(token)
    # Direct lookup (case-insensitive)
    hit = DEPARTMENT_MAP.get(normed) or DEPARTMENT_MAP.get(normed.upper())
    if hit:
        return hit

    # Fuzzy: check if the token *contains* a known alias (e.g. "泌尿外科URO")
    # Also check if a known alias *contains* the token (e.g. "家醫" → "家醫科")
    for key, val in DEPARTMENT_MAP.items():
        if len(key) >= 2 and (key in normed or (len(normed) >= 2 and normed in key)):
            return val

    return None

# 常見醫學科別關鍵字 (即使未收錄在 department_mapping 裡，也不應被當成姓名)
_DEPT_KEYWORDS = {
    "科", "內科", "外科", "神內", "神外", "心內", "心外",
    "胸腔", "腎臟", "感染", "腫瘤", "血液", "風濕", "復健",
    "放射", "急診", "麻醉", "骨科", "皮膚", "眼科", "耳鼻",
    "牙科", "精神", "整形", "肝膽", "腸胃", "直腸", "胃腸",
    "新陳代謝", "內分泌", "神經", "心臟", "胸外", "一般外",
}


def _is_chinese_name(token: str, hospitals: set[str] | None = None) -> bool:
    """Heuristic: a 2-4 CJK character string that isn't a hospital or dept."""
    normed = _normalise_token(token)
    if not _CJK_NAME_RE.match(normed):
        return False
    if normed in (hospitals or KNOWN_HOSPITALS):
        return False
    if DEPARTMENT_MAP.get(normed):
        return False
    # 排除看似科別名稱的 token (例如 "神內", "骨科", "心內")
    if normed in _DEPT_KEYWORDS:
        return False
    # 包含「科」的 token 幾乎都是科別而非人名
    if "科" in normed:
        return False
    return True


def parse_single_entry(line: str, extra_hospitals: Optional[set[str]] = None) -> Optional[VisitEntry]:
    """
    Parse a single line like '慈濟/URO/吳書雨/B' or '永耕/URO/楊弘如/A08:30'.

    `extra_hospitals` 補充使用者自訂的醫院名稱/別名（來自 hospital_product_rules），
    讓自訂醫院不會被誤判成客戶姓名。

    Returns a VisitEntry with customer_name and department info,
    or None if the line is blank / unparseable.
    """
    hospitals = KNOWN_HOSPITALS | (extra_hospitals or set())
    line = line.strip()
    if not line:
        return None

    # 過濾掉可能是表格標題列的文字
    if "醫院" in line and ("科別" in line or "客戶" in line):
        logger.info(f"  ⏭️ 忽略標題列: {line}")
        return None

    # 清理時間標記 (例如 08:30, 14:00)
    # 把類似 HH:MM 的格式直接移除
    line = re.sub(r"\d{1,2}:\d{2}", "", line)

    # Split by common delimiters
    tokens = re.split(r"[/／、\t]+", line)
    tokens = [_normalise_token(t) for t in tokens if _normalise_token(t)]

    customer_name: str = ""
    hospital_name: str = ""
    dept_info: Optional[dict] = None

    # Pass 0: identify hospital (longest matching token wins, e.g. 耕莘安康 > 耕莘)
    for token in tokens:
        normed = _normalise_token(token)
        if normed in hospitals and len(normed) > len(hospital_name):
            hospital_name = normed

    # Pass 1: identify department
    for token in tokens:
        found = _identify_department(token)
        if found:
            dept_info = found
            break

    # Pass 2: identify customer name
    #   Priority: first CJK 2-4 char token that isn't hospital/dept
    for token in tokens:
        if _is_chinese_name(token, hospitals):
            customer_name = token
            break

    # Fallback: if no CJK name found, pick a non-dept / non-hospital /
    # non-grade token
    if not customer_name:
        for token in tokens:
            normed = _normalise_token(token)
            if _GRADE_RE.match(normed):
                continue
            if normed in hospitals:
                continue
            if _identify_department(normed):
                continue
            if normed:
                customer_name = normed
                break

    # Still nothing? Use full line
    if not customer_name:
        customer_name = line

    entry = VisitEntry(
        customer_name=customer_name,
        raw_line=line,
        hospital_name=hospital_name,
    )

    if dept_info:
        entry.department_code = dept_info["code"]
        entry.department_name_zh = dept_info["name_zh"]
        entry.matched_products = list(dept_info["products"])
    else:
        # 未知科別 (神內、其他未建檔科別等) → 預設帶入 uri + oxb
        entry.department_code = "OTHER"
        entry.department_name_zh = "其他"
        entry.matched_products = ["uri", "oxb"]
        logger.info("  ℹ️ 未匹配到已知科別，預設帶入產品: [uri, oxb]")

    return entry


def parse_visit_list(text: str, extra_hospitals: Optional[set[str]] = None) -> list[VisitEntry]:
    """
    Parse multi-line visit list text into structured entries.

    Example input:
        慈濟/URO/吳書雨/B
        耕莘/URO/姜秉均/A
        慈濟/OBS/祝春紅/B

    Returns a list of VisitEntry objects.
    """
    entries: list[VisitEntry] = []
    for line in text.strip().splitlines():
        entry = parse_single_entry(line, extra_hospitals=extra_hospitals)
        if entry:
            entries.append(entry)
            logger.info(
                "  ✅ 解析: %s → 姓名=%s, 科別=%s(%s), 產品=%s",
                entry.raw_line,
                entry.customer_name,
                entry.department_code,
                entry.department_name_zh,
                entry.matched_products,
            )
    logger.info("共解析 %d 筆待訪名單", len(entries))
    return entries


# ---------------------------------------------------------------------------
# Hospital+department product rules (per-user settings)
# ---------------------------------------------------------------------------


def collect_hospital_aliases(hospital_product_rules: Optional[dict]) -> set[str]:
    """Collect all hospital names and aliases from user rules (for parsing)."""
    aliases: set[str] = set()
    for hospital in (hospital_product_rules or {}).values():
        if not isinstance(hospital, dict):
            continue
        name = str(hospital.get("name") or "").strip()
        if name:
            aliases.add(name)
        for alias in hospital.get("aliases") or []:
            alias = str(alias or "").strip()
            if alias:
                aliases.add(alias)
    return aliases


def find_hospital_department_rule(entry: VisitEntry, hospital_product_rules: dict) -> Optional[dict]:
    """
    Find the rule for this entry's hospital+department.

    醫院比對：規則的 name/aliases 與 entry.hospital_name 完全相等，
    或 alias 是 hospital_name 的一部分（如 安康 ⊂ 耕莘安康院區）。
    多間醫院命中時取最長的 alias（耕莘安康 勝過 耕莘）。
    """
    if not hospital_product_rules or not entry.department_code:
        return None

    haystack = entry.hospital_name or ""
    best: Optional[dict] = None
    best_len = 0
    for hospital in hospital_product_rules.values():
        if not isinstance(hospital, dict):
            continue
        candidates = [str(hospital.get("name") or "")] + [
            str(a or "") for a in (hospital.get("aliases") or [])
        ]
        for alias in candidates:
            alias = alias.strip()
            if not alias:
                continue
            hit = alias == haystack or (haystack and alias in haystack) \
                or (not haystack and alias in entry.raw_line)
            if hit and len(alias) > best_len:
                best = hospital
                best_len = len(alias)

    if not best:
        return None
    departments = best.get("departments")
    if not isinstance(departments, dict):
        return None
    rule = departments.get(entry.department_code)
    return rule if isinstance(rule, dict) else None


def resolve_matched_products(
    entry: VisitEntry,
    hospital_product_rules: Optional[dict] = None,
) -> tuple[list[str], bool]:
    """
    Resolve the product list for an entry.

    Returns (products, locked)。locked=True 表示命中鎖定規則，
    產品清單必須原樣使用（不做 ELI 科別過濾）。
    """
    rule = find_hospital_department_rule(entry, hospital_product_rules or {})
    if rule and rule.get("mode") == "locked":
        return [str(p) for p in (rule.get("products") or [])], True
    return list(entry.matched_products), False


def apply_hospital_product_rules(
    entries: list[VisitEntry],
    hospital_product_rules: Optional[dict],
) -> list[VisitEntry]:
    """
    Apply locked hospital rules onto parsed entries (in place).

    在 parse 之後呼叫一次，之後所有下游（預覽/自動化）都用同一份結果。
    """
    if not hospital_product_rules:
        return entries
    for entry in entries:
        products, locked = resolve_matched_products(entry, hospital_product_rules)
        if locked:
            entry.matched_products = products
            entry.products_locked = True
            logger.info(
                "  🔒 套用鎖定規則: %s(%s) → %s",
                entry.hospital_name or entry.customer_name,
                entry.department_code,
                products,
            )
    return entries


# ---------------------------------------------------------------------------
# Convenience: auto-select 2 products from matched list
# ---------------------------------------------------------------------------


def _is_eli(product_code: str) -> bool:
    return product_code == "eli" or product_code.startswith("eli_")


def select_products(
    entry: VisitEntry,
    count: int = 2,
    hospital_product_rules: Optional[dict] = None,
) -> list[str]:
    """
    From an entry's matched_products, select up to `count` products.
    Returns product codes (e.g. ['uri', 'eli_22_5']).

    Hard Rule: ELIGARD (eli_*) only allowed for URO (Urology) and PED (Pediatrics),
    除非產品清單來自醫院鎖定規則（使用者明確指定）。
    """
    products, locked = resolve_matched_products(entry, hospital_product_rules)
    if locked or entry.products_locked:
        return products[:count]

    filtered = []
    for p in products:
        if _is_eli(p) and entry.department_code not in ["URO", "PED"]:
            continue
        filtered.append(p)
    return filtered[:count]


def get_product_info(product_code: str) -> dict:
    """
    Look up product details from product_catalog.yaml.
    Returns dict with brand_name, generic_name, descriptions (list).
    """
    return PRODUCT_CATALOG.get(product_code, {})


def resolve_crm_product_id(product_code: str, entry: VisitEntry) -> str:
    """
    Resolve the CRM Product ID (e.g., '21363' or 'T5EL2') for a SKU code.

    每個 SKU（含 Eligard 各劑量）都有固定編號，不再依醫院/科別動態判定；
    醫院差異改由 hospital_product_rules 鎖定 SKU 本身。
    """
    info = get_product_info(product_code)
    pid = str(info.get("crm_product_id", "") or "")
    return pid if pid != "DYNAMIC" else ""

def should_skip_visit_content(product_code: str) -> bool:
    """Check if the product should skip the Visit Content field."""
    info = get_product_info(product_code)
    return bool(info.get("skip_visit_content", False))


def get_random_description(product_code: str) -> str:
    """
    Randomly select one description from the product's list.
    """
    info = get_product_info(product_code)
    descs = info.get("descriptions", [])
    if not descs:
        return ""
    return random.choice(descs)


# ---------------------------------------------------------------------------
# CLI for quick testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    sample = """慈濟/URO/吳書雨/B
耕莘/URO/姜秉均/A
慈濟/OBS/祝春紅/B
新光/PED/林小明/C
馬偕/家醫科/陳大華/A"""

    text = sys.stdin.read() if not sys.stdin.isatty() else sample
    results = parse_visit_list(text)

    print("\n" + "=" * 60)
    for e in results:
        products = select_products(e)
        product_details = [get_product_info(p) for p in products]
        print(f"拜訪對象: {e.customer_name}")
        print(f"  科別: {e.department_code} ({e.department_name_zh})")
        print(f"  匹配產品: {products}")
        for p_code, p_info in zip(products, product_details):
            brand = p_info.get("brand_name", p_code)
            print(f"    → {p_code}: {brand}")
        print()

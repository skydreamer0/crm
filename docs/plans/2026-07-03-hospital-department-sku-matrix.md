# Hospital Department SKU Matrix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a settings flow where each hospital and department can lock the exact product SKUs the CRM automation will create.

**Architecture:** Treat product SKU codes as the smallest selectable unit, with CRM product IDs attached directly to those SKUs. Resolve products by first checking a hospital+department locked rule, then falling back to department defaults when no lock exists. Use the selected Variant B matrix UI as the primary settings surface because it makes gaps, locks, and fallback rules easy to scan.

**Tech Stack:** Flask, plain HTML/CSS/JavaScript templates, JSON per-user settings in `settings_store.py`, YAML seed config in `config/`, pytest.

---

## Chosen Direction

Use the **Variant B matrix** now mounted at `/settings/products` from `src/templates/product_rules.html`.

The production settings page should show hospitals as rows and departments as columns. Each cell shows:

- `Locked` or `Fallback`
- the exact selected SKU chips
- a short note or warning when no SKU is available

Clicking a cell opens an editor for that hospital+department rule.

## Data Model

### Product Catalog

Move from brand-level ELI selection to SKU-level selection.

```yaml
products:
  eli_7_5:
    family: eli
    brand_name: ELI 7.5
    display_name: Eligard 7.5 一個月劑量
    crm_product_id: T5EL0
    dose_label: 1個月 / 7.5mg

  eli_22_5:
    family: eli
    brand_name: ELI 22.5
    display_name: Eligard 22.5 三個月劑量
    crm_product_id: T5EL1
    dose_label: 3個月 / 22.5mg

  eli_45:
    family: eli
    brand_name: ELI 45
    display_name: Eligard 45 六個月劑量
    crm_product_id: T5EL2
    dose_label: 6個月 / 45mg
```

### Hospital Rules

Store user-editable rules in the per-user settings JSON.

```json
{
  "hospital_product_rules": {
    "skh": {
      "name": "新光醫院",
      "aliases": ["新光", "新光醫院"],
      "departments": {
        "URO": {
          "mode": "locked",
          "products": ["uri", "eli_45"],
          "note": "院內主跑六個月劑量"
        }
      }
    }
  }
}
```

`mode: locked` means the resolver must use only the listed SKU codes. It must not replace one Eligard dose with another.

## Task 1: Convert ELI to Explicit SKU Catalog Entries

**Files:**
- Modify: `config/product_catalog.yaml`
- Modify: `config/department_mapping.yaml`
- Test: `tests/test_visit_list_parser.py`

**Step 1: Write failing tests**

Add assertions that department defaults return explicit SKU codes:

```python
def test_uro_uses_explicit_eli_sku_default():
    e = parse_single_entry("慈濟/URO/吳書雨/B")
    assert "eli_22_5" in e.matched_products
    assert "eli" not in e.matched_products

def test_ped_uses_explicit_eli_45_default():
    e = parse_single_entry("新光/PED/林小明/C")
    assert e.matched_products == ["eli_45", "oxb"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_visit_list_parser.py -v`

Expected: FAIL because current defaults still use `eli`.

**Step 3: Update YAML**

- Replace `eli` with `eli_7_5`, `eli_22_5`, `eli_45`.
- Keep product descriptions on the ELI SKU entries, duplicating the current ELI descriptions for now.
- Remove `crm_product_id: DYNAMIC` and `crm_dynamic_rules`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_visit_list_parser.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add config/product_catalog.yaml config/department_mapping.yaml tests/test_visit_list_parser.py
git commit -m "feat(products): split Eligard into SKU entries"
```

## Task 2: Parse Hospital as a First-Class Field

**Files:**
- Modify: `src/visit_list_parser.py`
- Test: `tests/test_visit_list_parser.py`

**Step 1: Write failing tests**

```python
def test_standard_format_extracts_hospital():
    e = parse_single_entry("慈濟/URO/吳書雨/B")
    assert e.hospital_name == "慈濟"

def test_long_hospital_alias_wins():
    e = parse_single_entry("耕莘安康/URO/彭崇信/B")
    assert e.hospital_name == "耕莘安康"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_visit_list_parser.py -v`

Expected: FAIL because `VisitEntry` has no `hospital_name`.

**Step 3: Implement minimal parser change**

Add fields:

```python
hospital_name: str = ""
hospital_alias: str = ""
```

For four-part slash-delimited rows, treat token 1 as hospital, token 2 as department, token 3 as customer. Keep the existing heuristic path for incomplete rows.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_visit_list_parser.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/visit_list_parser.py tests/test_visit_list_parser.py
git commit -m "feat(parser): extract hospital from visit rows"
```

## Task 3: Add Hospital Product Rules to Settings Store

**Files:**
- Modify: `src/settings_store.py`
- Test: `tests/test_settings_store.py`

**Step 1: Write failing tests**

```python
def test_save_settings_persists_hospital_product_rules():
    public = save_settings({
        "crm_base_url": "https://crm.example.test",
        "crm_username": "alice",
        "crm_password": "secret",
        "hospital_product_rules": {
            "skh": {
                "name": "新光醫院",
                "aliases": ["新光"],
                "departments": {
                    "URO": {"mode": "locked", "products": ["uri", "eli_45"], "note": ""}
                },
            }
        },
    })
    assert public["hospital_product_rules"]["skh"]["departments"]["URO"]["products"] == ["uri", "eli_45"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_settings_store.py -v`

Expected: FAIL because settings currently drops unknown product-rule fields.

**Step 3: Implement settings persistence**

- Preserve existing CRM credential behavior.
- Add `hospital_product_rules` to saved raw JSON.
- Validate shape enough to avoid crashes:
  - top-level must be dict
  - hospital entries must be dict
  - departments must be dict
  - products must be a list of strings
  - unknown modes become `fallback`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_settings_store.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/settings_store.py tests/test_settings_store.py
git commit -m "feat(settings): persist hospital SKU rules"
```

## Task 4: Resolve Products by Locked Rule then Fallback

**Files:**
- Modify: `src/visit_list_parser.py`
- Modify: `src/app.py`
- Test: `tests/test_visit_list_parser.py`
- Test: `tests/test_settings_api.py`

**Step 1: Write failing tests**

```python
def test_locked_hospital_department_rule_wins():
    e = parse_single_entry("新光/URO/蔡醫師/A")
    rules = {
        "skh": {
            "name": "新光醫院",
            "aliases": ["新光"],
            "departments": {
                "URO": {"mode": "locked", "products": ["uri", "eli_45"], "note": ""}
            },
        }
    }
    assert select_products(e, count=2, hospital_product_rules=rules) == ["uri", "eli_45"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_visit_list_parser.py -v`

Expected: FAIL because `select_products` has no rules argument.

**Step 3: Implement resolver**

Add a small resolver function:

```python
def resolve_matched_products(entry, hospital_product_rules=None):
    rule = find_hospital_department_rule(entry, hospital_product_rules or {})
    if rule and rule.get("mode") == "locked":
        return list(rule.get("products", []))
    return list(entry.matched_products)
```

Then let `select_products` call this before count trimming.

**Step 4: Wire API preview**

In `/api/parse`, load `get_effective_settings()` and pass `hospital_product_rules` into selection so the preview shows the real SKU result.

**Step 5: Run tests**

Run: `pytest tests/test_visit_list_parser.py tests/test_settings_api.py -v`

Expected: PASS.

**Step 6: Commit**

```bash
git add src/visit_list_parser.py src/app.py tests/test_visit_list_parser.py tests/test_settings_api.py
git commit -m "feat(products): resolve locked hospital SKU rules"
```

## Task 5: Build the Production Matrix Settings UI

**Files:**
- Modify: `src/templates/settings.html`
- Modify: `src/app.py`
- Test: `tests/test_settings_api.py`

**Step 1: Write failing API/page tests**

```python
def test_settings_page_includes_hospital_product_matrix(client):
    html = client.get("/settings").get_data(as_text=True)
    assert "hospitalProductMatrix" in html
    assert "Eligard 45" in html
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_settings_api.py -v`

Expected: FAIL because the settings page only has CRM credentials today.

**Step 3: Implement matrix UI from Variant B**

Use `src/templates/product_rules.html` as the production matrix surface:

- Keep the existing CRM credentials section.
- Add a `hospitalProductMatrix` section.
- Render hospitals as rows and departments as columns.
- Add cell editor controls:
  - mode selector: `fallback` / `locked`
  - SKU checkbox list
  - note text input
- Save through `/api/settings`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_settings_api.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/templates/settings.html src/app.py tests/test_settings_api.py
git commit -m "feat(settings): add hospital SKU matrix"
```

## Task 6: Use Resolved SKU IDs in CRM Automation

**Files:**
- Modify: `src/create_appointments.py`
- Modify: `src/visit_list_parser.py`
- Test: `tests/test_automation_settings.py`
- Test: `tests/test_visit_list_parser.py`

**Step 1: Write failing tests**

```python
def test_resolve_crm_product_id_uses_sku_directly():
    e = VisitEntry(customer_name="蔡醫師", department_code="URO", matched_products=["eli_45"])
    assert resolve_crm_product_id("eli_45", e) == "T5EL2"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_visit_list_parser.py -v`

Expected: FAIL until catalog and resolver use SKU IDs directly.

**Step 3: Remove dynamic ELI dependency**

- Keep `resolve_crm_product_id` simple: return `crm_product_id` for the SKU.
- Do not inspect hospital or department to change ELI dose.
- Pass effective settings into product selection before automation starts.

**Step 4: Run tests**

Run: `pytest tests/test_visit_list_parser.py tests/test_automation_settings.py -v`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/create_appointments.py src/visit_list_parser.py tests/test_automation_settings.py tests/test_visit_list_parser.py
git commit -m "feat(automation): use locked SKU product IDs"
```

## Task 7: End-to-End Verification and Cleanup

**Files:**
- Modify as needed from prior tasks.
- Keep `src/templates/product_rules.html` as the matrix settings surface.

**Step 1: Run focused tests**

Run:

```bash
pytest tests/test_visit_list_parser.py tests/test_settings_store.py tests/test_settings_api.py tests/test_automation_settings.py -v
```

Expected: PASS.

**Step 2: Run full test suite**

Run:

```bash
pytest
```

Expected: PASS.

**Step 3: Manual browser check**

Run:

```bash
python src/app.py
```

Open `/settings` and verify:

- Matrix rows show hospitals.
- Matrix columns show departments.
- New ELI SKU chips appear separately.
- A locked cell previews exact CRM product IDs.
- `/api/parse` preview matches the locked cell.

**Step 4: Commit final cleanup**

```bash
git add .
git commit -m "chore: finalize hospital SKU matrix rollout"
```

## Acceptance Criteria

- Product selection is SKU-based.
- ELI dose never changes unless the selected SKU changes.
- Hospital+department locked rules override department defaults.
- Missing or fallback rules still use department defaults.
- Settings page uses the Variant B matrix layout.
- Preview and automation use the same resolved SKU list.
- Tests cover parser, settings persistence, API preview, and automation product ID resolution.

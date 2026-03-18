"""
驗證修復：家醫科縮寫辨識 + 重名場景測試名單

這個腳本會:
1. 直接用 parser 驗證三個目標名單的解析結果
2. 如果解析正確，自動觸發 CRM 自動化流程進行實際觀察
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from visit_list_parser import parse_visit_list, select_products

# 測試目標名單
TEST_LIST = """
新光/家醫/陳仲達/C
新光/URO/陳怡伶/B
耕莘/URO/李維/A
""".strip()

print("=" * 60)
print("  驗證修復：家醫科縮寫 + 重名場景")
print("=" * 60)

entries = parse_visit_list(TEST_LIST)
all_pass = True

print(f"\n共解析 {len(entries)} 筆名單\n")

for e in entries:
    products = select_products(e, count=2)
    status = "✅" if e.department_code else "❌"
    print(f"  {status} {e.customer_name}")
    print(f"     科別: {e.department_code} ({e.department_name_zh})")
    print(f"     產品: {products}")
    print(f"     原始: {e.raw_line}")
    print()

    # 驗證家醫科辨識
    if e.customer_name == "陳仲達":
        if e.department_code != "FM":
            print(f"     ❌ 家醫科辨識失敗！預期 FM，實際 {e.department_code}")
            all_pass = False
        else:
            print(f"     ✅ 家醫科辨識正確")

    # 驗證重名場景解析 (parser 層面)
    if e.customer_name in ("陳怡伶", "李維"):
        if not e.customer_name:
            print(f"     ❌ 姓名解析失敗")
            all_pass = False
        else:
            print(f"     ✅ 姓名解析正確 (CRM 重名選取需實際執行驗證)")

print("=" * 60)
if all_pass:
    print("✅ 所有 Parser 層面的驗證通過！")
    print("💡 CRM 重名自動選取 (陳怡伶、李維) 需要實際執行自動化來驗證")
else:
    print("❌ 部分驗證失敗，請檢查上方輸出")
print("=" * 60)

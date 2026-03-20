from bs4 import BeautifulSoup

with open("docs/html_dumps/new_daily_report_form.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

print("--- 所有 Label 與其對應的 Input ID ---")
for label in soup.find_all("label"):
    text = label.get_text(strip=True)
    if text:
        target = label.get('for', 'No-For')
        print(f"[{text}] -> {target}")

print("\n--- 所有 Select 選單 (下拉式) ---")
for select in soup.find_all("select"):
    print(f"Select ID: {select.get('id')}")

print("\n--- 所有 Input 欄位 ---")
for input_tag in soup.find_all("input"):
    if input_tag.get('type') not in ['hidden']:
        print(f"Input Name: {input_tag.get('name')}, ID: {input_tag.get('id')}, Type: {input_tag.get('type')}")

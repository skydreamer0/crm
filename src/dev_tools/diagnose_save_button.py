"""
CRM 儲存按鈕診斷腳本 (Save Button Diagnostic)
================================================

目的：登入 CRM → 開日報 → 開約會 Popup → dump Ribbon HTML & 截圖
用來找出儲存按鈕的正確選擇器。

執行方式：
  cd c:\\Users\\User\\Documents\\project_work\\crm
  python src/dev_tools/diagnose_save_button.py
"""
import asyncio
import os
import sys
from pathlib import Path

# Windows cp950 無法印 emoji，強制 UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from playwright.async_api import async_playwright

# 載入設定
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "logs" / "diagnostics"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


async def dump_ribbon_info(page, label: str):
    """把頁面中 Ribbon 區域的 HTML dump 出來，並截圖"""
    print(f"\n{'='*60}")
    print(f"  [{label}] 開始診斷 Ribbon / 儲存按鈕")
    print(f"{'='*60}")

    # 截圖
    screenshot_path = OUTPUT_DIR / f"{label}_full.png"
    await page.screenshot(path=str(screenshot_path), full_page=False)
    print(f"  📸 完整截圖: {screenshot_path}")

    # --- 1. 搜尋所有可能的儲存相關元素 ---
    selectors_to_check = [
        # 常見 CRM 2013/2015 儲存按鈕
        ("img.ms-crm-ImageStrip-Save_16", "Save icon (CRM 2013)"),
        ("img.ms-crm-ImageStrip-SaveAndClose_16", "SaveAndClose icon (CRM 2013)"),
        ("li[id*='SavePrimary']", "Save li (Primary)"),
        ("li[id*='SaveAndClosePrimary']", "SaveAndClose li (Primary)"),
        ("li#TabHomeSave", "TabHomeSave li"),
        ("li#TabHomeSaveAndClose", "TabHomeSaveAndClose li"),
        ("span[command='save']", "span command=save"),
        ("span[command='saveandclose']", "span command=saveandclose"),
        ("button[data-id='edit-save-status-btn']", "button data-id save"),
        # 更廣泛的搜尋
        ("img[src*='Save']", "Any img with Save in src"),
        ("img[title*='存']", "Any img with 存 in title"),
        ("a[title*='存']", "Any a with 存 in title"),
        ("span[title*='存']", "Any span with 存 in title"),
        ("li[title*='存']", "Any li with 存 in title"),
        ("button[title*='存']", "Any button with 存 in title"),
        # Ribbon 區域
        ("ul[id*='Mscrm.Form']", "Ribbon UL container"),
        ("div#crmRibbon", "CRM Ribbon div"),
        ("div[id*='ribbon']", "Any ribbon div (case-sensitive)"),
        ("div[id*='Ribbon']", "Any Ribbon div"),
    ]

    print(f"\n  --- 搜尋儲存相關元素 ---")
    found_any = False
    for selector, desc in selectors_to_check:
        try:
            elements = await page.query_selector_all(selector)
            if elements:
                found_any = True
                for i, el in enumerate(elements):
                    visible = await el.is_visible()
                    tag = await el.evaluate("e => e.tagName")
                    outer_html = await el.evaluate("e => e.outerHTML.substring(0, 300)")
                    print(f"  ✅ [{desc}] #{i} | visible={visible} | <{tag}>")
                    print(f"     HTML: {outer_html}")
                    print()
        except Exception as e:
            pass  # 選擇器不合法或其他問題，跳過

    if not found_any:
        print("  ❌ 在 page 層級完全找不到任何儲存相關元素！")

    # --- 2. 把整個 Ribbon 區域的 HTML dump 出來 ---
    print(f"\n  --- Dump 頁面頂部 Ribbon HTML ---")
    try:
        # 嘗試抓取整個 Ribbon 區域
        ribbon_html = await page.evaluate("""() => {
            // 嘗試各種可能的 Ribbon 容器
            const candidates = [
                document.getElementById('crmRibbon'),
                document.getElementById('TabHome'),
                document.querySelector('[id*="ribbon"]'),
                document.querySelector('[id*="Ribbon"]'),
                document.querySelector('ul.ms-crm-CommandBar-Menu'),
                document.querySelector('div.ms-crm-CommandBar'),
            ];
            for (const el of candidates) {
                if (el) return el.outerHTML.substring(0, 5000);
            }
            
            // 找不到特定容器，dump body 前 3000 字元
            return '(No ribbon container found) Body preview: ' + document.body.innerHTML.substring(0, 3000);
        }""")
        # 寫入檔案
        html_path = OUTPUT_DIR / f"{label}_ribbon.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(ribbon_html)
        print(f"  📄 Ribbon HTML 已存至: {html_path}")
        # 也印出前 1500 字元
        print(f"  Preview (前 1500 字):\n{ribbon_html[:1500]}")
    except Exception as e:
        print(f"  ⚠️ Dump Ribbon HTML 失敗: {e}")

    # --- 3. 列出頁面中所有 iframe ---
    print(f"\n  --- 列出所有 iframe ---")
    try:
        iframes = await page.query_selector_all("iframe")
        for i, iframe in enumerate(iframes):
            iframe_id = await iframe.get_attribute("id") or "(no id)"
            iframe_src = await iframe.get_attribute("src") or "(no src)"
            visible = await iframe.is_visible()
            print(f"  iframe #{i}: id={iframe_id} | visible={visible} | src={iframe_src[:80]}")
    except Exception as e:
        print(f"  ⚠️ 列出 iframe 失敗: {e}")


async def main():
    username = os.getenv("CRM_USERNAME")
    password = os.getenv("CRM_PASSWORD")
    base_url = os.getenv("CRM_BASE_URL", "https://crm.synmosa.com.tw/SYNCRM/main.aspx")

    print("🔍 CRM 儲存按鈕診斷工具")
    print(f"   Base URL: {base_url}")
    print(f"   Output: {OUTPUT_DIR}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            http_credentials={"username": username, "password": password}
        )
        page = await context.new_page()

        # === Step 1: 登入 ===
        print("\n📌 Step 1: 登入 CRM...")
        full_url = base_url.rstrip('/') + '/SYNCRM/main.aspx' if '/SYNCRM' not in base_url else base_url
        await page.goto(full_url, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)
        print("  ✅ 登入完成")

        # === Step 2: 開新日報 ===
        print("\n📌 Step 2: 開新日報表單...")
        host_url = base_url.split('/SYNCRM')[0] if '/SYNCRM' in base_url else base_url.rstrip('/')
        new_report_url = f"{host_url}/SYNCRM/main.aspx?etn=new_dailyreport&pagetype=entityrecord"
        await page.goto(new_report_url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        # 診斷日報頁面的儲存按鈕
        await dump_ribbon_info(page, "daily_report")

        # === Step 3: 儲存日報 (用 Ctrl+S 確保存得下) ===
        print("\n📌 Step 3: 嘗試儲存日報 (Ctrl+S)...")
        # 先填時間
        try:
            iframe_el = await page.wait_for_selector("iframe#contentIFrame0", timeout=10000)
            frame = await iframe_el.content_frame()
            if frame:
                date_input = await frame.query_selector("input#DateInput")
                if date_input:
                    await date_input.click()
                    await page.keyboard.press("Tab")
                    await page.wait_for_timeout(500)
                    await page.keyboard.press("Tab")
                    await page.wait_for_timeout(500)
                    await page.keyboard.insert_text("09:00")
                    await page.keyboard.press("Tab")
                    await page.wait_for_timeout(500)
                    await page.keyboard.insert_text("18:00")
                    await page.keyboard.press("Tab")
                    await page.wait_for_timeout(500)
        except Exception as e:
            print(f"  ⚠️ 填寫日報時間失敗: {e}")

        await page.keyboard.press("Control+s")
        await page.wait_for_timeout(5000)
        print("  ✅ 日報儲存完成 (Ctrl+S)")

        # === Step 4: 開約會 Popup ===
        print("\n📌 Step 4: 開約會 Popup...")
        # 找新增約會按鈕
        add_btn = None
        try:
            iframe_el = await page.wait_for_selector("iframe#contentIFrame0", timeout=10000)
            frame = await iframe_el.content_frame()
            if frame:
                for sel in ["img#details_addImageButtonImage", 'img[title*="新增 約會"]', "img.ms-crm-add-button-icon"]:
                    elements = await frame.query_selector_all(sel)
                    for el in elements:
                        if await el.is_visible():
                            add_btn = el
                            break
                    if add_btn:
                        break
        except Exception as e:
            print(f"  ⚠️ 找約會按鈕失敗: {e}")

        if add_btn:
            print("  ✅ 找到約會按紐，點擊開啟 Popup...")
            async with context.expect_page(timeout=15000) as popup_info:
                await add_btn.click()
            popup_page = await popup_info.value
            await popup_page.wait_for_load_state("domcontentloaded", timeout=15000)
            await popup_page.wait_for_timeout(5000)

            # 診斷 Popup 的儲存按鈕
            await dump_ribbon_info(popup_page, "appointment_popup")

            # 關閉 popup
            await popup_page.close()
        else:
            print("  ❌ 找不到約會新增按鈕，跳過 Popup 診斷")
            print("     (可能日報尚未完整儲存，subgrid 未產生)")

        # === 完成 ===
        print(f"\n{'='*60}")
        print(f"  🎉 診斷完成！請檢查以下輸出：")
        print(f"     {OUTPUT_DIR}")
        print(f"{'='*60}")

        # 保留瀏覽器 15 秒讓使用者觀察
        print("\n  瀏覽器將在 15 秒後關閉...")
        await page.wait_for_timeout(15000)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

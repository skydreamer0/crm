"""
單獨測試：名稱填入 (拜訪對象)
只測試在約會記錄 popup 表單中，輸入客戶姓名並選取 autocomplete 結果的流程。

用法:
    cd /Users/george/Documents/project/crm
    source venv/bin/activate
    python src/test_name_input.py             # 預設測試 "吳書雨"
    python src/test_name_input.py "姜秉均"     # 自訂姓名
"""
import asyncio
import os
import sys
import logging
import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# === 載入選擇器 ===
_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"

def load_selectors() -> dict:
    path = _CONFIG_DIR / "selectors.yaml"
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("crm", {})

SEL = load_selectors()


def get_all_frames(f):
    """遞迴取得所有子 frames"""
    frames = [f]
    for child in f.child_frames:
        frames.extend(get_all_frames(child))
    return frames


async def find_add_activity_button(page):
    """在所有 frames 中尋找「+ 新增約會紀錄」按鈕"""
    all_frames = get_all_frames(page.main_frame)
    for i, f in enumerate(all_frames):
        try:
            btn = await f.query_selector(SEL['appointment']['add_button_primary'])
            if not btn:
                btn = await f.query_selector(SEL['appointment']['add_button_fallback_title'])
            if not btn:
                btn = await f.query_selector(SEL['appointment']['add_button_fallback_class'])
            if btn:
                logger.info(f"✅ 在 frame {i} 找到「+ 新增約會紀錄」按鈕")
                return btn
        except Exception:
            pass
    return None


async def test_name_input(customer_name: str):
    """
    獨立測試名稱填入流程:
        1. 登入 CRM
        2. 新增日報 (含儲存)
        3. 開啟約會記錄 popup
        4. 只測試「拜訪對象」欄位的填寫
        5. 截圖後暫停，不儲存也不關閉，方便肉眼檢查
    """
    load_dotenv()
    username = os.getenv("CRM_USERNAME")
    password = os.getenv("CRM_PASSWORD")
    base_url = os.getenv("CRM_BASE_URL", "https://crm.synmosa.com.tw/")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)   # 有 UI，方便觀察
        context = await browser.new_context(
            http_credentials={"username": username, "password": password},
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        try:
            # --- Step 1: 登入 ---
            logger.info("Step 1: 登入 CRM...")
            await page.goto(base_url, wait_until="networkidle", timeout=60000)
            logger.info("✅ 登入成功")

            # --- Step 2: 新增日報 ---
            new_report_url = f"{base_url.rstrip('/')}/SYNCRM/main.aspx?etn=new_dailyreport&pagetype=entityrecord"
            logger.info("Step 2: 新增日報...")
            await page.goto(new_report_url, wait_until="networkidle")
            await page.wait_for_timeout(5000)

            iframe_el = await page.wait_for_selector(SEL['common']['content_iframe'], timeout=10000)
            frame = await iframe_el.content_frame()
            if not frame:
                raise Exception("無法取得表單 iframe")

            # 填寫時間
            date_input = await frame.query_selector(SEL['daily_report']['date_input'])
            if date_input:
                await date_input.click()
            else:
                await frame.click("input[type='text']")

            await page.keyboard.press("Tab")
            await page.wait_for_timeout(100)
            await page.keyboard.press("Tab")
            await page.wait_for_timeout(100)
            await page.keyboard.type("09:00")
            await page.keyboard.press("Tab")
            await page.wait_for_timeout(100)
            await page.keyboard.type("18:00")

            # 儲存日報
            save_btn = await page.query_selector(SEL['common']['save_button'])
            if not save_btn:
                raise Exception("找不到儲存按鈕")
            await save_btn.click()
            await page.wait_for_timeout(5000)
            logger.info("✅ 日報已儲存")

            # --- Step 3: 點擊「+ 新增約會紀錄」 ---
            logger.info("Step 3: 尋找新增約會紀錄按鈕...")
            add_btn = await find_add_activity_button(page)
            if not add_btn:
                logger.info("第一次沒找到，reload 後再試...")
                await page.reload(wait_until="networkidle")
                await page.wait_for_timeout(5000)
                add_btn = await find_add_activity_button(page)
                if not add_btn:
                    raise Exception("找不到「+ 新增約會紀錄」按鈕")

            logger.info("Step 3: 點擊按鈕，等待 popup...")
            async with context.expect_page(timeout=15000) as popup_info:
                await add_btn.click()

            popup_page = await popup_info.value
            logger.info(f"✅ Popup 開啟: {popup_page.url}")

            # --- Step 4: 名稱填入測試 ---
            logger.info("Step 4: 開始名稱填入測試 ───────────────────")

            await popup_page.wait_for_load_state("networkidle", timeout=30000)
            await popup_page.wait_for_timeout(3000)

            popup_iframe_el = await popup_page.wait_for_selector(
                SEL['common']['content_iframe'], timeout=15000
            )
            popup_frame = await popup_iframe_el.content_frame()
            if not popup_frame:
                raise Exception("無法取得 popup 表單 iframe")

            await popup_page.wait_for_timeout(2000)

            logger.info(f"  🔍 在 div#new_abc 欄位填入: {customer_name}")
            abc_field = await popup_frame.wait_for_selector(
                SEL['appointment']['customer_input'], timeout=15000
            )
            await abc_field.click()
            await popup_page.wait_for_timeout(500)

            # 輸入客戶姓名
            await popup_page.keyboard.type(customer_name)
            logger.info(f"  ✅ 已輸入文字: {customer_name}")
            await popup_page.wait_for_timeout(2000)  # 等待 autocomplete 出現

            # 嘗試尋找 autocomplete 下拉選單
            lookup_result = await popup_frame.query_selector(
                "ul.ac-dropdown li:first-child, "
                "ul[id$='_IMenu'] li:first-child, "
                "div.ms-crm-Inline-LookupResults li:first-child, "
                "span.ms-crm-Lookup-Result"
            )

            if lookup_result:
                text = await lookup_result.text_content()
                logger.info(f"  🎯 找到 autocomplete 下拉選項: {text}")
                await lookup_result.click()
                await popup_page.wait_for_timeout(2000)
                logger.info(f"  ✅ 已點選 autocomplete 結果")
            else:
                logger.info("  ⚠️ 未出現 autocomplete 下拉選單")

                # Dump 目前 popup_frame 的 HTML，方便偵錯
                frame_html = await popup_frame.content()
                os.makedirs("logs/debug", exist_ok=True)
                debug_path = f"logs/debug/name_input_{datetime.datetime.now().strftime('%H%M%S')}.html"
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(frame_html)
                logger.info(f"  📄 已匯出 iframe HTML → {debug_path}")

                # fallback: 按 Tab
                logger.info("  → 使用 Tab 離開欄位 (fallback)...")
                await popup_page.keyboard.press("Tab")
                await popup_page.wait_for_timeout(3000)

            # --- Step 5: 截圖 ---
            os.makedirs("logs/screenshots", exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            screenshot_path = f"logs/screenshots/test_name_{ts}_{customer_name}.png"
            await popup_page.screenshot(path=screenshot_path, full_page=True)
            logger.info(f"  📸 截圖已存: {screenshot_path}")

            # --- 暫停，讓使用者有時間觀察 ---
            logger.info("=" * 60)
            logger.info("🛑 測試完成！瀏覽器保持開啟 60 秒，請肉眼確認結果。")
            logger.info("=" * 60)
            await page.wait_for_timeout(60000)

        except Exception as e:
            logger.error(f"❌ 測試失敗: {e}")
            os.makedirs("logs/screenshots", exist_ok=True)
            await page.screenshot(path="logs/screenshots/test_name_error.png")
            raise
        finally:
            await browser.close()


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "吳書雨"
    print(f"\n{'='*60}")
    print(f"  測試名稱填入: {name}")
    print(f"{'='*60}\n")
    asyncio.run(test_name_input(name))

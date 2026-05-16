"""
CRM 約會記錄自動化引擎 (create_appointments.py)
================================================

本檔案是 CRM 自動化的**核心引擎**，負責驅動 Playwright 瀏覽器完成所有 CRM 操作。

完整流程:
  1. 解析待訪名單（由 visit_list_parser 處理）
  2. 登入 CRM（使用 HTTP Basic Auth）
  3. 新增日報（填寫上下班時間並儲存）
  4. 批次建立約會記錄:
     - 填寫拜訪對象（客戶姓名 autocomplete）
     - 選擇實際拜訪時段（上午/下午）
     - 填寫拜訪描述（從產品描述庫隨機選取）
     - 勾選完成事項「產品說明」
     - 新增產品介紹明細（產品搜尋 + 拜訪目的 + 拜訪內容）
  5. 儲存並關閉，執行完畢後發送 Line Notify 通知

呼叫方式:
  - CLI:    python src/create_appointments.py
  - Web UI: 由 app.py 的 /api/execute 路由在背景執行 run_automation()
"""
# === 標準庫 ===
import asyncio
import datetime
import json
import logging
import os
import random
from pathlib import Path

# === 第三方套件 ===
import requests
import yaml
from dotenv import load_dotenv
from playwright.async_api import async_playwright

# === 本地模組 ===
from visit_list_parser import (
    parse_visit_list,
    select_products,
    VisitEntry,
    resolve_crm_product_id,
    should_skip_visit_content,
    get_random_description,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === 載入外部選擇器 ===
_CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_selectors() -> dict:
    """Load CRM selectors from config/selectors.yaml."""
    path = _CONFIG_DIR / "selectors.yaml"
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("crm", {})


SEL = load_selectors()

# ---------------------------------------------------------------------------
# Timing Configuration (Phase 1 optimization)
# ---------------------------------------------------------------------------
# All wait durations in milliseconds. Tune these to balance speed vs. stability.
TIMING = {
    # --- 鍵盤操作後的最短等待 (讓 CRM JS 處理事件) ---
    "key_press":       200,   # 單一按鍵 (Tab/Enter) 後 (80→200)
    "after_type":      300,   # 打完一段文字後 (150→300)
    "type_delay":      100,   # keyboard.type 每字元間隔 ms
    # --- UI 互動 ---
    "after_click":     300,   # 點擊欄位後 (200→300)
    "autocomplete":    500,   # 等 autocomplete 下拉出現 (400→500)
    "dropdown":        400,   # 下拉選單操作 (300→400)
    "iframe_ready":    500,   # iframe 內容載入後的緩衝 (300→500)
    # --- 儲存 / 頁面切換 ---
    "after_save":      2000,  # 儲存按鈕點擊後 (1500→2000)
    "page_transition": 800,   # 頁面切換後的緩衝 (500→800)
    "popup_ready":     800,   # popup 加載後的緩衝 (500→800)
}

def _resolved_lookup_selector(lookup_id: str) -> str:
    """Return selectors that indicate a CRM lookup has resolved to a real row."""
    return (
        f"#{lookup_id} span.ms-crm-Lookup-Item[resolved='true'], "
        f"#{lookup_id}_lookupDiv span.ms-crm-Lookup-Item[oid]"
    )


def _lookup_item_matches(text: str, title: str, keyvalues: str, expected: str) -> bool:
    """Check visible and CRM metadata text for the expected lookup value."""
    expected_value = str(expected or "").casefold()
    if not expected_value:
        return False

    haystack = "\n".join(
        str(part or "") for part in (text, title, keyvalues)
    ).casefold()
    return expected_value in haystack


async def wait_for_resolved_lookup(frame, lookup_id: str, expected: str, timeout: int = 8000) -> bool:
    """Poll until a CRM lookup shows a resolved item matching the expected value."""
    selector = _resolved_lookup_selector(lookup_id)
    attempts = max(1, timeout // 500)

    for _ in range(attempts):
        items = await frame.query_selector_all(selector)
        for item in items:
            text = await item.text_content() or ""
            title = await item.get_attribute("title") or ""
            keyvalues = (
                await item.get_attribute("keyvalues")
                or await item.get_attribute("values")
                or ""
            )
            if _lookup_item_matches(text, title, keyvalues, expected):
                return True

        await asyncio.sleep(0.5)

    return False


async def reliable_save(target_page, label: str = "記錄", timeout: int = 15000):
    """
    可靠的儲存操作：先嘗試按鈕，再嘗試 Ctrl+S（確保焦點在正確的視窗上）。

    Args:
        target_page: Playwright page 物件（主頁面或 popup）
        label: 儲存操作的描述（用於日誌）
        timeout: 等待儲存按鈕出現的最長時間 (ms)
    """
    saved = False

    # 嘗試 1: 點擊可見的儲存按鈕
    try:
        save_btn = await target_page.wait_for_selector(
            SEL['common']['save_button'], state="visible", timeout=timeout
        )
        # 等待 loading 遮罩消失
        try:
            await target_page.wait_for_selector(
                "div#InlineDialog_Background", state="hidden", timeout=3000
            )
        except Exception:
            pass
        await save_btn.click(force=True)
        logger.info(f"  ✅ 已點擊{label}儲存按鈕")
        saved = True
    except Exception:
        logger.warning(f"  ⚠️ 找不到{label}儲存按鈕 (等待 {timeout}ms)，改用 Ctrl+S")

    # 嘗試 2: Ctrl+S — 先確保焦點在目標視窗
    if not saved:
        try:
            await target_page.bring_to_front()
        except Exception:
            pass
        # 點擊表單主體確保焦點
        try:
            await target_page.click("body", timeout=2000)
        except Exception:
            pass
        await target_page.keyboard.press("Control+s")
        logger.info(f"  ✅ 已執行 Ctrl+S ({label})")

    # 等待儲存完成
    await target_page.wait_for_timeout(TIMING['after_save'] + 1500)


def send_line_notify(message: str):
    """傳送 Line Notify 通知 (若環境變數有設定 LINE_NOTIFY_TOKEN)"""
    token = os.getenv("LINE_NOTIFY_TOKEN")
    if not token:
        return
    url = "https://notify-api.line.me/api/notify"
    headers = {"Authorization": f"Bearer {token}"}
    data = {"message": message}
    try:
        requests.post(url, headers=headers, data=data, timeout=5)
        logger.info("🔔 Line Notify 發送成功")
    except Exception as e:
        logger.warning(f"⚠️ Line Notify 發送失敗: {e}")

# === 預設待訪名單（僅供 CLI 直接執行時使用，Web UI 會從前端傳入） ===
VISIT_LIST = """
慈濟/URO/吳書雨/B
耕莘/URO/姜秉均/A
慈濟/OBS/祝春紅/B
""".strip()

# === 設定 ===
MORNING_VISITS = 5   # 上午拜訪人數
AFTERNOON_VISITS = 5  # 下午拜訪人數


async def login(page, base_url):
    """登入 CRM"""
    logger.info("登入 CRM...")
    await page.goto(base_url, wait_until="domcontentloaded", timeout=60000)
    logger.info("✅ 登入成功")


async def create_daily_report(page, base_url, run_date: str = None):
    """新增日報並填寫上下班時間與自訂日期"""
    # 確保 base_url 只取到 .com.tw 或 .com，避免跟後面的 /SYNCRM/main.aspx 疊加
    host_url = base_url.split('/SYNCRM')[0] if '/SYNCRM' in base_url else base_url.rstrip('/')
    new_report_url = f"{host_url}/SYNCRM/main.aspx?etn=new_dailyreport&pagetype=entityrecord"
    logger.info(f"前往新增日報表單... ({new_report_url})")
    await page.goto(new_report_url, wait_until="domcontentloaded")

    # 用 smart wait 取代固定 2000ms：直接等 iframe 出現
    iframe_element = await page.wait_for_selector(SEL['common']['content_iframe'], timeout=15000)
    frame = await iframe_element.content_frame()
    if not frame:
        raise Exception("無法取得表單 iframe")

    logger.info("成功進入日報表單")

    # 填寫時間: 點擊日期欄位 → Tab 到上班時間 → 填 09:00 → Tab → 填 18:00
    date_input = await frame.query_selector(SEL['daily_report']['date_input'])
    if date_input:
        await date_input.click()
    else:
        await frame.click("input[type='text']")

    if run_date:
        target_date = run_date.replace('-', '/')
        logger.info(f"填寫自訂日期: {target_date}")
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Backspace")
        await page.wait_for_timeout(200)
        await page.keyboard.insert_text(target_date)
        await page.wait_for_timeout(300)

    await page.keyboard.press("Tab")
    await page.wait_for_timeout(TIMING['key_press'] + 300)
    await page.keyboard.press("Tab")
    await page.wait_for_timeout(500)
    
    # 直接貼上，模擬高速輸入
    await page.keyboard.insert_text("09:00")
    logger.info("已填入上班時間 09:00")

    await page.keyboard.press("Tab")
    await page.wait_for_timeout(500)
    await page.keyboard.insert_text("18:00")
    logger.info("已填入下班時間 18:00")
    
    # 離開欄位，觸發 CRM 系統的 onchange 事件，確保資料被正確寫入暫存
    await page.keyboard.press("Tab")
    await page.wait_for_timeout(500)

    # 儲存
    logger.info("準備儲存日報...")
    await reliable_save(page, label="日報", timeout=15000)

    # 等待 CRM 儲存完成並重新載入頁面 (給充足時間讓系統產生對應的子表單)
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    
    # 強制等候 3 到 4 秒以確保 subgrid 完全產生
    await page.wait_for_timeout(4000)
    logger.info("✅ 日報儲存完成")


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
            for sel in [
                SEL['appointment']['add_button_primary'],
                SEL['appointment']['add_button_fallback_title'],
                SEL['appointment']['add_button_fallback_class']
            ]:
                elements = await f.query_selector_all(sel)
                for el in elements:
                    if await el.is_visible():
                        logger.info(f"✅ 在 frame {i} 找到可見的「+ 新增約會紀錄」按鈕 (Selector: {sel})")
                        return el
        except Exception:
            pass
    return None


# =========================================================================
#  fill_appointment — 還原為原始可運作版本 (不包含 context / 不包含產品選取)
# =========================================================================
async def fill_appointment(popup_page, period: str, entry: VisitEntry = None):
    """
    在約會記錄 popup 視窗中填寫基本表單。
    流程: 姓名 → 時段 → 勾選產品說明 → 截圖 → 儲存 → 儲存後關閉

    Args:
        popup_page: Playwright popup page 物件
        period: "上午" 或 "下午"
        entry: VisitEntry 物件 (含客戶姓名、科別、產品)
    """
    customer_name = entry.customer_name if entry else ""
    logger.info(f"填寫約會記錄 (時段: {period}, 拜訪對象: {customer_name})...")

    # 等待頁面基礎載入，使用較短的 timeout 避免乾等
    try:
        await popup_page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass
    
    # 給 CRM JavaScript 一點時間綁定事件
    await popup_page.wait_for_timeout(TIMING['popup_ready'])

    # 取得 popup 內的表單 iframe (contentIFrame0)
    popup_iframe_element = await popup_page.wait_for_selector(
        SEL['common']['content_iframe'], timeout=15000
    )
    popup_frame = await popup_iframe_element.content_frame()
    if not popup_frame:
        raise Exception("無法取得 popup 表單 iframe")
    
    await popup_page.wait_for_timeout(TIMING['iframe_ready'])

    # (拜訪對象移至步驟 4 填寫)

    # === 2. 實際拜訪時段 (new_actualvisitperiod): 選擇上午/下午 ===
    logger.info(f"  選擇實際拜訪時段: {period}...")
    period_selected = False
    for period_attempt in range(3):
        try:
            if period_attempt > 0:
                logger.warning(f"  ⚠️ 重試選擇時段 (第 {period_attempt} 次)...")
                await popup_page.wait_for_timeout(1000)

            period_field = await popup_frame.wait_for_selector(
                SEL['appointment']['period_div'], timeout=10000
            )
            await period_field.click()
            await popup_page.wait_for_timeout(TIMING['after_click'] + 200)

            # 等待 select 元素出現 (明確等待，避免 JS 尚未加載)
            period_select = await popup_frame.wait_for_selector(
                SEL['appointment']['period_select'], state="attached", timeout=5000
            )
            if period_select:
                options = await popup_frame.query_selector_all(
                    SEL['appointment']['period_options']
                )
                for opt in options:
                    text = await opt.text_content()
                    if period in text:
                        value = await opt.get_attribute("value")
                        await period_select.select_option(value=value)
                        logger.info(f"  ✅ 已選擇: {text} (value={value})")
                        period_selected = True
                        break
            if not period_selected:
                logger.info("  嘗試用鍵盤選擇...")
                await popup_page.keyboard.press("Enter")
                await popup_page.wait_for_timeout(TIMING['dropdown'])
                period_selected = True  # 假設鍵盤操作成功

            await popup_page.wait_for_timeout(TIMING['key_press'])
            if period_selected:
                break
        except Exception as e:
            logger.warning(f"  ⚠️ 實際拜訪時段選擇異常 (嘗試 {period_attempt+1}): {e}")

    if not period_selected:
        logger.error("  ❌ 無法選取實際拜訪時段 (已重試 3 次)，此筆記錄儲存後可能失敗")

    # === 3. 拜訪描述 (new_visit_description): 填寫隨機產品描述 ===
    logger.info("  填寫拜訪描述...")
    try:
        # 選取一項產品來產生描述
        if entry and entry.matched_products:
            # 第一個優先配對的產品
            main_product = entry.matched_products[0]
            description = get_random_description(main_product)
            
            if description:
                desc_field = await popup_frame.wait_for_selector(
                    SEL['appointment']['visit_description'], timeout=5000
                )
                if desc_field:
                    await desc_field.click()
                    await popup_page.wait_for_timeout(TIMING['after_click'])
                    await popup_page.keyboard.insert_text(description)
                    logger.info(f"  ✅ 已填寫描述: {description[:15]}...")
                    await popup_page.wait_for_timeout(TIMING['after_type'])
                else:
                    logger.warning("  ⚠️ 找不到拜訪描述欄位")
            else:
                logger.info("  ⏭️ 產品無可用描述，跳過填寫")
        else:
            logger.info("  ⏭️ 無產品資料，跳過填寫描述")
    except Exception as e:
        logger.warning(f"  ⚠️ 拜訪描述填寫異常: {e}")

    # === 4. 完成事項: 勾選「產品說明」===
    logger.info("  勾選完成事項: 產品說明...")
    checkbox_done = False
    for cb_attempt in range(2):
        try:
            if cb_attempt > 0:
                logger.info("  重試載入 checkbox iframe...")
                await popup_page.wait_for_timeout(1500)

            checkbox_iframe = await popup_frame.wait_for_selector(
                SEL['appointment']['checkbox_iframe'], timeout=10000
            )
            checkbox_frame = await checkbox_iframe.content_frame()

            if checkbox_frame:
                # 等待 iframe 內容實際載入完成
                await popup_page.wait_for_timeout(TIMING['iframe_ready'] + 500)
                try:
                    await checkbox_frame.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass

                checkbox = await checkbox_frame.query_selector(
                    SEL['appointment']['checkbox_product_intro']
                )
                if checkbox:
                    is_checked = await checkbox.is_checked()
                    if not is_checked:
                        await checkbox.click()
                        logger.info("  ✅ 已勾選「產品說明」")
                    else:
                        logger.info("  ✅ 「產品說明」已經勾選")
                    checkbox_done = True
                    break
                else:
                    checkbox = await checkbox_frame.query_selector(
                        SEL['appointment']['checkbox_product_intro_fallback']
                    )
                    if checkbox:
                        await checkbox.click()
                        logger.info("  ✅ 已勾選「產品說明」(備用選擇器)")
                        checkbox_done = True
                        break
                    else:
                        logger.warning(f"  ⚠️ 找不到產品說明 checkbox (嘗試 {cb_attempt+1})")
            else:
                logger.warning("  ⚠️ 無法進入 WebResource_checkbox iframe")
        except Exception as e:
            logger.warning(f"  ⚠️ 完成事項勾選異常 (嘗試 {cb_attempt+1}): {e}")

    if not checkbox_done:
        logger.warning("  ⚠️ 產品說明 checkbox 最終未勾選，繼續執行")



    # === 4. 拜訪對象 (new_abc): 輸入客戶姓名 (移至最後填寫) ===
    logger.info(f"  填寫拜訪對象: {customer_name}...")
    try:
        # 等待欄位出現並可點擊
        abc_field = await popup_frame.wait_for_selector(
            SEL['appointment']['customer_input'], timeout=10000
        )
        await abc_field.click()
        await popup_page.wait_for_timeout(TIMING['after_click'] + 300)

        if customer_name:
            customer_selected = False
            for attempt in range(3):
                if attempt > 0:
                    logger.warning(f"  ⚠️ 重新輸入拜訪對象 (第 {attempt} 次重試)...")
                    await abc_field.click()
                    await popup_page.keyboard.press("Control+A")
                    await popup_page.keyboard.press("Backspace")
                    await popup_page.wait_for_timeout(800)

                # 直接貼上客戶姓名，提升速度
                await popup_page.keyboard.insert_text(customer_name)
                # 給更長的時間讓 CRM 的 onChange 或 keyup 事件去拉取資料
                await popup_page.wait_for_timeout(1500 + attempt * 1000)

                logger.info("  → 按下 Enter (觸發搜尋或選取第一個)...")
                await popup_page.keyboard.press("Enter")

                # 嘗試等待下拉選單出現 (增加容錯能力)
                try:
                    await popup_frame.wait_for_selector("ul#new_abc_i_IMenu", state="visible", timeout=6000 + attempt * 2000)
                    logger.info("  ✅ 客戶下拉選單出現")
                except Exception:
                    pass

                await popup_page.wait_for_timeout(800 + attempt * 500)
                logger.info("  → 按下 Enter 確認選取...")
                await popup_page.keyboard.press("Enter")
                
                # 給予時間讓 CRM 確認選取
                await popup_page.wait_for_timeout(1500)
                
                # Check if it was successfully resolved
                customer_selected = True
                break
                
            logger.info(f"  ✅ 拜訪對象已帶入: {customer_name}")
        else:
            await popup_page.keyboard.press("Tab")
            await popup_page.wait_for_timeout(TIMING['key_press'])
            logger.info("  ✅ 拜訪對象已帶入 (模板)")
    except Exception as e:
        logger.warning(f"  ⚠️ 拜訪對象填寫異常: {e}")

    # === 5. 儲存約會記錄 ===
    logger.info("  儲存約會記錄...")
    await reliable_save(popup_page, label="約會記錄", timeout=15000)

    # 這裡不再執行「儲存後關閉」，保留 popup 開啟狀態，交由後續的產品填寫步驟處理。


# =========================================================================
#  add_products — 產品選取 (在約會已儲存後、獨立操作)
#  TODO: 此功能獨立於基本填表流程。目前先註解，確認基本流程穩定後再啟用。
# =========================================================================
async def add_products_to_appointment(popup_page, popup_frame, context, entry: VisitEntry):
    """
    在已儲存的約會記錄中新增產品（需先儲存約會才能啟用子表單）

    Args:
        popup_page: 約會記錄的 popup page
        popup_frame: popup 內的 iframe
        context: browser context (用於接管新彈出的產品視窗)
        entry: VisitEntry 物件
    """
    if not entry or not entry.matched_products:
        logger.info("  ⚠️ 無匹配產品資料")
        return

    products_to_add = select_products(entry, count=2)
    logger.info(f"  → 預計新增產品: {products_to_add}")

    for p_idx, product_code in enumerate(products_to_add):
        logger.info(f"    [{p_idx+1}/{len(products_to_add)}] 正在處理產品: {product_code}")
        try:
            product_id = resolve_crm_product_id(product_code, entry)
            if not product_id:
                logger.warning(f"      ⚠️ 無法解析產品編號，跳過: {product_code}")
                continue

            logger.info(f"      產品編號: {product_id}")

            # 點擊「新增 日報 - 產品介紹明細」按鈕
            logger.info("      呼叫產品新增視窗...")
            add_prod_btn = popup_frame.locator(SEL['product']['add_product_button'])
            # 先確認按鈕可見 (30s 而非預設 300s)
            try:
                await add_prod_btn.wait_for(state="visible", timeout=30000)
            except Exception:
                logger.warning("      ⚠️ 產品新增按鈕 30 秒內未出現，嘗試重新儲存約會記錄...")
                await reliable_save(popup_page, label="約會記錄(重試)", timeout=10000)
                # 重新取得 iframe
                try:
                    refreshed = await popup_page.wait_for_selector(
                        SEL['common']['content_iframe'], timeout=10000
                    )
                    popup_frame = await refreshed.content_frame()
                    add_prod_btn = popup_frame.locator(SEL['product']['add_product_button'])
                    await add_prod_btn.wait_for(state="visible", timeout=15000)
                except Exception as retry_e:
                    logger.error(f"      ❌ 重試後仍找不到產品新增按鈕: {retry_e}")
                    raise

            async with context.expect_page() as new_page_info:
                await add_prod_btn.click(timeout=10000)

            product_popup = await new_page_info.value
            await product_popup.wait_for_load_state("domcontentloaded", timeout=15000)

            # 取得 product popup 內的表單 iframe
            prod_iframe_element = await product_popup.wait_for_selector(SEL['common']['content_iframe'], timeout=15000)
            prod_frame = await prod_iframe_element.content_frame()
            await product_popup.wait_for_timeout(TIMING['iframe_ready'])
            # CRM 開啟新視窗較慢，多等一點時間讓輸入框與事件綁定完成
            await product_popup.wait_for_timeout(2500)

            logger.info("      輸入產品編號搜尋...")
            prod_input = prod_frame.locator(SEL['product']['product_input'])
            await prod_input.click()
            await product_popup.wait_for_timeout(TIMING['after_click'])

            dropdown_appeared = False
            for attempt in range(3):
                if attempt > 0:
                    logger.warning(f"      ⚠️ 等待下拉選單超時，重新輸入產品 (第 {attempt} 次重試)...")
                    await prod_input.click()
                    await product_popup.keyboard.press("Control+A")
                    await product_popup.keyboard.press("Backspace")
                    await product_popup.wait_for_timeout(500)

                await product_popup.keyboard.insert_text(product_id)
                # 等待自動完成的後端查詢稍微跑一下再按 Enter
                await product_popup.wait_for_timeout(1000 + attempt * 1000)
                await product_popup.keyboard.press("Enter")

                # 等待下拉選單出現 (smart wait)
                logger.info("      等待並確認選項...")
                try:
                    await prod_frame.wait_for_selector(SEL['product']['product_dropdown_menu'], timeout=10000 + attempt * 5000)
                    dropdown_appeared = True
                    break
                except Exception:
                    pass

            if not dropdown_appeared:
                 logger.warning("      ⚠️ 無法載入產品下拉選單 (已超過重試次數)，將嘗試強行繼續")
                 
            await product_popup.wait_for_timeout(TIMING['dropdown'])
            await product_popup.keyboard.press("Enter")
            await product_popup.wait_for_timeout(TIMING['dropdown'])

            # --- 產品選完後，用 Tab 離開產品欄位讓 CRM 確認選取 ---
            await product_popup.keyboard.press("Tab")
            await product_popup.wait_for_timeout(TIMING['autocomplete'])

            product_selected = await wait_for_resolved_lookup(
                prod_frame,
                "new_product",
                product_id,
                timeout=8000,
            )
            if not product_selected:
                raise Exception(f"產品 lookup 未解析，停止儲存避免空白產品: {product_id}")

            logger.info("      填寫拜訪目的...")
            try:
                purpose_sel = SEL['product']['visit_purpose']
                purpose_field = prod_frame.locator(purpose_sel).first
                await purpose_field.click(timeout=5000)
                await product_popup.wait_for_timeout(TIMING['after_click'])

                purpose_text = random.choice(["上量", "了解需求"])
                await product_popup.keyboard.insert_text(purpose_text)
                await product_popup.wait_for_timeout(TIMING['after_type'])

                # Tab 離開讓 CRM 確認
                await product_popup.keyboard.press("Tab")
                await product_popup.wait_for_timeout(TIMING['key_press'])
                logger.info(f"      ✅ 拜訪目的: {purpose_text}")
            except Exception as e:
                logger.warning(f"      ⚠️ 無法填寫拜訪目的: {e}")

            if not should_skip_visit_content(product_code):
                logger.info("      填寫拜訪內容 (選第一個)...")
                try:
                    # 捲動到底部確保可見
                    await prod_frame.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await product_popup.wait_for_timeout(TIMING['after_click'])

                    item_sel = SEL['product']['visit_item']
                    visit_item_field = prod_frame.locator(item_sel).first
                    await visit_item_field.scroll_into_view_if_needed()
                    await visit_item_field.click(timeout=5000)
                    await product_popup.wait_for_timeout(TIMING['after_click'])

                    # 展開 lookup 下拉 (Enter)
                    await product_popup.keyboard.press("Enter")
                    await product_popup.wait_for_timeout(TIMING['dropdown'])

                    # 固定選第一個選項
                    await product_popup.keyboard.press("ArrowDown")
                    await product_popup.wait_for_timeout(TIMING['key_press'])
                    await product_popup.keyboard.press("Enter")
                    await product_popup.wait_for_timeout(TIMING['key_press'])
                    logger.info("      ✅ 已選取拜訪內容 (第一項)")
                except Exception as e:
                    logger.warning(f"      ⚠️ 無法填寫拜訪內容: {e}")
            else:
                logger.info("      ⏭️ 已設定跳過拜訪內容")


            # 4. 儲存並關閉產品 Popup
            logger.info("      儲存該產品...")
            try:
                await reliable_save(product_popup, label="產品", timeout=15000)
                
                try:
                    # 手動關閉視窗 (因為是點儲存而不是儲存並關閉)
                    if not product_popup.is_closed():
                        await product_popup.close()
                except Exception:
                    # Target closed 意味著 CRM 幫忙關閉了，這也算成功
                    pass
                    
                logger.info(f"    ✅ 產品 {product_code} 儲存並關閉完成")
            except Exception as e:
                logger.warning(f"      ⚠️ 產品儲存發生異常: {e}")
                try:
                    if not product_popup.is_closed():
                        await product_popup.close()
                except Exception:
                    pass

        except Exception as e:
            logger.warning(f"    ⚠️ 處理產品 {product_code} 時發生異常: {e}")

        # === 產品間等待: 讓約會表單的 subgrid (產品明細列表) 完成背景重整 ===
        # 儲存第一項產品後，CRM 會自動 reload 約會表單的 iframe，
        # 若不等待就立即點「新增」，會因 DOM 尚未就緒而找不到按鈕。
        if p_idx < len(products_to_add) - 1:
            logger.info("    ⏳ 等待約會表單 subgrid 刷新...")
            await popup_page.wait_for_timeout(3000)

            # 重新取得 popup_frame (因 iframe 可能已被 CRM 重新載入)
            try:
                refreshed_iframe = await popup_page.wait_for_selector(
                    SEL['common']['content_iframe'], timeout=15000
                )
                popup_frame = await refreshed_iframe.content_frame()
                if popup_frame:
                    # 確認新增按鈕已可見再繼續
                    await popup_frame.wait_for_selector(
                        SEL['product']['add_product_button'],
                        state="visible", timeout=10000
                    )
                    logger.info("    ✅ Subgrid 已刷新，新增按鈕已就緒")
                else:
                    logger.warning("    ⚠️ 無法重新取得 iframe，後續產品可能失敗")
            except Exception as e:
                logger.warning(f"    ⚠️ 等待 subgrid 刷新時發生異常: {e}")


# =========================================================================
#  cleanup & create_single_appointment
# =========================================================================
async def cleanup_stale_popups(context, main_page):
    """關閉所有殘留的 Popup 視窗，只保留主頁面"""
    for p in context.pages:
        if p != main_page and not p.is_closed():
            try:
                logger.info(f"  🧹 清理殘留 Popup: {p.url[:60]}")
                await p.close()
            except Exception:
                pass


async def create_single_appointment(page, context, period: str, index: int, entry: VisitEntry = None, daily_report_url: str = None):
    """
    建立單筆約會記錄

    Args:
        page: 主頁面 (日報頁面)
        context: browser context (用來監聯 popup)
        period: "上午" 或 "下午"
        index: 第幾筆 (1-based)
        entry: VisitEntry 物件 (含客戶姓名、科別、產品)
        daily_report_url: 日報頁面的 URL，用於完成後導航回去
    """
    customer_label = f" — {entry.customer_name}" if entry else ""
    logger.info(f"{'='*50}")
    logger.info(f"建立第 {index} 筆約會記錄 ({period}{customer_label})")
    logger.info(f"{'='*50}")

    # 每筆開始前清理殘留 Popup
    await cleanup_stale_popups(context, page)

    # 尋找「+ 新增約會紀錄」按鈕 (含多次重試機制)
    add_btn = await find_add_activity_button(page)
    if not add_btn:
        # 最多重試 3 次，每次用 goto 回到日報頁面
        for retry in range(3):
            logger.warning(f"找不到「+ 新增」按鈕，第 {retry+1} 次重試...")
            if daily_report_url:
                logger.info(f"  → 導航回日報頁面: {daily_report_url[:80]}...")
                await page.goto(daily_report_url, wait_until="networkidle")
            else:
                await page.reload(wait_until="networkidle")
            await page.wait_for_timeout(2000)
            # 等待 content iframe 載入
            try:
                await page.wait_for_selector(
                    SEL['common']['content_iframe'], timeout=15000
                )
                await page.wait_for_timeout(1500)
            except Exception:
                pass
            add_btn = await find_add_activity_button(page)
            if add_btn:
                break
        if not add_btn:
            raise Exception("找不到「+ 新增約會紀錄」按鈕 (已重試 3 次)")

    # 點擊並等待 popup
    async with context.expect_page(timeout=15000) as popup_info:
        await add_btn.click()

    popup_page = await popup_info.value
    logger.info(f"✅ Popup 開啟: {popup_page.url}")

    # 填寫約會表單 (原始可運作邏輯，不包含產品)
    await fill_appointment(popup_page, period, entry=entry)

    # 取得 popup 內的表單 iframe (為了給新增產品使用)
    try:
        popup_iframe_element = await popup_page.wait_for_selector(
            SEL['common']['content_iframe'], timeout=10000
        )
        popup_frame = await popup_iframe_element.content_frame()

        # === 新增產品 ===
        # 移至此處，在約會已經儲存 (但尚未關閉) 的情況下，接續執行新增產品
        if popup_frame and entry and entry.matched_products:
            await add_products_to_appointment(popup_page, popup_frame, context, entry)

    except Exception as e:
        logger.warning(f"  ⚠️ 準備新增產品時發生異常: {e}")

    # === 關閉約會 Popup ===
    try:
        if not popup_page.is_closed():
            # 嘗試「儲存後關閉」
            try:
                save_close_btn = await popup_page.wait_for_selector(
                    SEL['common']['save_and_close_button'], state="visible", timeout=5000
                )
                logger.info("  執行「儲存後關閉」...")
                await save_close_btn.click()
                await popup_page.wait_for_timeout(1500)
            except Exception:
                # 按鈕找不到或已不可見，直接關閉
                pass

            # 確保 popup 被關閉
            try:
                if not popup_page.is_closed():
                    await popup_page.close()
            except Exception:
                pass  # 已經被關閉了

        logger.info("  ✅ Popup 已關閉")
    except Exception:
        # 最外層防呆：TargetClosedError 等
        logger.info("  ✅ Popup 已自動關閉")

    # === 導航回日報頁面 ===
    # 取消強制導航回日報頁面，因為每次建立約會都是開啟 Popup，主頁面並未改變。
    # 依賴下一筆的 find_add_activity_button 防呆機制去判斷是否需要重新載入。
    await page.wait_for_timeout(TIMING['page_transition'])

    logger.info(f"✅ 第 {index} 筆約會記錄建立完成\n")


# =========================================================================
#  run_automation — 主流程 (可從 Flask API 或 CLI 呼叫)
# =========================================================================
async def run_automation(entries: list[VisitEntry], run_date: str = None, progress_callback=None):
    """
    Core automation routine: launches browser, logs in, creates daily report,
    and fills appointment records for each entry.

    Args:
        entries: List of VisitEntry objects (parsed visit list).
        run_date: Date to fill in 'YYYY-MM-DD' format.
        progress_callback: Optional callable(dict) invoked after each step.
    """
    load_dotenv()
    username = os.getenv("CRM_USERNAME")
    password = os.getenv("CRM_PASSWORD")
    base_url = os.getenv("CRM_BASE_URL", "https://crm.synmosa.com.tw/SYNCRM/main.aspx#187829805/")
    headless = os.getenv("HEADLESS", "false").lower() == "true"

    total = len(entries)
    run_history = {
        "start_time": datetime.datetime.now().isoformat(),
        "total_entries": total,
        "headless": headless,
        "logs": [],
        "error": None
    }

    def _report(step: str, index: int = 0, detail: str = ""):
        msg = {"step": step, "index": index, "total": total, "detail": detail, "time": datetime.datetime.now().isoformat()}
        logger.info(f"[Progress] {msg}")
        run_history["logs"].append(msg)
        if progress_callback:
            progress_callback(msg)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(
            http_credentials={"username": username, "password": password}
        )
        page = await context.new_page()

        try:
            # Step 1: 登入
            _report("login")
            await login(page, base_url)

            # Step 2: 新增日報
            _report("daily_report")
            await create_daily_report(page, base_url, run_date)

            # 記住日報頁面的 URL，用於每筆約會完成後導航回來
            daily_report_url = page.url
            logger.info(f"📌 日報頁面 URL: {daily_report_url[:100]}")

            # Step 3: 批次建立約會記錄
            succeeded: list[VisitEntry] = []
            failed: list[tuple[VisitEntry, str]] = []  # (entry, error_message)

            midpoint = (total + 1) // 2
            browser_dead = False
            for idx, entry in enumerate(entries, start=1):
                if browser_dead:
                    failed.append((entry, "瀏覽器已關閉，跳過"))
                    continue
                try:
                    period = "上午" if idx <= midpoint else "下午"
                    _report("appointment", idx, f"{entry.customer_name} ({period})")
                    await create_single_appointment(page, context, period, idx, entry=entry, daily_report_url=daily_report_url)
                    succeeded.append(entry)
                except Exception as entry_e:
                    err_msg = str(entry_e)
                    logger.warning(f"⚠️ 第 {idx} 筆資料 ({entry.customer_name}) 執行異常: {entry_e}")
                    _report("error", idx, f"跳過此筆: {entry_e}")
                    failed.append((entry, err_msg))
                    # 偵測瀏覽器崩潰：如果頁面/Context 已關閉，後面全部不用再試
                    if "has been closed" in err_msg or "Target closed" in err_msg:
                        logger.error("🛑 瀏覽器已關閉，停止後續所有約會記錄")
                        browser_dead = True

            # =================================================================
            #  Step 4: 最終檢核報告 — 哪些醫師沒寫到
            # =================================================================
            logger.info("")
            logger.info("=" * 60)
            logger.info("📋 最終檢核報告")
            logger.info("=" * 60)
            logger.info(f"  預計處理: {total} 筆")
            logger.info(f"  ✅ 成功:  {len(succeeded)} 筆")
            logger.info(f"  ❌ 失敗:  {len(failed)} 筆")

            if succeeded:
                logger.info("")
                logger.info("  ── 成功名單 ──")
                for e in succeeded:
                    logger.info(f"    ✅ {e.customer_name} ({e.department_code})")

            if failed:
                logger.info("")
                logger.info("  ── ⚠️ 未完成名單 (請手動補填) ──")
                for e, err in failed:
                    logger.info(f"    ❌ {e.customer_name} ({e.department_code}) — 原因: {err[:80]}")

            logger.info("=" * 60)

            # 組合 Line Notify 訊息
            notify_lines = [f"\n📋 CRM 自動化檢核報告", f"預計: {total} 筆 | ✅ 成功: {len(succeeded)} | ❌ 失敗: {len(failed)}"]
            if failed:
                notify_lines.append("\n⚠️ 未完成名單:")
                for e, err in failed:
                    notify_lines.append(f"  ❌ {e.customer_name}({e.department_code})")
            else:
                notify_lines.append("\n🎉 全部完成，無遺漏！")
            send_line_notify("\n".join(notify_lines))

            # 將檢核結果寫入 run_history
            run_history["succeeded"] = [e.customer_name for e in succeeded]
            run_history["failed"] = [{"name": e.customer_name, "dept": e.department_code, "error": err} for e, err in failed]

            _report("done")

        except Exception as e:
            logger.error(f"❌ 執行錯誤: {e}")
            run_history["error"] = str(e)
            os.makedirs("logs/screenshots", exist_ok=True)
            await page.screenshot(path="logs/screenshots/error.png")
            _report("error", detail=str(e))
            send_line_notify(f"\n❌ CRM 自動化發生嚴重錯誤:\n{e}\n\n請檢查截圖 logs/screenshots/error.png。")
            raise
        finally:
            run_history["end_time"] = datetime.datetime.now().isoformat()
            try:
                os.makedirs("logs/history", exist_ok=True)
                history_path = f"logs/history/run_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(history_path, "w", encoding="utf-8") as f:
                    json.dump(run_history, f, ensure_ascii=False, indent=2)
                logger.info(f"📝 執行日誌已存至 {history_path}")
            except Exception as e:
                logger.error(f"⚠️ 寫入執行日誌失敗: {e}")

            if not headless:
                logger.info("瀏覽器保持開啟 30 秒...")
                await page.wait_for_timeout(30000)
            await browser.close()


async def main():
    """CLI entry point: parse VISIT_LIST and run automation."""
    visit_list_text = os.getenv("VISIT_LIST", VISIT_LIST)
    entries = parse_visit_list(visit_list_text)

    if not entries:
        logger.error("沒有解析到任何待訪名單！")
        return

    logger.info(f"已解析 {len(entries)} 筆待訪名單")
    for e in entries:
        products = select_products(e)
        logger.info(f"  → {e.customer_name} | {e.department_code}({e.department_name_zh}) | 產品: {products}")

    await run_automation(entries)


if __name__ == "__main__":
    asyncio.run(main())

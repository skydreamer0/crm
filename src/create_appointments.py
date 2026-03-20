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
    "key_press":       80,    # 單一按鍵 (Tab/Enter) 後
    "after_type":      150,   # 打完一段文字後
    # --- UI 互動 ---
    "after_click":     200,   # 點擊欄位後
    "autocomplete":    400,   # 等 autocomplete 下拉出現
    "dropdown":        300,   # 下拉選單操作
    "iframe_ready":    300,   # iframe 內容載入後的緩衝
    # --- 儲存 / 頁面切換 ---
    "after_save":      1500,  # 儲存按鈕點擊後
    "page_transition": 500,   # 頁面切換後的緩衝
    "popup_ready":     500,   # popup 加載後的緩衝
}

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


async def create_daily_report(page, base_url):
    """新增日報並填寫上下班時間"""
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

    await page.keyboard.press("Tab")
    await page.wait_for_timeout(TIMING['key_press'])
    await page.keyboard.press("Tab")
    await page.wait_for_timeout(TIMING['key_press'])
    await page.keyboard.type("09:00")
    logger.info("已填入上班時間 09:00")

    await page.keyboard.press("Tab")
    await page.wait_for_timeout(TIMING['key_press'])
    await page.keyboard.type("18:00")
    logger.info("已填入下班時間 18:00")

    # 儲存
    save_button = await page.query_selector(SEL['common']['save_button'])
    if not save_button:
        raise Exception("找不到儲存按鈕!")

    logger.info("點擊儲存...")
    await save_button.click()
    await page.wait_for_timeout(TIMING['key_press'])
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

    # === 1. 拜訪對象 (new_abc): 輸入客戶姓名 ===
    logger.info(f"  填寫拜訪對象: {customer_name}...")
    try:
        # 等待欄位出現並可點擊
        abc_field = await popup_frame.wait_for_selector(
            SEL['appointment']['customer_input'], timeout=10000
        )
        await abc_field.click()
        await popup_page.wait_for_timeout(TIMING['after_click'])

        if customer_name:
            # 輸入客戶姓名
            await popup_page.keyboard.type(customer_name)
            await popup_page.wait_for_timeout(TIMING['autocomplete'])

            # 使用兩次 Enter 確認客戶姓名（模擬手動操作）
            logger.info("  → 按下 Enter 選取第一個 autocomplete 結果...")
            await popup_page.keyboard.press("Enter")
            await popup_page.wait_for_timeout(TIMING['autocomplete'])

            logger.info("  → 按下 Enter 確認選取...")
            await popup_page.keyboard.press("Enter")
            await popup_page.wait_for_timeout(TIMING['autocomplete'])

            logger.info(f"  ✅ 拜訪對象已填入: {customer_name}")
        else:
            await popup_page.keyboard.press("Tab")
            await popup_page.wait_for_timeout(TIMING['key_press'])
            logger.info("  ✅ 拜訪對象已帶入 (模板)")
    except Exception as e:
        logger.warning(f"  ⚠️ 拜訪對象填寫異常: {e}")

    # === 2. 實際拜訪時段 (new_actualvisitperiod): 選擇上午/下午 ===
    logger.info(f"  選擇實際拜訪時段: {period}...")
    try:
        period_field = await popup_frame.wait_for_selector(
            SEL['appointment']['period_div'], timeout=10000
        )
        await period_field.click()
        await popup_page.wait_for_timeout(TIMING['after_click'])

        # 找到下拉選單 select (原始可運作邏輯)
        period_select = await popup_frame.query_selector(
            SEL['appointment']['period_select']
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
                    break
            else:
                logger.info("  嘗試用鍵盤選擇...")
                await popup_page.keyboard.press("Enter")
                await popup_page.wait_for_timeout(TIMING['dropdown'])
        else:
            await popup_page.keyboard.press("Enter")
            await popup_page.wait_for_timeout(TIMING['dropdown'])

        await popup_page.wait_for_timeout(TIMING['key_press'])
    except Exception as e:
        logger.warning(f"  ⚠️ 實際拜訪時段選擇異常: {e}")

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
                    await popup_page.keyboard.type(description)
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
    try:
        checkbox_iframe = await popup_frame.wait_for_selector(
            SEL['appointment']['checkbox_iframe'], timeout=10000
        )
        checkbox_frame = await checkbox_iframe.content_frame()

        if checkbox_frame:
            await popup_page.wait_for_timeout(TIMING['iframe_ready'])
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
            else:
                checkbox = await checkbox_frame.query_selector(
                    SEL['appointment']['checkbox_product_intro_fallback']
                )
                if checkbox:
                    await checkbox.click()
                    logger.info("  ✅ 已勾選「產品說明」(備用選擇器)")
                else:
                    logger.warning("  ⚠️ 找不到產品說明 checkbox")
        else:
            logger.warning("  ⚠️ 無法進入 WebResource_checkbox iframe")
    except Exception as e:
        logger.warning(f"  ⚠️ 完成事項勾選異常: {e}")



    # === 5. 儲存約會記錄 ===
    logger.info("  儲存約會記錄...")
    save_btn = await popup_page.query_selector(SEL['common']['save_button'])
    if save_btn:
        await save_btn.click()
        await popup_page.wait_for_timeout(TIMING['after_save'])
        logger.info("  ✅ 約會記錄儲存完成")
    else:
        logger.warning("  ⚠️ 找不到儲存按鈕，嘗試 Ctrl+S")
        await popup_page.keyboard.press("Control+s")
        await popup_page.wait_for_timeout(TIMING['after_save'])

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
            async with context.expect_page() as new_page_info:
                await popup_frame.locator(SEL['product']['add_product_button']).click()

            product_popup = await new_page_info.value
            await product_popup.wait_for_load_state("domcontentloaded", timeout=15000)

            # 取得 product popup 內的表單 iframe
            prod_iframe_element = await product_popup.wait_for_selector(SEL['common']['content_iframe'], timeout=15000)
            prod_frame = await prod_iframe_element.content_frame()
            await product_popup.wait_for_timeout(TIMING['iframe_ready'])

            logger.info("      輸入產品編號搜尋...")
            prod_input = prod_frame.locator(SEL['product']['product_input'])
            await prod_input.click()
            await product_popup.wait_for_timeout(TIMING['after_click'])
            await product_popup.keyboard.type(product_id)
            await product_popup.wait_for_timeout(TIMING['after_type'])
            await product_popup.keyboard.press("Enter")

            # 等待下拉選單出現 (smart wait)
            logger.info("      等待並確認選項...")
            await prod_frame.wait_for_selector(SEL['product']['product_dropdown_menu'], timeout=10000)
            await product_popup.wait_for_timeout(TIMING['dropdown'])
            await product_popup.keyboard.press("Enter")
            await product_popup.wait_for_timeout(TIMING['dropdown'])

            # --- 產品選完後，用 Tab 離開產品欄位讓 CRM 確認選取 ---
            await product_popup.keyboard.press("Tab")
            await product_popup.wait_for_timeout(TIMING['autocomplete'])

            logger.info("      填寫拜訪目的...")
            try:
                purpose_sel = SEL['product']['visit_purpose']
                purpose_field = prod_frame.locator(purpose_sel).first
                await purpose_field.click(timeout=5000)
                await product_popup.wait_for_timeout(TIMING['after_click'])

                purpose_text = random.choice(["上量", "了解需求"])
                await product_popup.keyboard.type(purpose_text)
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
                # 嚴格使用按鈕制
                save_btn = await product_popup.wait_for_selector(SEL['common']['save_button'], state="attached", timeout=15000)
                await save_btn.click()
                
                try:
                    # 等待一下，如果視窗被 CRM 自己關了，這裡會噴例外，我們抓接即可
                    await product_popup.wait_for_timeout(1500)
                    
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
    await page.wait_for_timeout(500)
    if daily_report_url:
        logger.info(f"  🔄 導航回日報頁面...")
        await page.goto(daily_report_url, wait_until="domcontentloaded")
    else:
        await page.reload(wait_until="networkidle")
    await page.wait_for_timeout(1500)

    # 等待 content iframe 載入
    try:
        await page.wait_for_selector(SEL['common']['content_iframe'], timeout=15000)
        await page.wait_for_timeout(1000)
    except Exception:
        logger.warning("  ⚠️ 等待 content iframe 超時")

    logger.info(f"✅ 第 {index} 筆約會記錄建立完成\n")


# =========================================================================
#  run_automation — 主流程 (可從 Flask API 或 CLI 呼叫)
# =========================================================================
async def run_automation(entries: list[VisitEntry], progress_callback=None):
    """
    Core automation routine: launches browser, logs in, creates daily report,
    and fills appointment records for each entry.

    Args:
        entries: List of VisitEntry objects (parsed visit list).
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
            await create_daily_report(page, base_url)

            # 記住日報頁面的 URL，用於每筆約會完成後導航回來
            daily_report_url = page.url
            logger.info(f"📌 日報頁面 URL: {daily_report_url[:100]}")

            # Step 3: 批次建立約會記錄
            midpoint = (total + 1) // 2
            for idx, entry in enumerate(entries, start=1):
                try:
                    period = "上午" if idx <= midpoint else "下午"
                    _report("appointment", idx, f"{entry.customer_name} ({period})")
                    await create_single_appointment(page, context, period, idx, entry=entry, daily_report_url=daily_report_url)
                except Exception as entry_e:
                    logger.warning(f"⚠️ 第 {idx} 筆資料 ({entry.customer_name}) 執行異常: {entry_e}")
                    _report("error", idx, f"跳過此筆: {entry_e}")

            _report("done")
            logger.info("=" * 60)
            logger.info(f"🎉 全部完成！共建立 {total} 筆約會記錄")
            logger.info("=" * 60)
            send_line_notify(f"\n🎉 CRM 自動化執行完畢！\n預計處理 {total} 筆紀錄。")

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

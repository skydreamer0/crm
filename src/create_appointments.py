"""
CRM 約會記錄自動化 — Phase 2
完整流程: 解析待訪名單 → 登入 → 新增日報 → 填時間 → 儲存 → 批次建立約會記錄

約會記錄操作:
  1. 拜訪對象: 從待訪名單解析客戶姓名，自動填入
  2. 實際拜訪時段: 上午/下午
  3. 完成事項: 勾選「產品說明」
  4. 儲存
"""
import asyncio
import os
import logging
from dotenv import load_dotenv
from playwright.async_api import async_playwright
from visit_list_parser import parse_visit_list, select_products, VisitEntry

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# === 待訪名單 (可從檔案讀取或直接貼上) ===
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
    await page.goto(base_url, wait_until="networkidle", timeout=60000)
    logger.info("✅ 登入成功")


async def create_daily_report(page, base_url):
    """新增日報並填寫上下班時間"""
    new_report_url = f"{base_url.rstrip('/')}/SYNCRM/main.aspx?etn=new_dailyreport&pagetype=entityrecord"
    logger.info("前往新增日報表單...")
    await page.goto(new_report_url, wait_until="networkidle")
    await page.wait_for_timeout(5000)

    # 取得表單 iframe
    iframe_element = await page.wait_for_selector("iframe#contentIFrame0", timeout=10000)
    frame = await iframe_element.content_frame()
    if not frame:
        raise Exception("無法取得表單 iframe")

    logger.info("成功進入日報表單")

    # 填寫時間: 點擊日期欄位 → Tab 到上班時間 → 填 09:00 → Tab → 填 18:00
    date_input = await frame.query_selector("input#DateInput")
    if date_input:
        await date_input.click()
    else:
        await frame.click("input[type='text']")

    await page.keyboard.press("Tab")
    await page.wait_for_timeout(500)
    await page.keyboard.press("Tab")
    await page.wait_for_timeout(500)
    await page.keyboard.type("09:00")
    logger.info("已填入上班時間 09:00")

    await page.keyboard.press("Tab")
    await page.wait_for_timeout(500)
    await page.keyboard.type("18:00")
    logger.info("已填入下班時間 18:00")

    # 儲存
    save_button = await page.query_selector("img.ms-crm-ImageStrip-Save_16")
    if not save_button:
        raise Exception("找不到儲存按鈕!")

    logger.info("點擊儲存...")
    await save_button.click()
    await page.wait_for_timeout(8000)
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
            btn = await f.query_selector("img#details_addImageButtonImage")
            if not btn:
                btn = await f.query_selector('img[title*="新增 約會 記錄"]')
            if not btn:
                btn = await f.query_selector("img.ms-crm-add-button-icon")
            if btn:
                logger.info(f"✅ 在 frame {i} 找到「+ 新增約會紀錄」按鈕")
                return btn
        except Exception:
            pass
    return None


async def fill_appointment(popup_page, period: str, entry: VisitEntry = None):
    """
    在約會記錄 popup 視窗中填寫表單

    Args:
        popup_page: Playwright popup page 物件
        period: "上午" 或 "下午"
        entry: VisitEntry 物件 (含客戶姓名、科別、產品)
    """
    customer_name = entry.customer_name if entry else ""
    logger.info(f"填寫約會記錄 (時段: {period}, 拜訪對象: {customer_name})...")

    # 等待 popup 完全載入
    await popup_page.wait_for_load_state("networkidle", timeout=30000)
    await popup_page.wait_for_timeout(3000)

    # 取得 popup 內的表單 iframe (contentIFrame0)
    popup_iframe_element = await popup_page.wait_for_selector(
        "iframe#contentIFrame0", timeout=15000
    )
    popup_frame = await popup_iframe_element.content_frame()
    if not popup_frame:
        raise Exception("無法取得 popup 表單 iframe")

    # 等待表單渲染完成
    await popup_page.wait_for_timeout(3000)

    # === 1. 拜訪對象 (new_abc): 輸入客戶姓名 ===
    logger.info(f"  填寫拜訪對象: {customer_name}...")
    try:
        # 點擊拜訪對象欄位區域
        abc_field = await popup_frame.wait_for_selector(
            "div#new_abc", timeout=10000
        )
        await abc_field.click()
        await popup_page.wait_for_timeout(1000)

        if customer_name:
            # 輸入客戶姓名 → 從待訪名單自動帶入
            await popup_page.keyboard.type(customer_name)
            await popup_page.wait_for_timeout(1000)
            # 按 Enter 確認選取 lookup 結果
            await popup_page.keyboard.press("Enter")
            await popup_page.wait_for_timeout(1500)
            logger.info(f"  ✅ 拜訪對象已填入: {customer_name}")
        else:
            # Fallback: Enter×2 帶入模板 (舊行為)
            await popup_page.keyboard.press("Enter")
            await popup_page.wait_for_timeout(500)
            await popup_page.keyboard.press("Enter")
            await popup_page.wait_for_timeout(1500)
            logger.info("  ✅ 拜訪對象已帶入 (模板)")
    except Exception as e:
        logger.warning(f"  ⚠️ 拜訪對象填寫異常: {e}")

    # === 2. 實際拜訪時段 (new_actualvisitperiod): 選擇上午/下午 ===
    logger.info(f"  選擇實際拜訪時段: {period}...")
    try:
        period_field = await popup_frame.wait_for_selector(
            "div#new_actualvisitperiod", timeout=10000
        )
        await period_field.click()
        await popup_page.wait_for_timeout(1000)

        # 找到下拉選單 select
        period_select = await popup_frame.query_selector(
            "select#new_actualvisitperiod_i"
        )
        if period_select:
            # 取得所有選項，找到匹配的
            options = await popup_frame.query_selector_all(
                "select#new_actualvisitperiod_i option"
            )
            for opt in options:
                text = await opt.text_content()
                if period in text:
                    value = await opt.get_attribute("value")
                    await period_select.select_option(value=value)
                    logger.info(f"  ✅ 已選擇: {text} (value={value})")
                    break
            else:
                # 如果 select 方式不行，嘗試用鍵盤
                logger.info("  嘗試用鍵盤選擇...")
                await popup_page.keyboard.press("Enter")
                await popup_page.wait_for_timeout(500)
        else:
            # 嘗試直接點擊 inline edit 區域
            await popup_page.keyboard.press("Enter")
            await popup_page.wait_for_timeout(500)

        await popup_page.wait_for_timeout(1000)
    except Exception as e:
        logger.warning(f"  ⚠️ 實際拜訪時段選擇異常: {e}")

    # === 3. 完成事項: 勾選「產品說明」===
    logger.info("  勾選完成事項: 產品說明...")
    try:
        # 完成事項在 WebResource_checkbox iframe 內
        checkbox_iframe = await popup_frame.wait_for_selector(
            "iframe#WebResource_checkbox", timeout=10000
        )
        checkbox_frame = await checkbox_iframe.content_frame()

        if checkbox_frame:
            # 等待 iframe 載入
            await popup_page.wait_for_timeout(2000)

            # 勾選「產品說明」 (value=100000002)
            checkbox = await checkbox_frame.query_selector(
                "input#id100000002"
            )
            if checkbox:
                is_checked = await checkbox.is_checked()
                if not is_checked:
                    await checkbox.click()
                    logger.info("  ✅ 已勾選「產品說明」")
                else:
                    logger.info("  ✅ 「產品說明」已經勾選")
            else:
                # 嘗試其他選擇器
                checkbox = await checkbox_frame.query_selector(
                    "input[value='100000002']"
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

    # === 4. 儲存約會記錄 ===
    logger.info("  儲存約會記錄...")
    save_btn = await popup_page.query_selector("img.ms-crm-ImageStrip-Save_16")
    if save_btn:
        await save_btn.click()
        await popup_page.wait_for_timeout(5000)
        logger.info("  ✅ 約會記錄儲存完成")
    else:
        logger.warning("  ⚠️ 找不到儲存按鈕，嘗試 Ctrl+S")
        await popup_page.keyboard.press("Control+s")
        await popup_page.wait_for_timeout(5000)

    # 關閉 popup (儲存後關閉)
    save_close_btn = await popup_page.query_selector(
        "img.ms-crm-ImageStrip-SaveAndClose_16"
    )
    if save_close_btn:
        logger.info("  嘗試「儲存後關閉」...")
        await save_close_btn.click()
        await popup_page.wait_for_timeout(3000)


async def create_single_appointment(page, context, period: str, index: int, entry: VisitEntry = None):
    """
    建立單筆約會記錄

    Args:
        page: 主頁面 (日報頁面)
        context: browser context (用來監聯 popup)
        period: "上午" 或 "下午"
        index: 第幾筆 (1-based)
        entry: VisitEntry 物件 (含客戶姓名、科別、產品)
    """
    customer_label = f" — {entry.customer_name}" if entry else ""
    logger.info(f"{'='*50}")
    logger.info(f"建立第 {index} 筆約會記錄 ({period}{customer_label})")
    logger.info(f"{'='*50}")

    # 尋找「+ 新增約會紀錄」按鈕
    add_btn = await find_add_activity_button(page)
    if not add_btn:
        raise Exception("找不到「+ 新增約會紀錄」按鈕")

    # 點擊並等待 popup
    async with context.expect_page(timeout=15000) as popup_info:
        await add_btn.click()

    popup_page = await popup_info.value
    logger.info(f"✅ Popup 開啟: {popup_page.url}")

    # 填寫約會表單
    await fill_appointment(popup_page, period, entry=entry)

    # 等待 popup 關閉，回到主頁面
    try:
        await popup_page.wait_for_event("close", timeout=10000)
        logger.info("Popup 已關閉")
    except Exception:
        # 如果 popup 沒自動關閉，手動關閉
        if not popup_page.is_closed():
            logger.info("手動關閉 popup...")
            await popup_page.close()

    # 回到主頁面，等待穩定
    await page.wait_for_timeout(3000)

    # 重新整理主頁面的 frames (因為 subgrid 可能更新)
    await page.reload(wait_until="networkidle")
    await page.wait_for_timeout(5000)

    logger.info(f"✅ 第 {index} 筆約會記錄建立完成\n")


async def main():
    load_dotenv()
    username = os.getenv("CRM_USERNAME")
    password = os.getenv("CRM_PASSWORD")
    base_url = os.getenv("CRM_BASE_URL", "https://crm.synmosa.com.tw/")

    # Step 0: 解析待訪名單
    visit_list_text = os.getenv("VISIT_LIST", VISIT_LIST)
    entries = parse_visit_list(visit_list_text)

    if entries:
        total = len(entries)
        logger.info(f"已解析 {total} 筆待訪名單")
        for e in entries:
            products = select_products(e)
            logger.info(f"  → {e.customer_name} | {e.department_code}({e.department_name_zh}) | 產品: {products}")
    else:
        total = MORNING_VISITS + AFTERNOON_VISITS
        logger.info(f"未提供待訪名單，使用預設數量: {total} 筆")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            http_credentials={"username": username, "password": password}
        )
        page = await context.new_page()

        try:
            # Step 1: 登入
            await login(page, base_url)

            # Step 2: 新增日報
            await create_daily_report(page, base_url)

            # Step 3: 批次建立約會記錄
            if entries:
                # 依待訪名單建立 (前半上午、後半下午)
                midpoint = (len(entries) + 1) // 2
                for idx, entry in enumerate(entries, start=1):
                    period = "上午" if idx <= midpoint else "下午"
                    await create_single_appointment(page, context, period, idx, entry=entry)
            else:
                # Fallback: 舊行為 (無名單時)
                index = 1
                for i in range(MORNING_VISITS):
                    await create_single_appointment(page, context, "上午", index)
                    index += 1
                for i in range(AFTERNOON_VISITS):
                    await create_single_appointment(page, context, "下午", index)
                    index += 1

            logger.info("=" * 60)
            logger.info(f"🎉 全部完成！共建立 {total} 筆約會記錄")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"❌ 執行錯誤: {e}")
            os.makedirs("logs/screenshots", exist_ok=True)
            await page.screenshot(path="logs/screenshots/error.png")
            raise
        finally:
            # 保持瀏覽器開啟一段時間供檢查
            logger.info("瀏覽器保持開啟 5 分鐘...")
            await page.wait_for_timeout(300000)
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

import logging
import os
import asyncio
from dotenv import load_dotenv
from playwright.async_api import async_playwright

# 設定日誌
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/automation.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

async def run_crm_task():
    load_dotenv()
    
    username = os.getenv("CRM_USERNAME")
    password = os.getenv("CRM_PASSWORD")
    base_url = os.getenv("CRM_BASE_URL", "https://crm.synmosa.com.tw/")

    if not username or not password:
        logger.error("❌ 錯誤：未在 .env 中找到 CRM_USERNAME 或 CRM_PASSWORD")
        return

    async with async_playwright() as p:
        logger.info("🚀 啟動瀏覽器...")
        # 改為讀取環境變數設定，預設為背景執行
        headless_mode = os.getenv("HEADLESS", "true").lower() == "true"
        browser = await p.chromium.launch(headless=headless_mode)
        
        # 關鍵：設定 http_credentials 處理 Basic Auth
        context = await browser.new_context(
            http_credentials={
                "username": username,
                "password": password
            },
            viewport={'width': 1280, 'height': 800}
        )
        
        page = await context.new_page()
        
        try:
            logger.info(f"🌐 正在導覽至: {base_url}")
            # 導覽並等待頁面加載完成
            response = await page.goto(base_url, wait_until="networkidle", timeout=60000)
            
            if response.status == 200:
                logger.info("✅ 登入成功！已進入 CRM 系統。")
                
                # 建立截圖存檔以便確認
                os.makedirs("logs/screenshots", exist_ok=True)
                screenshot_path = "logs/screenshots/login_success.png"
                await page.screenshot(path=screenshot_path)
                logger.info(f"📸 已擷取成功畫面：{screenshot_path}")
                
                # --- 自動填寫日報邏輯開始 ---
                
                # 1. 導覽至日報清單 (檢查是否有今日紀錄)
                report_list_url = f"{base_url.rstrip('/')}/SYNCRM/_root/homepage.aspx?etc=10029"
                logger.info("前往日報清單...")
                await page.goto(report_list_url, wait_until="networkidle")
                await page.wait_for_timeout(3000)
                
                # 檢查今日日期 (格式 OOOO/O/O 或 OOOO/OO/OO)
                from datetime import datetime
                today = datetime.now()
                # 建立兩種可能的日期格式比對字串，因為月份跟日期不補零
                today_str = f"{today.year}/{today.month}/{today.day}"
                
                logger.info(f"尋找今日 ({today_str}) 日報紀錄...")
                
                # 嘗試進入 list iframe
                list_iframe_element = await page.query_selector("iframe#contentIFrame0")
                if list_iframe_element:
                    list_frame = await list_iframe_element.content_frame()
                    if list_frame:
                        # 在表格中找尋包含今日日期的儲存格
                        today_cells = await list_frame.query_selector_all(f"td.ms-crm-List-DataCell:has-text('{today_str}')")
                        if today_cells:
                            logger.info(f"✅ 發現今日 ({today_str}) 已有日報紀錄，不重複新增！")
                            # 儲存截圖證明
                            await page.screenshot(path="logs/screenshots/report_exists.png")
                            return # 結束執行
                        else:
                            logger.info("尚未建立今日日報，繼續新增流程。")
                else:
                    logger.warning("找不到日報清單 iframe，只能直接嘗試新增。")
                
                # 2. 導覽至新增日報表單
                new_report_url = f"{base_url.rstrip('/')}/SYNCRM/main.aspx?etn=new_dailyreport&pagetype=entityrecord"
                logger.info("準備新增今日日報...")
                await page.goto(new_report_url, wait_until="networkidle")
                await page.wait_for_timeout(5000) # 等待表單載入
                
                # 取得表單 iframe
                iframe_element = await page.wait_for_selector("iframe#contentIFrame0", timeout=10000)
                frame = await iframe_element.content_frame()
                
                if frame:
                    logger.info("成功進入日報表單，準備填寫...")
                    
                    try:
                        # 點擊報告日期欄位以設定初始焦點
                        date_input = await frame.query_selector("input#DateInput")
                        if date_input:
                            await date_input.click()
                            logger.info("已設定焦點於 DateInput")
                        else:
                            await frame.click("input[type='text']")
                            logger.info("已設定焦點於第一個文字輸入框")
                            
                        # 根據先前的測試，Tab 2 是上班時間，Tab 3 是下班時間
                        logger.info("尋找上班時間 (Tab 2)...")
                        await page.keyboard.press("Tab") # Tab 1 (new_memo_i)
                        await page.wait_for_timeout(500)
                        await page.keyboard.press("Tab") # Tab 2 (new_workstart_ledit)
                        await page.wait_for_timeout(500)
                        
                        # 填寫上班時間
                        await page.keyboard.type("09:00")
                        logger.info("已輸入上班時間: 09:00")
                        
                        logger.info("尋找下班時間 (Tab 3)...")
                        await page.keyboard.press("Tab") # Tab 3 (new_workend_ledit)
                        await page.wait_for_timeout(500)
                        
                        # 填寫下班時間
                        await page.keyboard.type("18:00")
                        logger.info("已輸入下班時間: 18:00")
                        
                    except Exception as e:
                        logger.error(f"填寫時間過程發生錯誤: {str(e)}")
                        
                    # 嘗試尋找儲存按鈕，可以嘗試多種選擇器
                    save_selectors = [
                        "li[id*='SavePrimary']",
                        "a[title='儲存']",
                        "img.ms-crm-ImageStrip-Save_16",
                        "li#新建立_span a"
                    ]
                    
                    save_button = None
                    for selector in save_selectors:
                        save_button = await page.query_selector(selector)
                        if save_button:
                            logger.info(f"使用選擇器 {selector} 找到儲存按鈕")
                            break
                            
                    if save_button:
                        # 點擊儲存
                        logger.info("點擊儲存按鈕...")
                        await save_button.click()
                        
                        # 等待儲存完成 (可以觀察網路請求或特定元素出現)
                        logger.info("等待系統儲存...")
                        await page.wait_for_timeout(5000) # 給予 5 秒的儲存與整理時間
                        
                        # 儲存後，尋找日報明細區塊右側的「＋ 新增約會紀錄」按鈕
                        # 精確選擇器: img#details_addImageButtonImage (使用者透過 DevTools 確認)
                        logger.info("尋找「新增約會紀錄」按鈕 (img#details_addImageButtonImage)...")
                        
                        # 重新抓取 iframe，因為儲存後頁面可能已重新載入
                        iframe_element = await page.wait_for_selector("iframe#contentIFrame0", timeout=15000)
                        frame = await iframe_element.content_frame() if iframe_element else None
                        
                        add_activity_btn = None
                        
                        # 使用精確的 ID 選擇器
                        if frame:
                            add_activity_btn = await frame.query_selector("img#details_addImageButtonImage")
                        if not add_activity_btn:
                            add_activity_btn = await page.query_selector("img#details_addImageButtonImage")
                        
                        # 備用: 用 title 屬性搜尋
                        if not add_activity_btn:
                            logger.info("ID 選擇器未命中，嘗試 title 屬性...")
                            if frame:
                                add_activity_btn = await frame.query_selector('img[title*="新增 約會 記錄"]')
                            if not add_activity_btn:
                                add_activity_btn = await page.query_selector('img[title*="新增 約會 記錄"]')
                        
                        # 備用: 用 class 名稱搜尋
                        if not add_activity_btn:
                            logger.info("title 選擇器未命中，嘗試 class 屬性...")
                            if frame:
                                add_activity_btn = await frame.query_selector("img.ms-crm-add-button-icon")
                            if not add_activity_btn:
                                add_activity_btn = await page.query_selector("img.ms-crm-add-button-icon")
                        
                        if add_activity_btn:
                            logger.info("✅ 找到「新增約會紀錄」按鈕！點擊中...")
                            await add_activity_btn.click()
                            
                            # 等待新增約會紀錄的視窗或頁面載入
                            logger.info("等待新增約會紀錄視窗載入...")
                            await page.wait_for_timeout(3000)
                            await page.screenshot(path="logs/screenshots/clicked_add_activity.png")
                            logger.info("📸 已擷取點擊新增紀錄後的畫面：logs/screenshots/clicked_add_activity.png")
                        else:
                            logger.warning("⚠️ 儲存成功，但找不到「新增約會紀錄」按鈕。")
                            await page.screenshot(path="logs/screenshots/cannot_find_add_button.png")
                        
                    else:
                        logger.warning("找不到儲存按鈕")
                        # 備用截圖
                        await page.screenshot(path="logs/screenshots/form_filled_no_save.png")
                        
                else:
                    logger.error("無法載入新增日報的表單 iframe")
                
            elif response.status == 401:
                logger.error("❌ 登入失敗：帳號或密碼錯誤 (401 Unauthorized)")
            else:
                logger.error(f"❌ 發生異常狀態碼: {response.status}")

        except Exception as e:
            logger.error(f"⚠️ 執行過程發生錯誤: {str(e)}")
        finally:
            logger.info("🚪 關閉瀏覽器")
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run_crm_task())

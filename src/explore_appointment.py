"""
探索約會紀錄表單 - 自動偵測彈出視窗版本
走完整流程: 新增日報 → 填時間 → 儲存 → 點擊「+ 新增約會紀錄」→ 偵測 popup → dump HTML
"""
import asyncio
import os
import logging
from dotenv import load_dotenv
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def explore_appointment_form():
    load_dotenv()
    username = os.getenv("CRM_USERNAME")
    password = os.getenv("CRM_PASSWORD")
    base_url = os.getenv("CRM_BASE_URL", "https://crm.synmosa.com.tw/")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            http_credentials={"username": username, "password": password}
        )
        page = await context.new_page()
        
        logger.info("登入 CRM...")
        await page.goto(base_url, wait_until="networkidle", timeout=60000)
        logger.info("✅ 登入成功")
        
        # === 1. 新增日報 ===
        new_report_url = f"{base_url.rstrip('/')}/SYNCRM/main.aspx?etn=new_dailyreport&pagetype=entityrecord"
        logger.info("前往新增日報表單...")
        await page.goto(new_report_url, wait_until="networkidle")
        await page.wait_for_timeout(5000)
        
        # 取得表單 iframe
        iframe_element = await page.wait_for_selector("iframe#contentIFrame0", timeout=10000)
        frame = await iframe_element.content_frame()
        
        if not frame:
            logger.error("無法取得表單 iframe")
            await browser.close()
            return
        
        logger.info("成功進入日報表單...")
        
        # === 2. 填寫時間 ===
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
        
        # === 3. 儲存 ===
        save_button = await page.query_selector("img.ms-crm-ImageStrip-Save_16")
        if save_button:
            logger.info("點擊儲存...")
            await save_button.click()
            await page.wait_for_timeout(8000)
            logger.info("✅ 儲存完成")
        else:
            logger.error("找不到儲存按鈕!")
            await browser.close()
            return
        
        # === 4. 尋找「+ 新增約會紀錄」並偵測 popup ===
        def get_all_frames(f):
            frames = [f]
            for child in f.child_frames:
                frames.extend(get_all_frames(child))
            return frames
        
        all_frames = get_all_frames(page.main_frame)
        
        add_btn = None
        for i, f in enumerate(all_frames):
            try:
                btn = await f.query_selector("img#details_addImageButtonImage")
                if not btn:
                    btn = await f.query_selector('img[title*="新增 約會 記錄"]')
                if not btn:
                    btn = await f.query_selector("img.ms-crm-add-button-icon")
                if btn:
                    add_btn = btn
                    logger.info(f"✅ 在 frame {i} 找到「+ 新增約會紀錄」按鈕！")
                    break
            except Exception:
                pass
        
        if not add_btn:
            logger.error("❌ 找不到「+ 新增約會紀錄」按鈕")
            await browser.close()
            return
        
        # ★★★ 關鍵: 監聽 popup (新視窗)  ★★★
        logger.info("點擊「+ 新增約會紀錄」，等待 popup 視窗...")
        
        # 使用 expect_popup 來等待新視窗
        async with context.expect_page() as popup_info:
            await add_btn.click()
        
        popup_page = await popup_info.value
        logger.info(f"✅ 偵測到新視窗！URL: {popup_page.url}")
        
        # 等待 popup 完全載入
        await popup_page.wait_for_load_state("networkidle", timeout=30000)
        await popup_page.wait_for_timeout(5000)  # 再多等 5 秒確保動態內容載入
        
        logger.info(f"Popup 完整 URL: {popup_page.url}")
        
        # 截圖 popup
        os.makedirs("logs/screenshots", exist_ok=True)
        await popup_page.screenshot(path="logs/screenshots/appointment_popup.png", full_page=True)
        logger.info("✅ 已截圖 popup 視窗")
        
        # Dump popup 頁面的所有 frames
        os.makedirs("docs/html_dumps", exist_ok=True)
        popup_frames = get_all_frames(popup_page.main_frame)
        logger.info(f"Popup 中有 {len(popup_frames)} 個 frames")
        
        for i, f in enumerate(popup_frames):
            try:
                html = await f.content()
                path = f"docs/html_dumps/popup_appointment_frame_{i}.html"
                with open(path, "w", encoding="utf-8") as file:
                    file.write(html)
                size_kb = len(html) / 1024
                logger.info(f"✅ Frame {i} → {path} ({size_kb:.1f} KB)")
            except Exception as e:
                logger.warning(f"Frame {i}: {e}")
        
        # 額外: 搜尋 popup 中的重要欄位名稱
        logger.info("=" * 60)
        logger.info("搜尋 popup 中的關鍵欄位...")
        keywords = ["拜訪對象", "完成事項", "實際拜訪時段", "主旨", "subject", "scheduledstart", "new_abc"]
        
        for kw in keywords:
            for i, f in enumerate(popup_frames):
                try:
                    html = await f.content()
                    if kw in html:
                        logger.info(f"  🔍 '{kw}' 出現在 popup frame {i}")
                except Exception:
                    pass
        
        logger.info("=" * 60)
        logger.info("全部完成！瀏覽器保持開啟 10 分鐘")
        logger.info("=" * 60)
        
        await popup_page.wait_for_timeout(600000)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(explore_appointment_form())

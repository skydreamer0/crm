"""
直接開啟今日日報，並等待 10 分鐘讓您操作。
請在 CRM 上對「＋」按鈕按右鍵 → 檢查，然後把看到的 HTML 標籤告訴我。
"""
import asyncio
import os
import logging
from dotenv import load_dotenv
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def open_report():
    load_dotenv()
    username = os.getenv("CRM_USERNAME")
    password = os.getenv("CRM_PASSWORD")
    base_url = os.getenv("CRM_BASE_URL", "https://crm.synmosa.com.tw/")

    async with async_playwright() as p:
        # 開啟 DevTools 讓使用者可以右鍵檢查元素
        browser = await p.chromium.launch(
            headless=False,
            args=["--auto-open-devtools-for-tabs"]
        )
        context = await browser.new_context(
            http_credentials={"username": username, "password": password}
        )
        page = await context.new_page()
        
        logger.info("登入 CRM...")
        await page.goto(base_url, wait_until="networkidle", timeout=60000)
        logger.info("✅ 登入成功")
        
        # 前往日報清單
        report_list_url = f"{base_url.rstrip('/')}/SYNCRM/_root/homepage.aspx?etc=10029"
        logger.info("前往日報清單...")
        await page.goto(report_list_url, wait_until="networkidle", timeout=60000)
        await page.wait_for_timeout(3000)
        
        # 嘗試點擊第一筆（今日）日報
        list_iframe_element = await page.query_selector("iframe#contentIFrame0")
        if list_iframe_element:
            list_frame = await list_iframe_element.content_frame()
            if list_frame:
                first_row_link = await list_frame.query_selector(
                    "table.ms-crm-List-Data tbody tr.ms-crm-List-Row a.ms-crm-List-Link"
                )
                if first_row_link:
                    logger.info("點擊第一筆日報紀錄...")
                    await first_row_link.click()
                    await page.wait_for_timeout(8000)
                    logger.info("✅ 日報已開啟！")
                else:
                    logger.warning("找不到日報紀錄，請手動點擊")
        
        logger.info("=" * 60)
        logger.info("✅ 畫面已準備好，DevTools 已開啟！")
        logger.info("")
        logger.info("請在日報明細區塊找到「＋」按鈕")
        logger.info("對著按鈕 按右鍵 → 檢查 (Inspect)")
        logger.info("然後把 Elements 面板中反白的那行 HTML 標籤截圖或貼給我")
        logger.info("")
        logger.info("⏰ 瀏覽器將保持開啟 10 分鐘")
        logger.info("=" * 60)
        
        # 保持開啟 10 分鐘
        await page.wait_for_timeout(600000)
        
        logger.info("⏰ 10 分鐘已到，關閉瀏覽器。")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(open_report())

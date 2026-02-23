import asyncio
import os
import logging
from dotenv import load_dotenv
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def analyze_report():
    load_dotenv()
    username = os.getenv("CRM_USERNAME")
    password = os.getenv("CRM_PASSWORD")
    base_url = os.getenv("CRM_BASE_URL", "https://crm.synmosa.com.tw/")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(http_credentials={"username": username, "password": password})
        page = await context.new_page()
        
        await page.goto(base_url, wait_until="networkidle")
        report_list_url = f"{base_url.rstrip('/')}/SYNCRM/_root/homepage.aspx?etc=10029"
        await page.goto(report_list_url, wait_until="networkidle")
        await page.wait_for_timeout(3000)
        
        list_iframe_element = await page.query_selector("iframe#contentIFrame0")
        if list_iframe_element:
            list_frame = await list_iframe_element.content_frame()
            if list_frame:
                # 點擊第一筆紀錄 (最近的紀錄)
                first_row_link = await list_frame.query_selector("table.ms-crm-List-Data tbody tr.ms-crm-List-Row a.ms-crm-List-Link")
                if first_row_link:
                    logger.info("打開第一筆日報紀錄...")
                    await first_row_link.click()
                    logger.info("等待頁面載入 8 秒...")
                    await page.wait_for_timeout(8000)
                    
                    os.makedirs("docs/html_dumps", exist_ok=True)
                    
                    # 遞迴抓取所有 frame
                    def get_all_frames(frame):
                        frames = [frame]
                        for child in frame.child_frames:
                            frames.extend(get_all_frames(child))
                        return frames
                        
                    all_frames = get_all_frames(page.main_frame)
                    logger.info(f"找到 {len(all_frames)} 個 frames")
                    
                    for i, f in enumerate(all_frames):
                        try:
                            html_content = await f.content()
                            file_path = f"docs/html_dumps/saved_report_frame_{i}.html"
                            with open(file_path, "w", encoding="utf-8") as file:
                                file.write(html_content)
                            logger.info(f"✅ 已儲存 frame {i} 至 {file_path}")
                        except Exception as e:
                            logger.warning(f"無法取得 frame {i} 的 HTML: {e}")
                    
                    # 擷取畫面
                    await page.screenshot(path="logs/screenshots/opened_report_full.png", full_page=True)
                    logger.info("已擷取畫面 logs/screenshots/opened_report_full.png")
                else:
                    logger.error("找不到任何紀錄")
                    
        await browser.close()

if __name__ == "__main__":
    asyncio.run(analyze_report())

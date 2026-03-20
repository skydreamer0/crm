import asyncio
import os
from dotenv import load_dotenv
from playwright.async_api import async_playwright

async def extract_daily_report_html():
    load_dotenv()
    
    username = os.getenv("CRM_USERNAME")
    password = os.getenv("CRM_PASSWORD")
    # 直接導覽到日報清單頁面
    report_url = "https://crm.synmosa.com.tw/SYNCRM/_root/homepage.aspx?etc=10029"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            http_credentials={"username": username, "password": password},
            viewport={'width': 1280, 'height': 800}
        )
        page = await context.new_page()
        
        try:
            print("導覽至日報頁面...")
            await page.goto(report_url, wait_until="networkidle")
            await page.wait_for_timeout(3000)
            
            # 從 iframe 中取得內容。Dynamics CRM 的主內容通常在 #contentIFrame0 中
            print("尋找內容 iframe...")
            iframe_element = await page.wait_for_selector("iframe#contentIFrame0")
            frame = await iframe_element.content_frame()
            
            os.makedirs("docs/html_dumps", exist_ok=True)
            
            if frame:
                content = await frame.content()
                with open("docs/html_dumps/daily_report_list.html", "w", encoding="utf-8") as f:
                    f.write(content)
                print("載入成功，已儲存 daily_report_list.html")
            else:
                print("找不到 iframe，儲存目前頁面 HTML...")
                content = await page.content()
                with open("docs/html_dumps/daily_report_list_fallback.html", "w", encoding="utf-8") as f:
                    f.write(content)

        except Exception as e:
            print(f"錯誤: {str(e)}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(extract_daily_report_html())

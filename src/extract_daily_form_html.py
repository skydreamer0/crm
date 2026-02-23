import asyncio
import os
from dotenv import load_dotenv
from playwright.async_api import async_playwright

async def extract_daily_form_html():
    load_dotenv()
    
    username = os.getenv("CRM_USERNAME")
    password = os.getenv("CRM_PASSWORD")
    # 直接導覽到新增日報的表單
    new_report_url = "https://crm.synmosa.com.tw/SYNCRM/main.aspx?etn=new_dailyreport&pagetype=entityrecord"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            http_credentials={"username": username, "password": password},
            viewport={'width': 1280, 'height': 800}
        )
        page = await context.new_page()
        
        try:
            print("導覽至新增日報表單...")
            await page.goto(new_report_url, wait_until="networkidle", timeout=60000)
            await page.wait_for_timeout(5000) # 等待表單載入
            
            # 從 iframe 中取得內容
            print("尋找內容 iframe...")
            iframe_element = await page.wait_for_selector("iframe#contentIFrame0", timeout=10000)
            frame = await iframe_element.content_frame()
            
            os.makedirs("docs/html_dumps", exist_ok=True)
            
            if frame:
                content = await frame.content()
                with open("docs/html_dumps/new_daily_report_form.html", "w", encoding="utf-8") as f:
                    f.write(content)
                print("載入成功，已儲存 new_daily_report_form.html")
            else:
                print("找不到 iframe，儲存目前頁面 HTML...")
                content = await page.content()
                with open("docs/html_dumps/new_daily_report_form_fallback.html", "w", encoding="utf-8") as f:
                    f.write(content)

        except Exception as e:
            print(f"錯誤: {str(e)}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(extract_daily_form_html())

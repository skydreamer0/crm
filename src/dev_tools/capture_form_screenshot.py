import asyncio
import os
import time
from dotenv import load_dotenv
from playwright.async_api import async_playwright

async def capture_form():
    load_dotenv()
    
    username = os.getenv("CRM_USERNAME")
    password = os.getenv("CRM_PASSWORD")
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
            await page.wait_for_timeout(5000) # 等待表單完全渲染
            
            ts = int(time.time() * 1000)
            target_path = f"C:\\Users\\User\\.gemini\\antigravity\\brain\\5294ff6b-0651-4645-87cc-2f5044be851d\\new_dailyreport_form_{ts}.png"
            
            await page.screenshot(path=target_path, full_page=True, type="png")
            print(f"Screenshot saved to {target_path}")

        except Exception as e:
            print(f"錯誤: {str(e)}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(capture_form())

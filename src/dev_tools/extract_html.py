import asyncio
import os
from dotenv import load_dotenv
from playwright.async_api import async_playwright

async def extract_crm_html():
    load_dotenv()
    
    username = os.getenv("CRM_USERNAME")
    password = os.getenv("CRM_PASSWORD")
    base_url = "https://crm.synmosa.com.tw/"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            http_credentials={"username": username, "password": password},
            viewport={'width': 1280, 'height': 800}
        )
        page = await context.new_page()
        
        try:
            print("導覽至首頁...")
            await page.goto(base_url, wait_until="networkidle")
            
            # 等待一段時間讓動態內容載入
            await page.wait_for_timeout(3000)
            
            # 建立資料夾
            os.makedirs("docs/html_dumps", exist_ok=True)
            
            # 儲存首頁 HTML
            content = await page.content()
            with open("docs/html_dumps/home.html", "w", encoding="utf-8") as f:
                f.write(content)
            print("首頁 HTML 已儲存")

            # 嘗試找尋報表連結，如果有的話
            # 注意: Microsoft Dynamics CRM 常常把選單藏在 iframe 或特定 id 裡
            
        except Exception as e:
            print(f"錯誤: {str(e)}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(extract_crm_html())

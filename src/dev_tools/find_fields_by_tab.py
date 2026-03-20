import asyncio
import os
from dotenv import load_dotenv
from playwright.async_api import async_playwright

async def find_fields_by_tab():
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
            await page.wait_for_timeout(5000) # 給表單一些時間載入
            
            # 從 iframe 中取得內容
            iframe_element = await page.wait_for_selector("iframe#contentIFrame0", timeout=10000)
            frame = await iframe_element.content_frame()
            
            if not frame:
                print("找不到 主要 iframe")
                return

            print("開始按 Tab 鍵尋找焦點元素...")
            
            try:
                # 尋找 報告日期 輸入框 click
                date_input = await frame.query_selector("input#DateInput")
                if date_input:
                    await date_input.click()
                    print("已點擊 DateInput")
                else:
                    await frame.click("input[type='text']")
                    print("已點擊一般文字輸入框")
            except Exception as e:
                print("無法點擊初始輸入框", e)
                
            # 連續按 15 次 tab
            for i in range(15):
                await page.keyboard.press("Tab")
                await page.wait_for_timeout(500)
                
                # 執行 JS 取得 HTML
                active_element_html = await frame.evaluate('''() => {
                    let el = document.activeElement;
                    if (!el) return "No active element";
                    return el.outerHTML;
                }''')
                
                # 將結果寫入檔案以避免 terminal 截斷
                with open("docs/tab_results.txt", "a", encoding="utf-8") as f:
                    f.write(f"\\n--- Tab {i+1} ---\\n{active_element_html}\\n")
                
                print(f"Tab {i+1} 記錄完成")
            
        except Exception as e:
            print(f"錯誤: {str(e)}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(find_fields_by_tab())

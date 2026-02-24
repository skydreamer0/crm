"""
探索 CRM 產品欄位 — 監控 Popup 版本

流程:
  1. 登入 → 前往已存在的日報
  2. 點擊「+ 新增約會紀錄」→ 等待約會 popup
  3. 在約會 popup 中:
     a. 先填基本欄位 (拜訪對象、時段、完成事項)
     b. 儲存約會記錄
     c. 探索表單中的所有 Tab、欄位，找出產品相關欄位
     d. 監聽是否有第二層 popup (產品視窗)
  4. Dump 所有 HTML + 截圖，輸出欄位清單
"""
import asyncio
import os
import json
import logging
from dotenv import load_dotenv
from playwright.async_api import async_playwright

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = "docs/product_fields"

# 要搜尋的關鍵字
PRODUCT_KEYWORDS = [
    "product", "keyproduct", "new_product", "產品",
    "new_visititem", "new_vst_text", "拜訪描述",
    "new_visiteffect", "拜訪效果", "new_visitpurpose",
    "拜訪目的", "new_footnote", "備註", "new_desc",
    "key_product", "重點產品",
]


def get_all_frames(f):
    """遞迴取得所有 frames"""
    frames = [f]
    for child in f.child_frames:
        frames.extend(get_all_frames(child))
    return frames


async def dump_all_ids(page_or_frame, label: str):
    """提取某個 page/frame 的所有 id 屬性"""
    all_ids = []
    frames = get_all_frames(
        page_or_frame.main_frame
        if hasattr(page_or_frame, "main_frame")
        else page_or_frame
    )

    for i, f in enumerate(frames):
        try:
            ids = await f.evaluate("""
                () => {
                    const result = [];
                    document.querySelectorAll('[id]').forEach(el => {
                        result.push({
                            id: el.id,
                            tag: el.tagName.toLowerCase(),
                            type: el.getAttribute('type') || '',
                            name: el.getAttribute('attrname') || el.getAttribute('name') || '',
                            title: el.getAttribute('title') || '',
                            text: (el.textContent || '').substring(0, 80).trim(),
                            class: el.className ? el.className.substring(0, 80) : '',
                        });
                    });
                    return result;
                }
            """)
            for item in ids:
                item["frame"] = i
            all_ids.extend(ids)
        except Exception as e:
            logger.warning(f"  Frame {i}: {e}")

    # 寫入檔案
    path = os.path.join(OUTPUT_DIR, f"{label}_all_ids.json")
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(all_ids, fp, ensure_ascii=False, indent=2)
    logger.info(f"  ✅ {label}: 共 {len(all_ids)} 個 ID → {path}")
    return all_ids


async def dump_html(page_or_frame, label: str):
    """Dump 所有 frames 的 HTML"""
    frames = get_all_frames(
        page_or_frame.main_frame
        if hasattr(page_or_frame, "main_frame")
        else page_or_frame
    )
    for i, f in enumerate(frames):
        try:
            html = await f.content()
            path = os.path.join(OUTPUT_DIR, f"{label}_frame_{i}.html")
            with open(path, "w", encoding="utf-8") as fp:
                fp.write(html)
            logger.info(f"  Frame {i} → {path} ({len(html)/1024:.1f} KB)")
        except Exception as e:
            logger.warning(f"  Frame {i}: {e}")


async def search_keywords(page_or_frame, keywords: list, label: str):
    """在所有 frames 中搜尋關鍵字"""
    frames = get_all_frames(
        page_or_frame.main_frame
        if hasattr(page_or_frame, "main_frame")
        else page_or_frame
    )
    results = {}
    for kw in keywords:
        for i, f in enumerate(frames):
            try:
                html = await f.content()
                if kw.lower() in html.lower():
                    if kw not in results:
                        results[kw] = []
                    results[kw].append(f"frame_{i}")
            except Exception:
                pass

    path = os.path.join(OUTPUT_DIR, f"{label}_keyword_hits.json")
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(results, fp, ensure_ascii=False, indent=2)

    logger.info(f"\n{'='*50}")
    logger.info(f"📋 {label} — 關鍵字搜尋結果:")
    logger.info(f"{'='*50}")
    for kw, locations in results.items():
        logger.info(f"  🔍 '{kw}' → {locations}")
    if not results:
        logger.info("  (無匹配)")
    return results


async def explore_tabs(popup_frame):
    """探索表單中的所有 Tab (核心、完成 等)"""
    tabs = await popup_frame.query_selector_all("li.ms-crm-Tab")
    if not tabs:
        tabs = await popup_frame.query_selector_all("span.ms-crm-Tab-Link")
    if not tabs:
        tabs = await popup_frame.query_selector_all("[role='tab']")

    logger.info(f"\n找到 {len(tabs)} 個 Tab:")
    tab_info = []
    for i, tab in enumerate(tabs):
        text = await tab.text_content()
        tab_id = await tab.get_attribute("id")
        logger.info(f"  Tab {i}: '{text.strip()}' (id={tab_id})")
        tab_info.append({"index": i, "text": text.strip(), "id": tab_id})
    return tab_info


async def explore_nav_links(popup_frame):
    """探索左側導航 (related records)"""
    nav_links = await popup_frame.query_selector_all("a.ms-crm-Nav-Link")
    if not nav_links:
        nav_links = await popup_frame.query_selector_all("[role='treeitem']")

    logger.info(f"\n找到 {len(nav_links)} 個導航連結:")
    for i, link in enumerate(nav_links):
        text = await link.text_content()
        link_id = await link.get_attribute("id")
        logger.info(f"  Nav {i}: '{text.strip()}' (id={link_id})")


async def main():
    load_dotenv()
    username = os.getenv("CRM_USERNAME")
    password = os.getenv("CRM_PASSWORD")
    base_url = os.getenv("CRM_BASE_URL", "https://crm.synmosa.com.tw/")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            http_credentials={"username": username, "password": password}
        )
        page = await context.new_page()

        # === Step 1: 登入 ===
        logger.info("登入 CRM...")
        await page.goto(base_url, wait_until="networkidle", timeout=60000)
        logger.info("✅ 登入成功")

        # === Step 2: 新增日報 ===
        new_report_url = f"{base_url.rstrip('/')}/SYNCRM/main.aspx?etn=new_dailyreport&pagetype=entityrecord"
        logger.info("前往新增日報...")
        await page.goto(new_report_url, wait_until="networkidle")
        await page.wait_for_timeout(5000)

        iframe_element = await page.wait_for_selector(
            "iframe#contentIFrame0", timeout=10000
        )
        frame = await iframe_element.content_frame()
        if not frame:
            logger.error("無法取得表單 iframe")
            return

        # 填時間 + 儲存
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
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(500)
        await page.keyboard.type("18:00")

        save_btn = await page.query_selector("img.ms-crm-ImageStrip-Save_16")
        if save_btn:
            await save_btn.click()
            await page.wait_for_timeout(8000)
            logger.info("✅ 日報儲存完成")
        else:
            logger.error("找不到儲存按鈕")
            return

        # === Step 3: 新增約會紀錄 ===
        all_frames = get_all_frames(page.main_frame)
        add_btn = None
        for f in all_frames:
            try:
                btn = await f.query_selector("img#details_addImageButtonImage")
                if not btn:
                    btn = await f.query_selector('img[title*="新增 約會 記錄"]')
                if not btn:
                    btn = await f.query_selector("img.ms-crm-add-button-icon")
                if btn:
                    add_btn = btn
                    break
            except Exception:
                pass

        if not add_btn:
            logger.error("找不到「+ 新增約會紀錄」按鈕")
            return

        logger.info("點擊「+ 新增約會紀錄」...")
        async with context.expect_page() as popup_info:
            await add_btn.click()

        popup_page = await popup_info.value
        await popup_page.wait_for_load_state("networkidle", timeout=30000)
        await popup_page.wait_for_timeout(5000)
        logger.info(f"✅ 約會 Popup 開啟: {popup_page.url}")

        # 截圖約會 popup (初始狀態)
        await popup_page.screenshot(
            path=os.path.join(OUTPUT_DIR, "01_appointment_popup_initial.png"),
            full_page=True,
        )

        # === Step 4: 探索約會 popup 的結構 ===
        logger.info("\n" + "=" * 60)
        logger.info("🔍 探索約會 Popup — 初始狀態")
        logger.info("=" * 60)

        # 取得 popup 內的 iframe
        popup_iframe_el = await popup_page.wait_for_selector(
            "iframe#contentIFrame0", timeout=15000
        )
        popup_frame = await popup_iframe_el.content_frame()

        if popup_frame:
            # === 預先填寫拜訪對象，以便解鎖後續的產品欄位 ===
            logger.info("預先填寫拜訪對象 (吳書雨)...")
            try:
                abc_field = await popup_frame.wait_for_selector("div#new_abc", timeout=10000)
                await abc_field.click()
                await popup_page.wait_for_timeout(1000)
                await popup_page.keyboard.type("吳書雨")
                await popup_page.wait_for_timeout(1000)
                await popup_page.keyboard.press("Enter")
                await popup_page.wait_for_timeout(1500)
                logger.info("✅ 已自動填入拜訪對象")
            except Exception as e:
                logger.warning(f"⚠️ 拜訪對象填寫失敗: {e} (您可能需要手動填寫)")

            # 探索 Tabs
            await explore_tabs(popup_frame)

            # 探索導航
            await explore_nav_links(popup_frame)

            # Dump 所有 ID
            await dump_all_ids(popup_page, "appointment_initial")

            # 搜尋產品關鍵字
            await search_keywords(popup_page, PRODUCT_KEYWORDS, "appointment_initial")

            # === Step 5: 點擊各個 Tab，dump 出現的新欄位 ===
            tab_labels = await popup_frame.query_selector_all(
                "span.ms-crm-Tab-Link, li.ms-crm-Tab a"
            )

            for i, tab in enumerate(tab_labels):
                text = (await tab.text_content()).strip()
                logger.info(f"\n📂 切換到 Tab: '{text}'")
                try:
                    await tab.click()
                    await popup_page.wait_for_timeout(2000)

                    # Dump 此 Tab 的 ID
                    await dump_all_ids(popup_page, f"appointment_tab_{i}_{text}")
                    await search_keywords(
                        popup_page, PRODUCT_KEYWORDS, f"appointment_tab_{i}_{text}"
                    )

                    # 截圖
                    await popup_page.screenshot(
                        path=os.path.join(
                            OUTPUT_DIR, f"02_tab_{i}_{text}.png"
                        ),
                        full_page=True,
                    )
                except Exception as e:
                    logger.warning(f"  Tab '{text}' 切換失敗: {e}")

            # Dump 完整 HTML
            await dump_html(popup_page, "appointment_after_tabs")

        # === Step 6: 暫停，等你手動操作到產品 popup ===
        logger.info("\n" + "=" * 60)
        logger.info("⏸️  現在請手動操作 CRM:")
        logger.info("   1. 在約會記錄中找到產品相關欄位")
        logger.info("   2. 點擊觸發產品 popup")
        logger.info("   腳本會自動偵測新 popup 並 dump HTML")
        logger.info("=" * 60)

        # 監聽新 popup
        product_popup = None

        def on_page(new_page):
            nonlocal product_popup
            product_popup = new_page
            logger.info(f"\n🎯 偵測到新 Popup！URL: {new_page.url}")

        context.on("page", on_page)

        # 每 3 秒檢查一次，最多等 10 分鐘
        for tick in range(200):
            await asyncio.sleep(3)

            if product_popup:
                logger.info("等待產品 Popup 載入...")
                try:
                    await product_popup.wait_for_load_state(
                        "networkidle", timeout=15000
                    )
                except Exception:
                    pass
                await asyncio.sleep(3)

                logger.info("\n" + "=" * 60)
                logger.info("🔍 探索產品 Popup")
                logger.info("=" * 60)

                # 截圖
                await product_popup.screenshot(
                    path=os.path.join(OUTPUT_DIR, "03_product_popup.png"),
                    full_page=True,
                )

                # Dump ID
                await dump_all_ids(product_popup, "product_popup")

                # Dump HTML
                await dump_html(product_popup, "product_popup")

                # 搜尋關鍵字
                await search_keywords(
                    product_popup, PRODUCT_KEYWORDS, "product_popup"
                )

                logger.info("\n✅ 產品 Popup 探索完成！")
                logger.info(f"   結果已輸出到: {OUTPUT_DIR}/")

                # 繼續監聽更多 popup (可能還有)
                product_popup = None
                logger.info("繼續監聽更多 Popup... (CTRL+C 結束)")

            # 每 30 秒報告一次
            if tick > 0 and tick % 10 == 0:
                logger.info(f"  ⏳ 已等待 {tick * 3} 秒，持續監聽中...")

        logger.info("⏱️ 等待超時，關閉瀏覽器")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())

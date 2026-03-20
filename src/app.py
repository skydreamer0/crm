"""
CRM 操作介面 — Flask Web Server (app.py)
=============================================

提供 Web GUI 供用戶貼入待訪名單，即時預覽解析結果、產品匹配，
並可一鍵觸發 CRM 自動化流程。

主要路由:
  - GET  /           → 主頁面 (index.html)
  - POST /api/parse   → 解析待訪名單文字，回傳結構化資料
  - POST /api/execute  → 在背景執行緝程啟動 CRM 自動化
  - GET  /api/status   → 查詢自動化執行進度

啟動方式:
  python src/app.py   → 開在 http://127.0.0.1:5050
"""
# === 標準庫 ===
import sys
import os
import json
import random
import asyncio
import threading

# === 第三方套件 ===
from flask import Flask, render_template, request, jsonify

# === 本地模組 ===
sys.path.insert(0, os.path.dirname(__file__))

from visit_list_parser import (
    parse_visit_list,
    select_products,
    get_product_info,
    get_random_description,
    VisitEntry,
)
from create_appointments import run_automation

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Shared automation state (thread-safe via GIL for simple dict updates)
# ---------------------------------------------------------------------------
_automation_state = {
    "running": False,
    "progress": [],      # list of progress dicts from the callback
    "error": None,
    "result": None,
}


def _reset_state():
    _automation_state["running"] = False
    _automation_state["progress"] = []
    _automation_state["error"] = None
    _automation_state["result"] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Serve the main GUI page."""
    return render_template("index.html")


@app.route("/api/parse", methods=["POST"])
def api_parse():
    """
    Parse a raw visit-list text block.

    Request body (JSON):
        { "text": "慈濟/URO/吳書雨/B\n耕莘/OBS/王小明/A" }

    Response (JSON):
        { "entries": [ { ... }, ... ] }
    """
    data = request.get_json(force=True)
    raw_text = data.get("text", "")

    if not raw_text.strip():
        return jsonify({"entries": [], "error": "請輸入待訪名單"}), 400

    entries = parse_visit_list(raw_text)
    results = []

    for entry in entries:
        selected = select_products(entry, count=2)
        products_detail = []
        for code in selected:
            info = get_product_info(code)
            desc = get_random_description(code)
            products_detail.append(
                {
                    "code": code,
                    "brand_name": info.get("brand_name", code),
                    "generic_name": info.get("generic_name", ""),
                    "description": desc,
                }
            )

        results.append(
            {
                "customer_name": entry.customer_name,
                "department_code": entry.department_code,
                "department_name_zh": entry.department_name_zh,
                "matched_products": entry.matched_products,
                "selected_products": products_detail,
                "raw_line": entry.raw_line,
            }
        )

    return jsonify({"entries": results, "count": len(results)})


@app.route("/api/execute", methods=["POST"])
def api_execute():
    """
    Trigger CRM automation in a background thread.

    Request body (JSON):
        { "text": "慈濟/URO/吳書雨/B\n耕莘/OBS/王小明/A" }

    Response (JSON):
        { "status": "started", "message": "..." }
    """
    if _automation_state["running"]:
        return jsonify({"status": "busy", "message": "自動化正在執行中，請稍後再試。"}), 409

    data = request.get_json(force=True)
    raw_text = data.get("text", "")

    if not raw_text.strip():
        return jsonify({"status": "error", "message": "沒有待執行的項目"}), 400

    # Parse entries
    entries = parse_visit_list(raw_text)
    if not entries:
        return jsonify({"status": "error", "message": "名單解析失敗，請檢查格式"}), 400

    # Reset & start
    _reset_state()
    _automation_state["running"] = True

    def progress_cb(msg):
        _automation_state["progress"].append(msg)

    def _run_in_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_automation(entries, progress_callback=progress_cb))
            _automation_state["result"] = "success"
        except Exception as e:
            _automation_state["error"] = str(e)
            _automation_state["result"] = "error"
        finally:
            _automation_state["running"] = False
            loop.close()

    t = threading.Thread(target=_run_in_thread, daemon=True)
    t.start()

    return jsonify({
        "status": "started",
        "message": f"已開始自動化處理 {len(entries)} 筆名單，請透過 /api/status 查詢進度。",
    })


@app.route("/api/status")
def api_status():
    """
    Poll automation progress.

    Response (JSON):
        { "running": bool, "progress": [...], "result": "success"|"error"|null, "error": str|null }
    """
    return jsonify(_automation_state)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import webbrowser
    import threading as _threading

    port = 5050

    def open_browser():
        webbrowser.open(f"http://127.0.0.1:{port}")

    # Open browser after a short delay
    _threading.Timer(1.2, open_browser).start()

    print(f"\n🚀 CRM 操作介面已啟動: http://127.0.0.1:{port}\n")
    app.run(host="127.0.0.1", port=port, debug=True, use_reloader=False)


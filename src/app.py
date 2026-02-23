"""
CRM 操作介面 — Flask Web Server

提供 Web GUI 供用戶貼入待訪名單，即時預覽解析結果、產品匹配，
並可一鍵觸發 CRM 自動化流程。
"""
import sys
import os
import json
import random

from flask import Flask, render_template, request, jsonify

# Ensure src/ is importable
sys.path.insert(0, os.path.dirname(__file__))

from visit_list_parser import (
    parse_visit_list,
    select_products,
    get_product_info,
    get_random_description,
)

app = Flask(__name__)


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
    Trigger CRM automation (placeholder).
    Will be wired to create_appointments.py in a future phase.
    """
    data = request.get_json(force=True)
    entries = data.get("entries", [])

    if not entries:
        return jsonify({"status": "error", "message": "沒有待執行的項目"}), 400

    # TODO: Wire to create_appointments.py automation
    return jsonify(
        {
            "status": "pending",
            "message": f"已收到 {len(entries)} 筆資料，CRM 自動化功能將於後續版本啟用。",
        }
    )


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import webbrowser
    import threading

    port = 5050

    def open_browser():
        webbrowser.open(f"http://127.0.0.1:{port}")

    # Open browser after a short delay
    threading.Timer(1.2, open_browser).start()

    print(f"\n🚀 CRM 操作介面已啟動: http://127.0.0.1:{port}\n")
    app.run(host="127.0.0.1", port=port, debug=True, use_reloader=False)

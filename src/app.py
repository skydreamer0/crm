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
import datetime
import threading
from collections import deque
from pathlib import Path

# 打包版將 Chromium 一併收在 bundle 內 (見 crm_automation.spec)，
# 需在 import playwright 之前指定從套件目錄尋找瀏覽器
if getattr(sys, "frozen", False):
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "0")

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
from settings_store import (
    get_effective_settings,
    get_public_settings,
    save_settings,
    settings_path,
    validate_effective_settings,
)


def _resource_path(relative_path: str) -> Path:
    """Resolve files both from source and from a PyInstaller bundle."""
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        return Path(bundle_dir) / relative_path
    return Path(__file__).resolve().parent / relative_path


app = Flask(__name__, template_folder=str(_resource_path("templates")))

# ---------------------------------------------------------------------------
# Shared automation state (protected by _state_lock)
# ---------------------------------------------------------------------------
MAX_PROGRESS_ENTRIES = 500   # progress 有界限，避免長時間執行時記憶體增長
MAX_TEXT_LENGTH = 20000      # 待訪名單文字上限

_state_lock = threading.Lock()
_cancel_event = threading.Event()
_automation_state = {
    "running": False,
    "progress": deque(maxlen=MAX_PROGRESS_ENTRIES),  # progress dicts from the callback
    "error": None,
    "result": None,
    "summary": None,     # 最終檢核報告 (complete / partial / failed / cancelled)
}


def _reset_state_locked():
    """Reset state fields. Caller must hold _state_lock."""
    _automation_state["progress"] = deque(maxlen=MAX_PROGRESS_ENTRIES)
    _automation_state["error"] = None
    _automation_state["result"] = None
    _automation_state["summary"] = None


def _snapshot_state() -> dict:
    """Return a JSON-serializable copy of the automation state."""
    with _state_lock:
        return {
            "running": _automation_state["running"],
            "progress": list(_automation_state["progress"]),
            "error": _automation_state["error"],
            "result": _automation_state["result"],
            "summary": _automation_state["summary"],
        }


def _validate_visit_text(data) -> tuple[str, str | None]:
    """Validate the raw visit-list text. Returns (text, error_message)."""
    if not isinstance(data, dict):
        return "", "請提供 JSON 物件"
    raw_text = data.get("text", "")
    if not isinstance(raw_text, str):
        return "", "text 欄位必須是文字"
    if len(raw_text) > MAX_TEXT_LENGTH:
        return "", f"名單文字過長 (上限 {MAX_TEXT_LENGTH} 字元)"
    if not raw_text.strip():
        return "", "請輸入待訪名單"
    return raw_text, None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    """Serve the main GUI page."""
    return render_template("index.html")


@app.route("/settings")
def settings_page():
    """Serve the standalone settings page."""
    return render_template("settings.html")


@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    """Return redacted per-user settings status."""
    return jsonify(get_public_settings())


@app.route("/api/settings", methods=["POST"])
def api_save_settings():
    """Save per-user settings without returning plaintext secrets."""
    data = request.get_json(force=True) or {}
    return jsonify(save_settings(data))


@app.route("/api/parse", methods=["POST"])
def api_parse():
    """
    Parse a raw visit-list text block.

    Request body (JSON):
        { "text": "慈濟/URO/吳書雨/B\n耕莘/OBS/王小明/A" }

    Response (JSON):
        { "entries": [ { ... }, ... ] }
    """
    data = request.get_json(force=True, silent=True)
    raw_text, text_error = _validate_visit_text(data)
    if text_error:
        return jsonify({"entries": [], "error": text_error}), 400

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
    data = request.get_json(force=True, silent=True)
    raw_text, text_error = _validate_visit_text(data)
    if text_error:
        return jsonify({"status": "error", "message": text_error}), 400

    run_date = data.get("date")
    if run_date is not None:
        if not isinstance(run_date, str):
            return jsonify({"status": "error", "message": "date 欄位必須是文字"}), 400
        run_date = run_date.strip() or None
        if run_date is not None:
            try:
                datetime.date.fromisoformat(run_date)
            except ValueError:
                return jsonify({"status": "error", "message": "日期格式錯誤，請使用 YYYY-MM-DD"}), 400

    settings = get_effective_settings()
    missing_fields = validate_effective_settings(settings)
    if missing_fields:
        return jsonify({
            "status": "error",
            "message": f"請先完成設定：{', '.join(missing_fields)}",
            "missing_fields": missing_fields,
            "settings_path": str(settings_path()),
        }), 400

    # Parse entries
    entries = parse_visit_list(raw_text)
    if not entries:
        return jsonify({"status": "error", "message": "名單解析失敗，請檢查格式"}), 400

    # 原子性檢查 busy 並佔用執行權，避免兩個請求同時通過檢查
    with _state_lock:
        if _automation_state["running"]:
            return jsonify({"status": "busy", "message": "自動化正在執行中，請稍後再試。"}), 409
        _reset_state_locked()
        _automation_state["running"] = True
    _cancel_event.clear()

    def progress_cb(msg):
        with _state_lock:
            _automation_state["progress"].append(msg)

    def _run_in_thread():
        try:
            # asyncio.run 統一處理 event loop 的建立、例外清理與關閉
            summary = asyncio.run(
                run_automation(
                    entries,
                    run_date=run_date,
                    progress_callback=progress_cb,
                    settings=settings,
                    cancel_event=_cancel_event,
                )
            )
            with _state_lock:
                _automation_state["summary"] = summary
                _automation_state["result"] = "success"
        except Exception as e:
            with _state_lock:
                _automation_state["error"] = str(e)
                _automation_state["result"] = "error"
        finally:
            with _state_lock:
                _automation_state["running"] = False

    t = threading.Thread(target=_run_in_thread, daemon=True)
    t.start()

    return jsonify({
        "status": "started",
        "message": f"已開始自動化處理 {len(entries)} 筆名單，請透過 /api/status 查詢進度。",
    })


@app.route("/api/cancel", methods=["POST"])
def api_cancel():
    """
    Request cancellation of the running automation.

    目前這筆約會會處理完才停止，未執行的筆數列入失敗名單 (原因: 使用者取消)。
    """
    with _state_lock:
        running = _automation_state["running"]
    if not running:
        return jsonify({"status": "idle", "message": "目前沒有執行中的自動化"}), 409

    _cancel_event.set()
    return jsonify({
        "status": "cancelling",
        "message": "已送出取消請求，目前這筆處理完後停止。",
    })


@app.route("/api/status")
def api_status():
    """
    Poll automation progress.

    Response (JSON):
        { "running": bool, "progress": [...], "result": "success"|"error"|null,
          "error": str|null, "summary": {...}|null }
    """
    return jsonify(_snapshot_state())


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

    print(f"\nCRM 操作介面已啟動: http://127.0.0.1:{port}\n")
    app.run(host="127.0.0.1", port=port, debug=not getattr(sys, "frozen", False), use_reloader=False)


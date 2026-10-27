"""
排程執行: 從週行程 Excel 取出當天名單並跑 CRM 自動化 (run_today.py)
=====================================================================

流程:
  1. 在週行程資料夾找含指定日期的 Weekly plan_*.xlsx
     (預設今天；18:00 前執行視為補跑前一天，對應排程錯過後隔天開機補跑)
  2. 取出當天上午 + 下午名單，以 HPK 模式解析 (同 /api/execute 的 HPK 路徑)
  3. 防重複: 當天已有跑到日報步驟的執行紀錄就不再送 (除非 --force)
  4. 寫入前跳 Windows 對話框確認 (10 分鐘無回應視為取消)；--auto 則直接送
  5. 執行 run_automation，結束跳摘要對話框，log 寫到 logs/scheduled/run_YYYYMMDD.log

週行程資料夾: --plan-dir 或 .env 的 WEEKLY_PLAN_DIR；也可用 --plan-file 指定單一檔案。

Exit code: 0 完成或當天無需執行 / 1 錯誤 / 2 有未完成筆數 / 3 使用者取消或逾時
"""
# === 標準庫 ===
import argparse
import asyncio
import datetime
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
# logs/ 與 config 皆以專案根目錄為相對路徑
os.chdir(PROJECT_ROOT)

# === 第三方套件 ===
from dotenv import load_dotenv

# === 本地模組 ===
from weekly_plan import find_day_plan
from visit_list_parser import parse_hpk_customer_list

logger = logging.getLogger("run_today")

HISTORY_DIR = PROJECT_ROOT / "logs" / "history"
SCHEDULED_LOG_DIR = PROJECT_ROOT / "logs" / "scheduled"
# 未指定 --date 時，在此時間前執行視為補跑前一天 (例如 20:30 錯過、隔天早上開機)
CATCH_UP_CUTOFF = datetime.time(18, 0)
CONFIRM_TIMEOUT_MS = 10 * 60 * 1000
SUMMARY_TIMEOUT_MS = 2 * 60 * 60 * 1000
DIALOG_TITLE = "CRM 週行程自動執行"

EXIT_OK, EXIT_ERROR, EXIT_INCOMPLETE, EXIT_CANCELLED = 0, 1, 2, 3

# MessageBox 旗標與回傳值
MB_OK, MB_OKCANCEL = 0x0, 0x1
MB_ICONERROR, MB_ICONQUESTION, MB_ICONWARNING, MB_ICONINFORMATION = 0x10, 0x20, 0x30, 0x40
MB_SETFOREGROUND, MB_TOPMOST = 0x10000, 0x40000
IDOK = 1


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="從週行程 Excel 執行當天的 CRM 約會建立")
    parser.add_argument("--date", help="執行日期 YYYY-MM-DD (預設今天)")
    parser.add_argument("--plan-dir", help="週行程資料夾 (預設 .env 的 WEEKLY_PLAN_DIR)")
    parser.add_argument("--plan-file", help="直接指定週行程檔案")
    parser.add_argument("--dry-run", action="store_true", help="只解析並列出名單，不連 CRM")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--confirm", dest="confirm", action="store_true", default=True,
                      help="寫入前跳對話框確認 (預設)")
    mode.add_argument("--auto", dest="confirm", action="store_false", help="不確認直接送出")
    parser.add_argument("--force", action="store_true", help="略過當天已執行過的防重複檢查")
    return parser.parse_args(argv)


def choose_run_date(date_arg: str | None, now: datetime.datetime) -> tuple[datetime.date, bool]:
    """
    Return (run_date, is_catch_up).

    沒指定日期且在 CATCH_UP_CUTOFF 之前執行 → 補跑前一天；只補一天，連續多天未跑需手動 --date。
    """
    if date_arg:
        return datetime.date.fromisoformat(date_arg), False
    if now.time() < CATCH_UP_CUTOFF:
        return now.date() - datetime.timedelta(days=1), True
    return now.date(), False


def setup_logging(run_date: datetime.date) -> Path:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    SCHEDULED_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = SCHEDULED_LOG_DIR / f"run_{run_date.strftime('%Y%m%d')}.log"
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root.addHandler(console)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    return log_path


def message_box(text: str, flags: int, timeout_ms: int) -> int:
    """Show a topmost Windows MessageBox; returns the button id (32000 on timeout, 0 off Windows)."""
    if sys.platform != "win32":
        return 0
    import ctypes
    user32 = ctypes.windll.user32
    return user32.MessageBoxTimeoutW(
        None, text, DIALOG_TITLE, flags | MB_TOPMOST | MB_SETFOREGROUND, 0, timeout_ms
    )


def history_date(record: dict) -> str:
    """Date a history record was run for: explicit run_date, else the day it started."""
    return (record.get("run_date") or str(record.get("start_time", ""))[:10]).replace("/", "-")


def find_previous_runs(run_date: datetime.date, history_dir: Path = HISTORY_DIR) -> list[Path]:
    """
    History files for `run_date` that reached the daily-report step.

    走到日報步驟就可能已在 CRM 留下日報/約會，再送一次會重複建立。
    """
    found = []
    if not history_dir.exists():
        return found
    for path in sorted(history_dir.glob("run_*.json")):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if history_date(record) != run_date.isoformat():
            continue
        if any(log.get("step") == "daily_report" for log in record.get("logs", [])):
            found.append(path)
    return found


def chromium_executable() -> Path:
    """Path Playwright will launch Chromium from (may not exist yet)."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        return Path(p.chromium.executable_path)


def ensure_browser_installed(executable=chromium_executable, run=subprocess.run) -> None:
    """
    Install Playwright Chromium once when its executable is missing.

    ms-playwright 快取被清掉時 launch 會失敗；先補裝再繼續，補裝失敗才報錯。
    """
    path = executable()
    if path.exists():
        return
    logger.warning("找不到 Playwright Chromium (%s)，執行 playwright install chromium...", path)
    result = run([sys.executable, "-m", "playwright", "install", "chromium"],
                 capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0 or not executable().exists():
        raise RuntimeError(f"安裝 Playwright Chromium 失敗: {(result.stderr or result.stdout).strip()[-300:]}")
    logger.info("✅ Playwright Chromium 安裝完成")


def build_entries(plan):
    """Parse plan lines with the HPK parser, keeping each entry's 上午/下午 slot."""
    entries = []
    for period in dict.fromkeys(p for p, _ in plan.entries):
        lines = [line for p, line in plan.entries if p == period]
        parsed = parse_hpk_customer_list("\n".join(lines))
        for entry in parsed:
            entry.visit_period = period
        entries.extend(parsed)
    return entries


def describe_plan(plan, entries) -> str:
    lines = [f"日期: {plan.date.isoformat()}  ({plan.source.name} / {plan.sheet} 欄 {plan.column})"]
    for period, mark in plan.off_periods.items():
        lines.append(f"{period}: {mark} (跳過)")
    for idx, entry in enumerate(entries, start=1):
        lines.append(f"{idx:>2}. [{entry.visit_period}] {entry.hospital_name}/{entry.department_name_zh}/{entry.customer_name}")
    for coord, text, reason in plan.skipped:
        lines.append(f"略過 {coord} {text} — {reason}")
    return "\n".join(lines)


def summarize(summary: dict, history_files: list[Path]) -> tuple[str, int, int]:
    """Return (message, icon flag, exit code) for the finished run."""
    complete = summary.get("complete", [])
    warnings = summary.get("product_warnings", [])
    failed = summary.get("failed", [])
    lines = [
        f"預計 {summary.get('total', 0)} 筆：完成 {len(complete)}、選填產品警告 {len(warnings)}、失敗 {len(failed)}",
    ]
    for item in failed:
        orphan = " [約會可能已存入 CRM，請檢查]" if item.get("orphan") else ""
        lines.append(f"❌ {item.get('name')} — {str(item.get('error', ''))[:60]}{orphan}")
    if failed:
        lines.extend(f"紀錄: {p}" for p in history_files)
        return "\n".join(lines), MB_ICONWARNING, EXIT_INCOMPLETE
    return "\n".join(lines), MB_ICONINFORMATION, EXIT_OK


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        run_date, catch_up = choose_run_date(args.date, datetime.datetime.now())
    except ValueError:
        print("日期格式錯誤，請使用 YYYY-MM-DD", file=sys.stderr)
        return EXIT_ERROR

    log_path = setup_logging(run_date)
    load_dotenv(PROJECT_ROOT / ".env")
    notify = not args.dry_run
    logger.info(
        "=== 週行程排程執行 %s%s%s ===",
        run_date.isoformat(),
        " (補跑前一天)" if catch_up else "",
        " (dry-run)" if args.dry_run else "",
    )

    def fail(message: str) -> int:
        logger.error(message)
        if notify:
            message_box(f"{message}\n\nLog: {log_path}", MB_OK | MB_ICONERROR, SUMMARY_TIMEOUT_MS)
        return EXIT_ERROR

    plan_file = Path(args.plan_file) if args.plan_file else None
    plan_dir = Path(args.plan_dir or os.getenv("WEEKLY_PLAN_DIR", "")) if not plan_file else None
    if plan_file is None and (plan_dir is None or not str(plan_dir) or not plan_dir.is_dir()):
        return fail(f"找不到週行程資料夾，請用 --plan-dir 或在 .env 設定 WEEKLY_PLAN_DIR (目前: {plan_dir})")

    try:
        plan = find_day_plan(run_date, folder=plan_dir, plan_file=plan_file)
    except Exception as e:
        return fail(f"讀取週行程失敗: {e}")
    if plan is None:
        return fail(f"週行程中找不到 {run_date.isoformat()} 這一天")

    entries = build_entries(plan)
    description = describe_plan(plan, entries)
    if catch_up:
        description = f"⚠️ 補跑前一天 ({run_date.isoformat()})\n{description}"
    logger.info("當天名單:\n%s", description)

    if not entries:
        logger.info("當天沒有需要建立的約會，結束。")
        return EXIT_OK
    if args.dry_run:
        logger.info("dry-run: 共 %d 筆，未連線 CRM。", len(entries))
        return EXIT_OK

    previous = find_previous_runs(run_date)
    if previous and not args.force:
        names = ", ".join(p.name for p in previous)
        logger.warning("當天已有執行紀錄，跳過以免重複建立約會: %s", names)
        message_box(
            f"{run_date.isoformat()} 已有執行紀錄，為避免重複建立約會本次未送出。\n"
            f"紀錄: {names}\n確認 CRM 後如需重跑，請執行 run_today.bat --date {run_date.isoformat()} --force",
            MB_OK | MB_ICONWARNING,
            SUMMARY_TIMEOUT_MS,
        )
        return EXIT_OK

    from settings_store import get_effective_settings, validate_effective_settings
    settings = get_effective_settings()
    missing = validate_effective_settings(settings)
    if missing:
        return fail(f"請先在 CRM 設定頁完成設定: {', '.join(missing)}")
    settings["business_unit"] = "HPK"

    if args.confirm:
        answer = message_box(
            f"即將寫入公司 CRM，按「確定」執行，「取消」不送出 (10 分鐘未回應視為取消)。\n\n{description}",
            MB_OKCANCEL | MB_ICONQUESTION,
            CONFIRM_TIMEOUT_MS,
        )
        if answer != IDOK:
            logger.warning("使用者取消或逾時未確認 (回傳 %s)，未送出。", answer)
            return EXIT_CANCELLED

    try:
        ensure_browser_installed()
    except Exception as e:
        return fail(f"瀏覽器準備失敗 (尚未連線 CRM): {e}")

    from create_appointments import run_automation
    before = set(HISTORY_DIR.glob("run_*.json")) if HISTORY_DIR.exists() else set()
    started = datetime.datetime.now().timestamp()
    try:
        summary = asyncio.run(run_automation(entries, run_date=run_date.isoformat(), settings=settings))
    except Exception as e:
        new_files = sorted(set(HISTORY_DIR.glob("run_*.json")) - before)
        details = [f"紀錄: {p}" for p in new_files] or ["未產生執行紀錄 (尚未登入 CRM)"]
        screenshot = PROJECT_ROOT / "logs" / "screenshots" / "error.png"
        if screenshot.exists() and screenshot.stat().st_mtime >= started:
            details.append(f"截圖: {screenshot}")
        return fail(f"自動化執行失敗: {e}\n" + "\n".join(details))

    new_files = sorted(set(HISTORY_DIR.glob("run_*.json")) - before)
    message, icon, code = summarize(summary, new_files)
    logger.info("執行結果:\n%s", message)
    message_box(f"{message}\n\nLog: {log_path}", MB_OK | icon, SUMMARY_TIMEOUT_MS)
    return code


if __name__ == "__main__":
    sys.exit(main())

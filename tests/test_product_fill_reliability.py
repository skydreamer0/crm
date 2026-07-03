"""產品填寫可靠性修復的單元測試。

背景: 改版後產品視窗只等「欄位可見 + 500ms」就開始打字，
CRM JS 尚未綁定 autocomplete，導致產品從未真正被 key 入。
此測試組定義修復後的三個行為:
  1. selectors.yaml 提供「欄位已初始化」的就緒訊號 (data-initialized)
  2. TIMING 保留足夠的 JS 綁定緩衝
  3. 產品流程失敗時能靜默關閉殘留 popup (close_popup_quietly)
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from create_appointments import TIMING, load_selectors, close_popup_quietly


def test_product_selectors_include_initialized_ready_signal():
    # 真實 DOM (docs/product_fields/product_popup_frame_1.html:4394):
    # div#new_product 在 CRM JS 綁定完行為後才會帶 data-initialized="true"
    sel = load_selectors()
    assert sel["product"]["product_ready"] == "div#new_product[data-initialized='true']"


def test_timing_reserves_product_form_bind_buffer():
    # 改版前實測可用的緩衝約 3000ms，修復後至少要保留 1500ms
    assert TIMING["product_form_bind"] >= 1500


class FakePopup:
    """最小 duck-type 的 Playwright page 替身 (只有 is_closed/close)。"""

    def __init__(self, closed=False, close_error=None):
        self.closed = closed
        self.close_error = close_error
        self.close_calls = 0

    def is_closed(self):
        return self.closed

    async def close(self):
        self.close_calls += 1
        if self.close_error:
            raise self.close_error
        self.closed = True


def test_close_popup_quietly_closes_open_popup():
    popup = FakePopup()
    asyncio.run(close_popup_quietly(popup))
    assert popup.close_calls == 1
    assert popup.closed


def test_close_popup_quietly_skips_already_closed():
    popup = FakePopup(closed=True)
    asyncio.run(close_popup_quietly(popup))
    assert popup.close_calls == 0


def test_close_popup_quietly_swallows_close_errors():
    # CRM 自己把視窗關掉時 close() 會丟 Target closed，不應讓它中斷流程
    popup = FakePopup(close_error=RuntimeError("Target page, context or browser has been closed"))
    asyncio.run(close_popup_quietly(popup))
    assert popup.close_calls == 1


def test_close_popup_quietly_accepts_none():
    # popup 尚未建立 (例外發生在 expect_page 之前) 時傳入 None 也要安全
    asyncio.run(close_popup_quietly(None))

"""「의견 보내기」 시리즈 공통 후속 정리(2026-10-27): 키보드 접근 · 툴팁 · 페이지 언어 규칙 · README.

창 시험 도구(임시 설정 파일, 기록만 하는 브라우저, 소켓 차단 후 0건 단언)는 test_feedback 의 것을
그대로 쓴다. 실제 브라우저·실제 네트워크·OS 마우스·키보드는 쓰지 않는다(Tk 안의 이벤트만).
"""

from __future__ import annotations

import re
import sys
import tkinter as tk
import urllib.parse
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import i18n  # noqa: E402
import update_check as uc  # noqa: E402
import version  # noqa: E402
from test_feedback import close, env, expected, log_text, no_sockets, start, switch  # noqa: E402,F401
from test_lang_ja import _missing_glyphs  # noqa: E402

KO_PAGE = "https://chaekgalpi.co.kr/tools/pdftoc"
EN_PAGE = "https://chaekgalpi.co.kr/en/tools/pdftoc"
TIPS = {
    "ko": "안 되는 것·불편한 것·바라는 기능을 알려 주세요(브라우저가 열립니다)",
    "en": "Tell us what's broken or missing (opens your browser)",
    "ja": "不具合・ご要望をお知らせください（ブラウザが開きます）",
    "zh": "告诉我们问题或建议（将打开浏览器）",
}


@pytest.fixture
def quick_tip(env, monkeypatch):
    """툴팁 지연을 0 으로(시험이 기다리지 않게)."""
    monkeypatch.setattr(env["gui"].Tooltip, "DELAY_MS", 0)
    return env


def hover(app):
    app.feedback_link.event_generate("<Enter>", x=2, y=2)
    for _ in range(3):
        app.root.update()
    return app.feedback_tip.tip


def tip_label(tip: tk.Toplevel) -> tk.Label:
    (label,) = tip.winfo_children()
    return label


def press(app, key: str):
    app.feedback_link.focus_force()
    app.root.update()
    app.feedback_link.event_generate(key)
    app.root.update()


# ------------------------------------------------------------------ a. 키보드

def test_link_takes_focus_in_tab_order(env):
    app = start(env, "ko")
    link = app.feedback_link
    assert str(link.cget("takefocus")) in ("1", "True", "true")
    check = link.master.winfo_children()[0]
    assert check.winfo_class() == "TCheckbutton"
    assert check.tk_focusNext() is link                  # 「새 버전 확인」 다음 Tab 이 링크
    assert link.tk_focusPrev() is check                  # Shift+Tab 은 되돌아간다
    close(app)


@pytest.mark.parametrize("key", ["<Return>", "<space>"])
@pytest.mark.parametrize("lang", i18n.LANGS)
def test_enter_and_space_open_exactly_once(env, lang, key):
    app = start(env, lang)
    before = app.var_update_check.get()
    press(app, key)
    assert env["opened"] == [expected(lang)]
    assert app.var_update_check.get() == before          # 옆 체크박스는 건드리지 않는다
    close(app)


def test_keypad_enter_is_bound_too(env):
    """Windows Tk 는 숫자판 Enter 도 Return 으로 주지만, 다른 환경을 위해 KP_Enter 에도 묶어 둔다."""
    app = start(env, "ko")
    assert app.feedback_link.bind("<KP_Enter>")
    close(app)


def test_other_keys_do_nothing(env):
    app = start(env, "ko")
    for key in ("<Tab>", "<Escape>", "<a>", "<Up>"):
        press(app, key)
    assert env["opened"] == []
    close(app)


def test_focus_is_visible(env):
    app = start(env, "ko")
    link = app.feedback_link
    assert link.cget("style") == "Link.TLabel"
    link.event_generate("<FocusIn>")
    app.root.update()
    assert link.cget("style") == "LinkFocus.TLabel"
    st = tk.ttk.Style()
    assert st.lookup("LinkFocus.TLabel", "background") != st.lookup("Link.TLabel", "background")
    link.event_generate("<FocusOut>")
    app.root.update()
    assert link.cget("style") == "Link.TLabel"
    close(app)


def test_keyboard_still_works_after_language_switch(env):
    app = start(env, "ko")
    switch(app, "ja")
    press(app, "<Return>")
    switch(app, "en")
    press(app, "<space>")
    assert env["opened"] == [expected("ja"), expected("en")]
    close(app)


def test_keyboard_failure_shows_copyable_address(env):
    app = start(env, "ja")
    env["result"] = False
    press(app, "<Return>")
    assert i18n.STRINGS["ja"]["feedback_failed"] in log_text(app)
    assert expected("ja") in log_text(app).splitlines()
    close(app)


# ------------------------------------------------------------------ b. 툴팁

def test_tooltip_wording():
    for lang, text in TIPS.items():
        assert i18n.STRINGS[lang]["feedback_tip"] == text
    assert len(set(TIPS.values())) == 4 and all(t.strip() for t in TIPS.values())


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_hover_shows_and_leave_hides(quick_tip, lang):
    app = start(quick_tip, lang)
    assert app.feedback_tip.tip is None
    tip = hover(app)
    assert tip is not None and tip.winfo_exists() and tip.winfo_ismapped()
    assert tip_label(tip).cget("text") == TIPS[lang]
    app.feedback_link.event_generate("<Leave>")
    app.root.update()
    assert app.feedback_tip.tip is None and not tip.winfo_exists()
    assert quick_tip["opened"] == []                      # 올리기만 해서는 브라우저를 열지 않는다
    close(app)


def test_tooltip_waits_before_showing(env):
    app = start(env, "ko")
    app.feedback_link.event_generate("<Enter>", x=2, y=2)
    app.root.update()
    assert app.feedback_tip.tip is None                   # 지나가기만 하면 뜨지 않는다
    app.feedback_link.event_generate("<Leave>")
    app.root.update()
    app.root.after(env["gui"].Tooltip.DELAY_MS + 100)
    app.root.update()
    assert app.feedback_tip.tip is None
    close(app)


def test_click_hides_tooltip_and_opens_once(quick_tip):
    app = start(quick_tip, "ko")
    hover(app)
    app.feedback_link.event_generate("<ButtonPress-1>", x=2, y=2)
    app.root.update()
    assert app.feedback_tip.tip is None
    assert quick_tip["opened"] == [expected("ko")]
    close(app)


def test_hover_twice_makes_one_tooltip(quick_tip):
    app = start(quick_tip, "en")
    first = hover(app)
    second = hover(app)
    assert first is second
    tops = [w for w in app.root.winfo_children() if isinstance(w, tk.Toplevel)]
    tips = [w for w in app.feedback_link.winfo_children() if isinstance(w, tk.Toplevel)]
    assert tops == [] and len(tips) == 1
    close(app)


def test_language_switch_changes_tooltip_text(quick_tip):
    app = start(quick_tip, "ko")
    seen = []
    for lang in ("ko", "en", "zh", "ja", "ko"):
        if lang != i18n.get_lang():
            switch(app, lang)
        seen.append(tip_label(hover(app)).cget("text"))
        app.feedback_link.event_generate("<Leave>")
        app.root.update()
    assert seen == [TIPS[x] for x in ("ko", "en", "zh", "ja", "ko")]
    close(app)


def test_switch_while_tooltip_is_open_or_pending(env):
    """툴팁이 떠 있거나 뜨기를 기다리는 중에 언어를 바꿔도 오류 없이 사라진다."""
    app = start(env, "ko")
    app.feedback_tip.show()
    old = app.feedback_tip
    switch(app, "ja")
    assert old.tip is None and app.feedback_tip is not old and app.feedback_tip.tip is None
    app.feedback_link.event_generate("<Enter>", x=2, y=2)   # 예약만 된 상태
    app.root.update()
    pending = app.feedback_tip
    switch(app, "en")
    app.root.after(env["gui"].Tooltip.DELAY_MS + 100)
    app.root.update()
    assert pending.tip is None and pending._job is None
    close(app)


def _inside(tip, root):
    x, y, w, h = tip.winfo_rootx(), tip.winfo_rooty(), tip.winfo_width(), tip.winfo_height()
    sw, sh = tip.winfo_screenwidth(), tip.winfo_screenheight()
    on_screen = x >= 0 and y >= 0 and x + w <= sw and y + h <= sh
    in_window = root.winfo_rootx() <= x and x + w <= root.winfo_rootx() + root.winfo_width()
    return on_screen, in_window, (x, y, w, h)


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_tooltip_fits_in_the_minimum_window(quick_tip, lang):
    app = start(quick_tip, lang)
    app.root.geometry("640x660+40+40")
    app.root.update()
    assert (app.root.winfo_width(), app.root.winfo_height()) == (640, 660)
    tip = hover(app)
    on_screen, in_window, box = _inside(tip, app.root)
    assert on_screen and in_window, box
    label = tip_label(tip)
    assert label.winfo_width() >= label.winfo_reqwidth() and label.winfo_height() >= label.winfo_reqheight()
    close(app)


@pytest.mark.parametrize("corner", ["right", "bottom-right"])
def test_tooltip_stays_on_screen_at_the_screen_edge(quick_tip, corner):
    app = start(quick_tip, "ko")
    sw, sh = app.root.winfo_screenwidth(), app.root.winfo_screenheight()
    y = sh - 660 - 10 if corner == "bottom-right" else 0
    app.root.geometry(f"640x660+{sw - 640}+{max(0, y)}")
    app.root.update()
    tip = hover(app)
    on_screen, _, box = _inside(tip, app.root)
    assert on_screen, box
    close(app)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 글꼴")
def test_japanese_tooltip_has_every_glyph(quick_tip):
    gui = quick_tip["gui"]
    app = start(quick_tip, "ja")
    label = tip_label(hover(app))
    family = tk.font.Font(root=app.root, font=label.cget("font")).actual("family")
    assert family in gui.LANG_FONTS["ja"], family          # 맑은 고딕(□)이 아니다
    assert _missing_glyphs(family, TIPS["ja"]) == ""
    close(app)


def test_other_languages_tooltip_uses_malgun_gothic(quick_tip):
    app = start(quick_tip, "ko")
    for lang in ("ko", "en", "zh"):
        if lang != i18n.get_lang():
            switch(app, lang)
        label = tip_label(hover(app))
        assert "Malgun Gothic" in str(label.cget("font")), lang
        app.feedback_link.event_generate("<Leave>")
        app.root.update()
    close(app)


def test_tooltip_does_not_add_clipped_widgets(quick_tip):
    """툴팁은 따로 뜨는 작은 창이라 본 창의 배치(잘림·겹침 시험 대상)를 바꾸지 않는다."""
    from test_lang_ja import layout_problems
    app = start(quick_tip, "ja")
    app.root.geometry("640x660")
    app.root.update()
    hover(app)
    assert layout_problems(app) == []
    close(app)


# ------------------------------------------------------------------ c. 페이지 언어 규칙

KOREAN = ["ko", "ko-KR", "ko_KR", "KO", " ko "]
OTHERS = ["en", "EN", "en-US", "ja", "ja-JP", "zh", "zh-CN", "zh_CN", "zh-TW", "zh-Hant-TW",
          "fr", "de", "de-DE", "es", "pt-BR", "ru", "vi", "xx", "kor", "k", "jp"]
EMPTY = [None, "", "   "]


def fb(lang):
    return uc.feedback_url("pdftoc", "1.2.3", lang)


@pytest.mark.parametrize("lang", KOREAN)
def test_korean_goes_to_korean_page(lang):
    assert fb(lang).startswith(KO_PAGE + "?")
    assert uc.is_korean(lang)


@pytest.mark.parametrize("lang", OTHERS)
def test_every_other_language_goes_to_english_page(lang):
    assert fb(lang).startswith(EN_PAGE + "?")
    assert not uc.is_korean(lang)


@pytest.mark.parametrize("lang", EMPTY)
def test_empty_language_follows_the_default_screen_language(lang):
    assert fb(lang) == fb(uc.DEFAULT_LANG) == fb("en")


def test_default_language_is_the_tools_fallback():
    i18n.set_lang("xx")                                   # 모르는 언어 → 이 툴은 영어 화면
    assert i18n.get_lang() == uc.DEFAULT_LANG == "en"


@pytest.mark.parametrize("lang", KOREAN + OTHERS + EMPTY)
@pytest.mark.parametrize("v", ["1.2.3", "", None, version.APP_VERSION])
def test_every_address_has_the_same_shape(lang, v):
    u = uc.feedback_url(version.UPDATE_SLUG, v, lang)
    assert u.startswith("https://chaekgalpi.co.kr/") and u.endswith("#feedback")
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(u).query)
    assert q["utm_source"] == ["app"] and q["utm_medium"] == ["feedback"]
    assert urllib.parse.urlsplit(u).path in ("/tools/pdftoc", "/en/tools/pdftoc")


INFO = uc.UpdateInfo("9.0.0", "1.0.0", KO_PAGE + "?utm_medium=update", EN_PAGE + "?utm_medium=update")


@pytest.mark.parametrize("lang", KOREAN)
def test_update_notice_korean_page(lang):
    assert INFO.page_for(lang) == INFO.url


@pytest.mark.parametrize("lang", OTHERS + EMPTY)
def test_update_notice_follows_the_same_rule(lang):
    assert INFO.page_for(lang) == INFO.url_en
    assert ("/en/" in INFO.page_for(lang)) == ("/en/" in fb(lang))


@pytest.mark.parametrize("lang", KOREAN + OTHERS + EMPTY)
def test_update_notice_without_english_page_opens_the_one_it_has(lang):
    assert uc.UpdateInfo("9.0.0", "1.0.0", KO_PAGE).page_for(lang) == KO_PAGE


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_update_notice_button_follows_the_rule(env, lang):
    app = start(env, lang)
    app._update_info = INFO
    app._show_update_notice()
    app._update_open()
    assert env["opened"] == [INFO.url if lang == "ko" else INFO.url_en]
    close(app)


# ------------------------------------------------------------------ d. README

def readme_sections() -> dict[str, str]:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    parts = re.split(r"^## ", text, flags=re.M)
    return {p.splitlines()[0].strip(): p for p in parts[1:]}


def feedback_links(section: str) -> list[str]:
    return re.findall(r"https://chaekgalpi\.co\.kr/[^\s)）]*#feedback", section)


@pytest.mark.parametrize("name", ["中文", "日本語"])
def test_readme_zh_ja_feedback_link_is_english_page(name):
    links = feedback_links(readme_sections()[name])
    assert links and all(u == EN_PAGE + "#feedback" for u in links), links


def test_readme_ko_en_feedback_links():
    s = readme_sections()
    assert feedback_links(s["한국어"]) == [KO_PAGE + "#feedback"]
    assert feedback_links(s["English"]) == [EN_PAGE + "#feedback"]

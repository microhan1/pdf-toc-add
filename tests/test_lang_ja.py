"""일본어(ja) 화면 시험: 키 동등성, 언어 전환·저장·복원, 레이아웃, 글꼴, 오류 문구, 회귀, 잘못된 언어 값.

창은 파이썬 안에서 띄우고 콜백을 직접 부른다(OS 마우스·키보드를 쓰지 않는다). 설정은 임시 폴더의
config.json 만 쓰고, 브라우저는 기록만 하는 가짜다. 실제 네트워크는 conftest 가 막는다.
"""

from __future__ import annotations

import ctypes
import json
import re
import string
import sys
import tkinter as tk
import webbrowser
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import i18n  # noqa: E402
import pdf_toc_add as core  # noqa: E402
import update_check as uc  # noqa: E402
import version  # noqa: E402

HANGUL = re.compile(r"[가-힣ᄀ-ᇿ㄰-㆏]")
KANA = re.compile(r"[぀-ヿ]")
# 일본어 화면에서 원문(영어)과 같아도 되는 키: 글자가 PDF 뿐이거나 기호뿐
SAME_AS_EN_OK = {"sec_pdf", "hint_fmt"}


def fields(text: str) -> list[tuple[str, str]]:
    """자리표시자 (이름, 서식) 목록. 개수까지 비교하려고 집합이 아니라 정렬한 목록."""
    return sorted((f, spec or "") for _, f, spec, _ in string.Formatter().parse(text) if f is not None)


# ------------------------------------------------------------------ a. 키 동등성

def test_ja_is_registered():
    assert "ja" in i18n.LANGS and i18n.LANG_NAMES["ja"] == "日本語"
    assert len(set(i18n.LANG_NAMES.values())) == len(i18n.LANGS)


def test_ja_keys_equal_ko_keys():
    ko, ja = set(i18n.STRINGS["ko"]), set(i18n.STRINGS["ja"])
    assert ja == ko, {"ko에만": ko - ja, "ja에만": ja - ko}


@pytest.mark.parametrize("key", sorted(i18n.STRINGS["ko"]))
def test_ja_value_not_empty_and_same_placeholders(key):
    ja = i18n.STRINGS["ja"][key]
    assert isinstance(ja, str) and ja.strip(), key
    assert fields(ja) == fields(i18n.STRINGS["ko"][key]), key


@pytest.mark.parametrize("key", sorted(i18n.STRINGS["ko"]))
def test_ja_formats_with_every_placeholder(key):
    kw = {name.split("!")[0]: 1 for name, _ in fields(i18n.STRINGS["ja"][key])}
    i18n.STRINGS["ja"][key].format(**kw)


def test_ja_has_no_korean_and_is_translated():
    """한국어가 섞이지 않았고, 영어 원문을 그대로 둔 키가 없다."""
    ja, en = i18n.STRINGS["ja"], i18n.STRINGS["en"]
    assert [k for k, v in ja.items() if HANGUL.search(v)] == []
    assert sorted(k for k in ja if ja[k] == en[k]) == sorted(SAME_AS_EN_OK)
    # 중국어 문구를 그대로 붙여 넣지 않았다(같은 것은 한자 낱말 하나뿐인 「更新」과 기호뿐인 키)
    assert sorted(k for k in ja if ja[k] == i18n.STRINGS["zh"][k]) == sorted(SAME_AS_EN_OK | {"btn_update"})
    # 문장인 문구(자리표시자·공백을 빼고 10글자 넘는 것)에는 가나가 들어간다. cli_lang 은 한자와 언어 코드뿐
    assert [k for k, v in ja.items() if len(re.sub(r"\{[^}]*\}|\s", "", v)) > 10 and not KANA.search(v)] == ["cli_lang"]


def test_feedback_words():
    assert i18n.STRINGS["ja"]["btn_feedback"] == "ご意見を送る"
    assert "ブラウザー" in i18n.STRINGS["ja"]["feedback_failed"]


def test_ja_examples_parse():
    """일본어 예시 목차·CLI 도움말의 예가 실제로 읽힌다."""
    parsed = core.parse_toc(i18n.STRINGS["ja"]["example_toc"])
    assert parsed.offset == 0
    assert [(e.level, e.title, e.page) for e in core.flatten(parsed.entries)][:3] == [
        (0, "はじめに", 1), (0, "第1章 序論", 2), (1, "1.1 背景", 3)]
    epilog = [ln.split("<-")[0] for ln in i18n.STRINGS["ja"]["cli_epilog"].splitlines()[1:6]]
    flat = core.flatten(core.parse_toc("\n".join(epilog)).entries)
    assert [(e.level, e.page) for e in flat] == [(0, 12), (0, 25), (1, 26), (1, 31), (0, 40)]


# ------------------------------------------------------------------ 창 시험 공통

@pytest.fixture
def env(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(i18n, "config_path", lambda: cfg)
    monkeypatch.delenv("PDF_TOC_LANG", raising=False)
    import pdf_toc_gui as gui

    state = {"opened": [], "result": True, "cfg": cfg, "gui": gui, "tmp": tmp_path}

    def fake_open(u, *a, **kw):
        state["opened"].append(u)
        return state["result"]

    monkeypatch.setattr(webbrowser, "open", fake_open)
    yield state
    import gc

    gc.collect()


def start(env, lang="ko", settings=None, geometry=None):
    i18n.set_lang(lang)
    if settings is not None:
        env["cfg"].write_text(settings if isinstance(settings, str) else json.dumps(settings), encoding="utf-8")
    gui = env["gui"]
    root = gui.TkinterDnD.Tk() if gui._DND else tk.Tk()
    app = gui.App(root)
    if geometry:
        root.geometry(geometry)
    root.update()
    return app


def close(app):
    for job in app.root.tk.splitlist(app.root.tk.call("after", "info")):
        app.root.after_cancel(job)
    app._detect_cancel.set()
    if app._detect_thread is not None:
        app._detect_thread.join(timeout=20)
    app._on_close()
    try:
        app.root.update()
    except Exception:
        pass


def switch(app, lang):
    app.lang_var.set(i18n.LANG_NAMES[lang])
    app._on_lang_change()
    app.root.update()


def walk(w):
    yield w
    for c in w.winfo_children():
        yield from walk(c)


TEXT_CLASSES = ("Label", "TLabel", "Button", "TButton", "TCheckbutton")


def widget_texts(app) -> list[str]:
    out = []
    for w in walk(app.root):
        if w.winfo_class() in TEXT_CLASSES:
            t = w.cget("text")
            if t:
                out.append(str(t))
    return out


def screen_keys(gui) -> list[str]:
    keys = ["app_subtitle", "lbl_language", "pdf_drop_hint" if gui._DND else "pdf_click_hint",
            "sec_pdf_hint_dnd" if gui._DND else "sec_pdf_hint_nodnd", "btn_browse", "sec_toc", "sec_toc_hint",
            "btn_open_txt", "btn_example", "btn_clear", "sec_settings", "lbl_offset", "btn_detect", "offset_hint",
            "lbl_output", "btn_change", "opt_update_check", "btn_feedback", "btn_preview", "btn_build",
            "sec_result", "sec_result_hint", "btn_update", "btn_later"]
    if gui._DND:
        keys.append("toc_drop_hint")
    return keys


# ------------------------------------------------------------------ b. 언어 전환·저장·복원

def test_switch_ko_ja_en_zh_ja_changes_every_label(env):
    gui = env["gui"]
    app = start(env, "ko")
    app._update_info = uc.UpdateInfo("9.9.9", version.APP_VERSION, "https://chaekgalpi.co.kr/tools/pdftoc")
    app._show_update_notice()  # 맨 아래 상태 줄(새 버전 알림)도 다시 그려지는지
    for lang in ("ja", "en", "zh", "ja"):
        switch(app, lang)
        texts = widget_texts(app)
        table = i18n.STRINGS[lang]
        assert app.root.title() == table["app_title"]
        assert app.lang_var.get() == i18n.LANG_NAMES[lang]
        missing = [k for k in screen_keys(gui) if table[k] not in texts]
        assert missing == [], (lang, missing)
        assert app.lbl_update.cget("text") == table["update_available"].format(latest="9.9.9",
                                                                               current=version.APP_VERSION)
        own = set(table.values())
        leftovers = [t for t in texts if t not in own and any(t in i18n.STRINGS[o].values()
                                                               for o in i18n.LANGS if o != lang)]
        assert leftovers == [], (lang, leftovers)
        assert json.loads(env["cfg"].read_text(encoding="utf-8"))["lang"] == lang
    close(app)


def test_new_messages_after_switch_are_japanese(env):
    app = start(env, "ko")
    switch(app, "ja")
    app.preview()  # PDF 도 목차도 없다
    log = app.log.get("1.0", "end-1c")
    assert i18n.STRINGS["ja"]["err_no_pdf"] in log and i18n.STRINGS["ja"]["err_toc_empty"] in log
    assert not HANGUL.search(log)
    close(app)


def test_input_survives_switch_to_ja(env):
    app = start(env, "ko")
    app.set_toc_text("第1章 序論, 3\n")
    app.offset_var.set("4")
    switch(app, "ja")
    assert app.toc_text.get("1.0", "end-1c") == "第1章 序論, 3\n"
    assert app.offset_var.get() == "4"
    close(app)


def test_ja_is_saved_and_restored_on_next_start(env):
    app = start(env, "ko", settings={"update_check": False, "other": 1})
    switch(app, "ja")
    close(app)
    saved = json.loads(env["cfg"].read_text(encoding="utf-8"))
    assert saved["lang"] == "ja" and saved["update_check"] is False and saved["other"] == 1
    # 다음 실행: 시작 순서와 같게 detect_lang 으로 고른다
    lang = i18n.detect_lang()
    assert lang == "ja"
    app = start(env, lang)
    assert app.root.title() == "PDF 目次しおり" and app.lang_var.get() == "日本語"
    close(app)


def test_ja_feedback_opens_english_page(env):
    app = start(env, "ja")
    app.open_feedback()
    assert env["opened"] == [uc.feedback_url(version.UPDATE_SLUG, version.APP_VERSION, "ja")]
    assert env["opened"][0].startswith("https://chaekgalpi.co.kr/en/tools/pdftoc?")
    close(app)


def test_ja_feedback_failure_message(env):
    env["result"] = False
    app = start(env, "ja")
    app.open_feedback()
    log = app.log.get("1.0", "end-1c")
    assert i18n.STRINGS["ja"]["feedback_failed"] in log and "/en/tools/pdftoc" in log
    close(app)


def test_ja_update_notice_opens_english_page(env):
    app = start(env, "ja")
    app._update_info = uc.UpdateInfo("9.9.9", version.APP_VERSION, "https://chaekgalpi.co.kr/tools/pdftoc",
                                     "https://chaekgalpi.co.kr/en/tools/pdftoc")
    app._update_open()
    assert env["opened"] == ["https://chaekgalpi.co.kr/en/tools/pdftoc"]
    close(app)


# ------------------------------------------------------------------ c. 레이아웃

def layout_problems(app) -> list[tuple]:
    """글자가 든 위젯이 요청한 폭·높이보다 좁게 그려졌거나(잘림), 창 밖으로 나갔거나, 같은 부모 안에서
    서로 겹치는지."""
    root = app.root
    rw, rh = root.winfo_width(), root.winfo_height()
    out = []
    leaves: dict[str, list] = {}
    for w in walk(root):
        if w.winfo_class() not in TEXT_CLASSES + ("TCombobox", "TSpinbox", "TEntry"):
            continue
        if not w.winfo_ismapped():
            if not str(w).startswith(str(app.frm_update)) or app._update_info is not None:
                out.append(("hidden", w.winfo_class(), w.cget("text") if w.winfo_class() in TEXT_CLASSES else ""))
            continue
        text = w.cget("text") if w.winfo_class() in TEXT_CLASSES else ""
        if w.winfo_width() < w.winfo_reqwidth() - 1 or w.winfo_height() < w.winfo_reqheight() - 1:
            out.append(("clipped", text, w.winfo_width(), w.winfo_reqwidth()))
        x, y = w.winfo_rootx() - root.winfo_rootx(), w.winfo_rooty() - root.winfo_rooty()
        if x < 0 or y < 0 or x + w.winfo_width() > rw or y + w.winfo_height() > rh:
            out.append(("outside", text, x, y, w.winfo_width(), w.winfo_height()))
        leaves.setdefault(w.winfo_parent(), []).append((x, y, w.winfo_width(), w.winfo_height(), text))
    for items in leaves.values():
        for i, a in enumerate(items):
            for b in items[i + 1:]:
                if a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]:
                    out.append(("overlap", a[4], b[4]))
    return out


@pytest.fixture
def pdf300(tmp_path):
    w = PdfWriter()
    for _ in range(300):
        w.add_blank_page(width=400, height=600)
    p = tmp_path / "スキャンした本_とても長いファイル名のサンプル.pdf"
    with p.open("wb") as fh:
        w.write(fh)
    return p


@pytest.mark.parametrize("lang", i18n.LANGS)
@pytest.mark.parametrize("geometry", ["640x660", "720x800"])  # 최소 크기, 기본 크기
def test_no_clipped_or_overlapping_text(env, lang, geometry):
    app = start(env, lang, geometry=geometry)
    assert (app.root.winfo_width(), app.root.winfo_height()) == tuple(map(int, geometry.split("x")))
    assert layout_problems(app) == [], (lang, geometry)
    close(app)


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_min_size_with_update_notice_and_loaded_pdf(env, lang, pdf300, monkeypatch):
    """알림 줄이 뜨고 PDF 를 넣은 상태(가장 붐비는 화면)에서도 최소 크기에서 잘리지 않는다."""
    import offset_detect
    monkeypatch.setattr(offset_detect, "detect_offset",
                        lambda *a, **k: offset_detect.OffsetResult(None, reason="no_numbers"))
    app = start(env, lang, geometry="640x660")
    app.set_pdf(pdf300)
    app._detect_thread.join(timeout=20)
    for _ in range(5):
        app.root.update()
        app._poll_detect()
    app._update_info = uc.UpdateInfo("10.10.10", version.APP_VERSION, "https://chaekgalpi.co.kr/tools/pdftoc")
    app._show_update_notice()
    app.root.update()
    assert "300" in app.pdf_label.cget("text")
    assert layout_problems(app) == [], lang
    close(app)


def test_window_minimum_is_still_640x660(env):
    app = start(env, "ja")
    assert app.root.minsize() == (640, 660)
    close(app)


# ------------------------------------------------------------------ d. 글꼴

def _missing_glyphs(family: str, text: str) -> str:
    """GDI 에 그 글꼴로 글리프 번호를 물어 없는 글자(0xFFFF)를 돌려준다."""
    gdi, user32 = ctypes.windll.gdi32, ctypes.windll.user32
    gdi.CreateFontW.restype = ctypes.c_void_p
    gdi.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi.SelectObject.restype = ctypes.c_void_p
    gdi.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi.GetGlyphIndicesW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int,
                                     ctypes.POINTER(ctypes.c_ushort), ctypes.c_uint]
    user32.GetDC.restype = ctypes.c_void_p
    user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    hdc = user32.GetDC(None)
    font = gdi.CreateFontW(-16, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, family)
    old = gdi.SelectObject(hdc, font)
    try:
        chars = "".join(sorted(set(text)))
        buf = (ctypes.c_ushort * len(chars))()
        gdi.GetGlyphIndicesW(hdc, chars, len(chars), buf, 1)  # GGI_MARK_NONEXISTING_GLYPHS
        return "".join(c for c, g in zip(chars, buf) if g == 0xFFFF)
    finally:
        gdi.SelectObject(hdc, old)
        gdi.DeleteObject(font)
        user32.ReleaseDC(None, hdc)


JA_TEXT = "".join(v for v in i18n.STRINGS["ja"].values()).replace("\n", "")


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 글꼴")
def test_ja_screen_uses_a_japanese_font_that_has_every_glyph(env):
    gui = env["gui"]
    app = start(env, "ja")
    family = gui.FONT_FAMILY
    assert family in gui.LANG_FONTS["ja"], family
    assert tk.font.Font(root=app.root, family=family, size=10).actual("family") == family  # 대체되지 않았다
    assert _missing_glyphs(family, JA_TEXT) == ""
    assert app.toc_text.cget("font").startswith("{" + family + "}") or family in str(app.toc_text.cget("font"))
    close(app)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows 글꼴")
def test_malgun_gothic_lacks_japanese_glyphs_so_ja_needs_its_own_font():
    """맑은 고딕을 그대로 쓰면 안 되는 이유(신자체·장음 기호가 없다). 글꼴이 바뀌면 이 시험이 알려 준다."""
    missing = _missing_glyphs("Malgun Gothic", JA_TEXT)
    assert "ー" in missing and "読" in missing


def test_other_languages_keep_malgun_gothic(env):
    gui = env["gui"]
    for lang in ("ko", "en", "zh", "ja", "ko"):
        app = start(env, lang)
        assert (gui.FONT_FAMILY == "Malgun Gothic") == (lang != "ja"), lang
        close(app)


def test_switching_to_ja_and_back_changes_the_font(env):
    gui = env["gui"]
    app = start(env, "ko")
    switch(app, "ja")
    ja_font = gui.FONT_FAMILY
    assert ja_font in gui.LANG_FONTS["ja"]
    assert ja_font in str(app.run_btn.cget("font"))
    switch(app, "ko")
    assert gui.FONT_FAMILY == "Malgun Gothic" and "Malgun Gothic" in str(app.run_btn.cget("font"))
    close(app)


def test_no_japanese_font_installed_falls_back_to_malgun(env, monkeypatch):
    gui = env["gui"]
    monkeypatch.setattr(gui.tkfont, "families", lambda *a, **k: ("Malgun Gothic", "Arial"))
    app = start(env, "ja")
    assert gui.FONT_FAMILY == "Malgun Gothic"
    assert app.root.title() == "PDF 目次しおり"
    close(app)


# ------------------------------------------------------------------ e. 오류·안내 문구

@pytest.fixture
def ja():
    i18n.set_lang("ja")
    yield
    i18n.set_lang("ko")


@pytest.fixture
def pdf12(tmp_path):
    w = PdfWriter()
    for _ in range(12):
        w.add_blank_page(width=400, height=600)
    p = tmp_path / "scan.pdf"
    with p.open("wb") as fh:
        w.write(fh)
    return p


def head(key: str) -> str:
    """문구의 첫 자리표시자 앞 부분(고정된 일본어)."""
    return i18n.STRINGS["ja"][key].split("{")[0]


def fixed(key: str) -> str:
    """자리표시자 사이의 고정된 글자 중 가장 긴 줄 조각."""
    parts = [p.strip() for chunk in re.split(r"\{[^}]*\}", i18n.STRINGS["ja"][key]) for p in chunk.split("\n")]
    return max(parts, key=len)


def assert_ja(msg: str, *keys: str):
    assert not HANGUL.search(msg), msg
    for k in keys:
        piece = fixed(k)
        assert piece and piece in msg, (k, piece, msg)


def _pdf_err(path):
    with pytest.raises(core.PdfError) as ei:
        core.open_pdf(path)
    return str(ei.value)


def test_pdf_errors_in_japanese(ja, tmp_path, pdf12):
    assert_ja(_pdf_err(tmp_path / "ない.pdf"), "pdf_missing")
    (tmp_path / "empty.pdf").write_bytes(b"")
    assert_ja(_pdf_err(tmp_path / "empty.pdf"), "pdf_empty")
    (tmp_path / "text.pdf").write_text("hello", encoding="utf-8")
    assert_ja(_pdf_err(tmp_path / "text.pdf"), "pdf_not_pdf")
    data = pdf12.read_bytes()
    (tmp_path / "cut.pdf").write_bytes(data[: len(data) // 3])
    cut = _pdf_err(tmp_path / "cut.pdf")
    assert not HANGUL.search(cut) and ("壊れ" in cut or "数えられません" in cut or "ページがありません" in cut)
    with (tmp_path / "zero.pdf").open("wb") as fh:
        PdfWriter().write(fh)
    assert_ja(_pdf_err(tmp_path / "zero.pdf"), "pdf_zero_pages")
    w = PdfWriter(clone_from=PdfReader(str(pdf12)))
    w.encrypt(user_password="secret")
    with (tmp_path / "locked.pdf").open("wb") as fh:
        w.write(fh)
    assert_ja(_pdf_err(tmp_path / "locked.pdf"), "pdf_encrypted")


def test_write_errors_in_japanese(ja, tmp_path, pdf12):
    entries = core.parse_toc("A, 1\n").entries
    with pytest.raises(core.PdfError) as ei:
        core.build_pdf(pdf12, tmp_path / "ないフォルダー" / "o.pdf", entries, 0, False)
    assert_ja(str(ei.value), "out_dir_missing")
    if sys.platform == "win32":
        import msvcrt
        out = tmp_path / "locked.pdf"
        out.write_bytes(b"x")
        with out.open("r+b") as fh:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                with pytest.raises(core.PdfError) as ei:
                    core.build_pdf(pdf12, out, entries, 0, False)
            finally:
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        assert_ja(str(ei.value), "out_locked")


def test_toc_file_errors_in_japanese(ja, tmp_path, pdf12):
    def err(path, enc=None):
        with pytest.raises(core.TocParseError) as ei:
            core.read_text(path, enc)
        return str(ei.value)

    (tmp_path / "empty.txt").write_bytes(b"")
    assert_ja(err(tmp_path / "empty.txt"), "empty_file")
    assert_ja(err(pdf12), "toc_is_pdf")
    (tmp_path / "img.txt").write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 4)
    assert_ja(err(tmp_path / "img.txt"), "toc_is_binary")
    (tmp_path / "u.txt").write_text("第1章, 1\n", encoding="utf-8")
    assert_ja(err(tmp_path / "u.txt", "no-such-encoding"), "decode_fail")
    assert_ja(err(tmp_path / "ない.txt"), "read_err")


@pytest.mark.parametrize("text,keys", [
    ("ページ番号なし\n", ("line_fmt", "no_page")),
    ("はじめに ...... iii\n", ("roman_reason",)),
    ("12\n", ("no_title",)),
    ("第1章, 0\n", ("page_lt_1",)),
    ("offset=八\n第1章, 1\n", ("offset_not_int",)),
    ("# だけ\n\n", ("no_entries",)),
])
def test_parse_errors_in_japanese(ja, text, keys):
    with pytest.raises(core.TocParseError) as ei:
        core.parse_toc(text)
    assert_ja(str(ei.value), *keys)


def test_parse_warnings_in_japanese(ja):
    p = core.parse_toc("offset=1\n第1章, 1-3\n# 第2章, 5\noffset=2\n")
    msgs = [str(w) for w in p.warnings]
    assert any(head("range_warn").strip() in m or "の範囲で書かれている" in m for m in msgs), msgs
    assert any("コメントとして読み飛ばしました" in m for m in msgs), msgs
    assert any("offset の行が" in m for m in msgs), msgs
    assert all(not HANGUL.search(m) for m in msgs)


def test_validate_messages_in_japanese(ja):
    with pytest.raises(core.TocParseError) as ei:
        core.validate(core.parse_toc("第1章, 50\n第2章, 60\n").entries, 0, 12)
    assert_ja(str(ei.value), "val_head")
    assert "最終ページを超えています" in str(ei.value) and "PDF は 12 ページまでです" in str(ei.value)
    with pytest.raises(core.TocParseError) as ei:
        core.validate(core.parse_toc("第1章, 1\n").entries, -5, 12)
    assert "1 ページ目より前です" in str(ei.value)
    warnings = core.validate(core.parse_toc("第1章, 5\n第2章, 3\n").entries, 0, 12)
    assert "書き間違いがないか" in str(warnings[0])


def test_gui_error_paths_in_japanese(env, tmp_path, pdf12):
    app = start(env, "ja")
    # 잘못된 PDF
    bad = tmp_path / "bad.pdf"
    bad.write_text("not a pdf", encoding="utf-8")
    app.set_pdf(bad)
    log = app.log.get("1.0", "end-1c")
    assert "PDF を開けません" in log and "PDF ファイルではありません" in log
    # 암호 PDF
    w = PdfWriter(clone_from=PdfReader(str(pdf12)))
    w.encrypt(user_password="secret")
    locked = tmp_path / "locked.pdf"
    with locked.open("wb") as fh:
        w.write(fh)
    app.set_pdf(locked)
    assert "パスワードが必要" in app.log.get("1.0", "end-1c")
    # offset 오류
    app.set_toc_text("第1章, 1\n")
    app.offset_var.set("八")
    app.preview()
    assert "「八」は整数ではありません" in app.log.get("1.0", "end-1c")
    # 폴더·없는 파일을 끌어다 놓기
    class Ev:
        data = "{%s} {%s}" % (tmp_path, tmp_path / "ない.txt")
    app._on_drop(Ev())
    log = app.log.get("1.0", "end-1c")
    assert "はフォルダーです" in log and "が見つかりません" in log
    assert not HANGUL.search(app.log.get("1.0", "end-1c"))
    close(app)


def test_gui_same_output_and_write_failure_in_japanese(env, tmp_path, pdf12, monkeypatch):
    monkeypatch.setattr(core, "build_pdf", lambda *a, **k: (_ for _ in ()).throw(
        core.PdfError(i18n.tr("out_write_fail", path="x.pdf", err="disk full"))))
    app = start(env, "ja")
    app.pdf_path, app.num_pages = pdf12, 12
    app.set_toc_text("第1章, 1\n")
    app.offset_var.set("0")
    app.out_var.set(str(pdf12))
    app.build()
    assert "出力ファイルが元のファイルと同じです" in app.log.get("1.0", "end-1c")
    app.out_var.set(str(tmp_path / "out.pdf"))
    app.build()
    log = app.log.get("1.0", "end-1c")
    assert "PDF を作成できませんでした" in log and "書き込めませんでした" in log
    close(app)


def test_detect_failure_messages_in_japanese(env):
    import offset_detect
    app = start(env, "ja")
    app.pdf_path, app.num_pages = Path("x.pdf"), 10
    for reason, key in [("no_numbers", "detect_fail_no_numbers"), ("ocr_unavailable", "detect_fail_ocr_unavailable")]:
        res = type("R", (), {"offset": None, "reason": reason, "votes": 0, "pages_with_numbers": 0})()
        app._detect_gen += 1
        app._detect_done(app._detect_gen, True, res, None)
        log = app.log.get("1.0", "end-1c")
        assert i18n.STRINGS["ja"][key] in log and i18n.STRINGS["ja"]["detect_fail_hint"] in log
    app._detect_gen += 1
    app._detect_done(app._detect_gen, True, None, "RuntimeError: x")
    assert "自動検出中にエラーが起きました" in app.log.get("1.0", "end-1c")
    assert offset_detect  # 모듈이 그대로 있는지
    close(app)


def test_cli_ja_messages(tmp_path, pdf12, capsys):
    toc = tmp_path / "t.txt"
    toc.write_text("ページ番号なし\n", encoding="utf-8")
    assert core.main(["--lang", "ja", str(pdf12), str(toc)]) == 1
    err = capsys.readouterr().err
    assert "エラー: " in err and "1 行目" in err and not HANGUL.search(err)
    with pytest.raises(SystemExit):
        core.main(["--lang=ja", "--help"])
    out = capsys.readouterr().out
    assert "目次ファイルの書き方" in out and "表示言語: ko, en, zh, ja" in out


# ------------------------------------------------------------------ f. 회귀: 출력은 언어와 무관

def outline(path: Path):
    r = PdfReader(str(path))
    out = []

    def go(items, level):
        for it in items:
            if isinstance(it, list):
                go(it, level + 1)
            else:
                out.append((level, it.title, r.get_destination_page_number(it) + 1))

    go(r.outline, 0)
    return out, [p.mediabox for p in r.pages], str(r.trailer["/Root"].get("/PageMode"))


def test_output_pdf_is_the_same_in_every_language(tmp_path, pdf12):
    toc = "はじめに, 1\n第1章 序論, 2\n    1.1 背景, 3\n한글 제목, 4\nEnglish, 5\n第2章 绪论, 6\n"
    results = {}
    for lang in i18n.LANGS:
        i18n.set_lang(lang)
        out = tmp_path / f"out_{lang}.pdf"
        core.build_pdf(pdf12, out, core.parse_toc(toc).entries, 2, keep_existing=False)
        results[lang] = outline(out)
    assert all(r == results["ko"] for r in results.values())
    assert results["ja"][0][0] == (0, "はじめに", 3)


def test_cli_output_is_the_same_in_every_language(tmp_path, pdf12, capsys):
    toc = tmp_path / "t.txt"
    toc.write_text("offset=1\n第1章, 1\n第2章, 5\n", encoding="utf-8")
    results = {}
    for lang in i18n.LANGS:
        out = tmp_path / f"cli_{lang}.pdf"
        assert core.main(["--lang", lang, str(pdf12), str(toc), "-o", str(out)]) == 0
        results[lang] = outline(out)
    capsys.readouterr()
    assert all(r == results["ko"] for r in results.values())


def test_update_page_for_ja_is_english_page():
    info = uc.UpdateInfo("2.0.0", "1.0.0", "https://chaekgalpi.co.kr/tools/pdftoc",
                         "https://chaekgalpi.co.kr/en/tools/pdftoc")
    assert info.page_for("ja") == info.url_en
    assert info.page_for("ko") == info.url
    assert uc.UpdateInfo("2.0.0", "1.0.0", "https://chaekgalpi.co.kr/tools/pdftoc").page_for("ja") == \
        "https://chaekgalpi.co.kr/tools/pdftoc"  # 영어 판이 없으면 기본 페이지


def test_feedback_url_for_ja():
    assert uc.feedback_url("pdftoc", "1.1.3", "ja") == \
        "https://chaekgalpi.co.kr/en/tools/pdftoc?utm_source=app&utm_medium=feedback&v=1.1.3#feedback"


def test_version_was_bumped_once():
    assert version.APP_VERSION == "1.1.4"


# ------------------------------------------------------------------ g. 알 수 없는 언어·깨진 설정

@pytest.mark.parametrize("bad", ["fr", "", "JA", "ja-JP", "jp", None, 5, True, ["ja"], {"ja": 1}])
def test_bad_saved_lang_is_ignored(env, bad):
    env["cfg"].write_text(json.dumps({"lang": bad}), encoding="utf-8")
    assert i18n.load_saved_lang() is None


@pytest.mark.parametrize("raw", ["{broken", "[1, 2]", '"ja"', "null", "﻿{\"lang\": \"ja\"}", "\x00\x01"])
def test_broken_settings_file_does_not_crash(env, raw):
    env["cfg"].write_text(raw, encoding="utf-8")
    assert i18n.load_saved_lang() in (None, "ja")
    lang = i18n.detect_lang()
    assert lang in i18n.LANGS
    app = start(env, lang)
    assert app.lang_var.get() in i18n.LANG_NAMES.values()
    close(app)


@pytest.mark.parametrize("code", ["fr", "", "xx", "JA ", None])
def test_set_lang_unknown_falls_back_to_english(code):
    i18n.set_lang(code)
    assert i18n.get_lang() == "en"
    assert i18n.tr("btn_build") == "Create PDF"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows UI 언어")
@pytest.mark.parametrize("langid,expected", [(0x0411, "ja"), (0x0412, "ko"), (0x0804, "zh"), (0x0404, "zh"),
                                             (0x0409, "en"), (0x040C, "en"), (0x0407, "en")])
def test_windows_ui_language_picks_first_lang(env, monkeypatch, langid, expected):
    monkeypatch.setattr(ctypes.windll.kernel32, "GetUserDefaultUILanguage", lambda: langid)
    assert i18n.detect_lang() == expected


@pytest.mark.skipif(sys.platform != "win32", reason="Windows UI 언어")
def test_saved_lang_beats_os_and_env_beats_saved(env, monkeypatch):
    monkeypatch.setattr(ctypes.windll.kernel32, "GetUserDefaultUILanguage", lambda: 0x0412)
    env["cfg"].write_text(json.dumps({"lang": "ja"}), encoding="utf-8")
    assert i18n.detect_lang() == "ja"
    monkeypatch.setenv("PDF_TOC_LANG", "zh")
    assert i18n.detect_lang() == "zh"
    monkeypatch.setenv("PDF_TOC_LANG", "xx")  # 모르는 값이면 저장된 값
    assert i18n.detect_lang() == "ja"
    monkeypatch.setenv("PDF_TOC_LANG", "ja_JP")
    assert i18n.detect_lang() == "ja"


def test_locale_fallback_picks_japanese(env, monkeypatch):
    """Windows API 를 못 쓰는 환경에서는 로케일로 고른다."""
    import locale
    monkeypatch.setattr(ctypes, "windll", None, raising=False)
    monkeypatch.setattr(locale, "getlocale", lambda *a: ("Japanese_Japan", "932"))
    assert i18n.detect_lang() == "ja"
    monkeypatch.setattr(locale, "getlocale", lambda *a: ("fr_FR", "UTF-8"))
    assert i18n.detect_lang() == "en"


def test_cli_unknown_lang_falls_back_to_english(tmp_path, pdf12, capsys):
    toc = tmp_path / "t.txt"
    toc.write_text("bad line\n", encoding="utf-8")
    assert core.main(["--lang", "xx", str(pdf12), str(toc)]) == 1
    assert "Error: " in capsys.readouterr().err

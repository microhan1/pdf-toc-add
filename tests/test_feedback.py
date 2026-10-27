"""「의견 보내기」: 툴 페이지의 의견 칸 주소를 만들고 브라우저로 열기만 한다.

실제 브라우저는 열지 않는다(webbrowser.open 은 기록만 하는 가짜). 실제 네트워크도 쓰지 않는다:
conftest 의 운영 서버 차단에 더해, 이 파일의 모든 시험에서 소켓 연결·주소 조회를 기록하고 막은 뒤
0건인지 단언한다. 설정 파일은 임시 폴더의 config.json 만 쓴다.
"""

from __future__ import annotations

import json
import socket
import sys
import tkinter as tk
import urllib.parse
import webbrowser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import i18n  # noqa: E402
import pdf_toc_add as core  # noqa: E402
import update_check as uc  # noqa: E402
import version  # noqa: E402

KO = "https://chaekgalpi.co.kr/tools/pdftoc?utm_source=app&utm_medium=feedback&v=0.2.1#feedback"
EN = "https://chaekgalpi.co.kr/en/tools/pdftoc?utm_source=app&utm_medium=feedback&v=0.2.1#feedback"


def url(lang, v="0.2.1"):
    return uc.feedback_url("pdftoc", v, lang)


def query_of(u: str) -> dict[str, list[str]]:
    return urllib.parse.parse_qs(urllib.parse.urlsplit(u).query, keep_blank_values=True)


# ------------------------------------------------------------------ g. 네트워크 0건

@pytest.fixture(autouse=True)
def no_sockets(monkeypatch, no_real_server):
    """소켓 연결·주소 조회를 기록하고 막는다. 끝날 때 0건이어야 한다(conftest 의 urlopen 차단 기록도)."""
    tried: list[str] = []

    def connect(self, addr, *a, **kw):
        tried.append(f"connect {addr}")
        raise OSError("시험에서는 네트워크에 접속하지 않는다")

    def create_connection(addr, *a, **kw):
        tried.append(f"create_connection {addr}")
        raise OSError("시험에서는 네트워크에 접속하지 않는다")

    def getaddrinfo(host, *a, **kw):
        tried.append(f"getaddrinfo {host}")
        raise socket.gaierror("시험에서는 주소를 조회하지 않는다")

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect)
    monkeypatch.setattr(socket, "create_connection", create_connection)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
    yield tried
    assert tried == [], tried
    assert no_real_server == [], no_real_server


# ------------------------------------------------------------------ a. 주소

@pytest.mark.parametrize("lang,expected", [
    ("ko", KO), ("en", EN), ("ja", EN), ("zh-CN", EN),
    ("zh", EN),                                   # 이 프로그램 안의 중국어 코드
])
def test_exact_address_per_language(lang, expected):
    assert url(lang) == expected


@pytest.mark.parametrize("lang", [None, "", "fr", "de-DE", "xx", "  ", "kor"])
def test_unknown_language_goes_to_english_page(lang):
    """시리즈 공통 규칙(10-27): ko 만 한국어 판, 나머지는 영어 판. 빈 값은 기본 화면 언어(영어)."""
    assert url(lang) == EN


@pytest.mark.parametrize("lang,expected", [
    ("EN", EN), ("En", EN), ("zh-cn", EN), ("ZH-CN", EN), ("zh_CN", EN), ("JA", EN), ("ja-JP", EN),
    ("en-US", EN), ("KO", KO), ("ko-KR", KO), (" en ", EN),
])
def test_language_code_case_and_region(lang, expected):
    assert url(lang) == expected


@pytest.mark.parametrize("lang", ["ko", "en", "ja", "zh-CN", "zh", None, "fr"])
@pytest.mark.parametrize("v", ["0.2.1", "", None, version.APP_VERSION])
def test_shape_of_every_address(lang, v):
    u = url(lang, v)
    assert u.startswith("https://chaekgalpi.co.kr/")
    assert u.endswith("#feedback")
    assert "utm_source=app" in u and "utm_medium=feedback" in u
    parts = urllib.parse.urlsplit(u)
    assert (parts.scheme, parts.netloc, parts.fragment) == ("https", "chaekgalpi.co.kr", "feedback")
    assert parts.path in ("/tools/pdftoc", "/en/tools/pdftoc")
    q = query_of(u)
    assert q["utm_source"] == ["app"] and q["utm_medium"] == ["feedback"]


def test_the_real_app_address_uses_slug_and_version():
    u = uc.feedback_url(version.UPDATE_SLUG, version.APP_VERSION, "ko")
    assert u == ("https://chaekgalpi.co.kr/tools/pdftoc?utm_source=app&utm_medium=feedback&v="
                 + urllib.parse.quote(version.APP_VERSION, safe="") + "#feedback")


def test_address_is_built_from_constants_only(tmp_path, monkeypatch):
    """설정 파일에 다른 주소가 들어 있어도 주소는 코드 상수로만 만든다."""
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"feedback_url": "https://evil.example/", "url": "https://evil.example/"}),
                   encoding="utf-8")
    monkeypatch.setattr(i18n, "config_path", lambda: cfg)
    assert url("ko") == KO and url("en") == EN


# ------------------------------------------------------------------ b. 버전

@pytest.mark.parametrize("v,in_url", [
    ("0.2.1", "v=0.2.1"),
    ("v0.2.1", "v=v0.2.1"),
    ("1.0.0-beta+3", "v=1.0.0-beta%2B3"),          # + 가 공백으로 읽히지 않게
])
def test_normal_versions(v, in_url):
    u = url("ko", v)
    assert in_url in u and query_of(u)["v"] == [v]


@pytest.mark.parametrize("v", ["", None, "   ", "\t\n"])
def test_empty_version_drops_v(v):
    u = url("ko", v)
    assert "v=" not in u.replace("utm_", "")
    assert "v" not in query_of(u)
    assert u == "https://chaekgalpi.co.kr/tools/pdftoc?utm_source=app&utm_medium=feedback#feedback"


@pytest.mark.parametrize("v", [
    "1.0 beta", "1&utm_source=evil", "1#x", "1?a=b", "버전 1.2", "1/2\\3", "a=b&c=d#e f",
    "%41%", "1;2,3", "1+1=2", "版本 2.0", "\u200b1.0", "x" * 200,
])
def test_odd_versions_are_encoded_and_read_back_intact(v):
    for lang in ("ko", "en"):
        u = url(lang, v)
        parts = urllib.parse.urlsplit(u)
        assert parts.fragment == "feedback" and parts.netloc == "chaekgalpi.co.kr"
        q = query_of(u)
        assert set(q) == {"utm_source", "utm_medium", "v"}           # 다른 파라미터가 끼어들지 않는다
        assert q["v"] == [v.strip()] and q["utm_source"] == ["app"]
        assert u.count("#") == 1 and " " not in u
        assert all(ord(c) < 128 for c in u)                          # 한글도 %xx 로


def test_surrounding_whitespace_is_trimmed():
    assert query_of(url("ko", "  1.2.3 \n"))["v"] == ["1.2.3"]


# ------------------------------------------------------------------ 창 시험 공통

@pytest.fixture
def env(tmp_path, monkeypatch):
    """임시 설정 파일과 기록만 하는 브라우저. browser['result'] 로 open 의 결과(또는 던질 예외)를 정한다."""
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(i18n, "config_path", lambda: cfg)
    import pdf_toc_gui as gui

    state = {"opened": [], "result": True, "cfg": cfg, "gui": gui}

    def fake_open(u, *a, **kw):
        state["opened"].append(u)
        r = state["result"]
        if isinstance(r, BaseException):
            raise r
        return r

    monkeypatch.setattr(webbrowser, "open", fake_open)
    yield state
    import gc

    gc.collect()


def start(env, lang="en", settings=None):
    i18n.set_lang(lang)
    s = {"lang": lang} if settings is None else settings
    env["cfg"].write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    gui = env["gui"]
    root = gui.TkinterDnD.Tk() if gui._DND else tk.Tk()
    app = gui.App(root)
    root.update()
    return app


def close(app):
    """예약된 새 버전 확인(1.5초 뒤)을 취소하고 닫는다. 안 그러면 없어진 창에서 after 가 울린다."""
    for job in app.root.tk.splitlist(app.root.tk.call("after", "info")):
        app.root.after_cancel(job)
    app._on_close()
    try:
        app.root.update()
    except Exception:
        pass


def switch(app, lang):
    app.lang_var.set(i18n.LANG_NAMES[lang])
    app._on_lang_change()
    app.root.update()


def log_text(app) -> str:
    return app.log.get("1.0", "end-1c")


def expected(lang):
    return uc.feedback_url(version.UPDATE_SLUG, version.APP_VERSION, lang)


# ------------------------------------------------------------------ c. 메뉴 콜백

@pytest.mark.parametrize("lang", i18n.LANGS)
def test_click_opens_the_page_exactly_once(env, lang):
    app = start(env, lang)
    app.open_feedback()
    assert env["opened"] == [expected(lang)]
    assert ("/en/" in env["opened"][0]) == (lang != "ko")
    assert "✖" not in log_text(app)                     # 성공하면 결과 칸에 아무것도 쓰지 않는다
    close(app)


def test_clicking_the_link_itself_calls_the_callback(env):
    """링크(라벨)의 <Button-1> 바인딩이 콜백으로 이어지는지. Tk 안의 이벤트이며 OS 마우스는 쓰지 않는다."""
    app = start(env, "ko")
    app.root.update()
    app.feedback_link.event_generate("<Button-1>", x=2, y=2)
    app.root.update()
    assert env["opened"] == [expected("ko")]
    close(app)


def test_language_switch_changes_the_next_address(env):
    app = start(env, "ko")
    app.open_feedback()
    switch(app, "en")
    app.open_feedback()
    switch(app, "zh")
    app.open_feedback()
    switch(app, "ko")
    app.open_feedback()
    assert env["opened"] == [expected("ko"), expected("en"), expected("zh"), expected("ko")]
    close(app)


def test_two_clicks_open_twice(env):
    app = start(env)
    app.open_feedback()
    app.open_feedback()
    assert env["opened"] == [expected("en")] * 2
    close(app)


# ------------------------------------------------------------------ d. 실패

def _fill(app):
    app.toc_text.insert("1.0", "1장 제목, 12\n2장 제목, 30")
    app.offset_var.set("8")
    app.out_var.set(r"C:\out\book_toc.pdf")
    app.write_log("앞서 남은 줄", "muted")


def _state(app):
    return (app.toc_text.get("1.0", "end-1c"), app.offset_var.get(), app.out_var.get(),
            app.var_update_check.get(), app.pdf_path, i18n.get_lang())


@pytest.mark.parametrize("failure", [
    False,
    webbrowser.Error("could not locate runnable browser"),
    OSError(2, "No such file or directory"),
    PermissionError("access denied"),
    RuntimeError("anything else"),
], ids=["returns-False", "webbrowser.Error", "OSError", "PermissionError", "RuntimeError"])
@pytest.mark.parametrize("lang", i18n.LANGS)
def test_failure_shows_copyable_address_and_keeps_state(env, failure, lang):
    app = start(env, lang)
    _fill(app)
    before, settings_before = _state(app), env["cfg"].read_text(encoding="utf-8")
    env["result"] = failure
    app.open_feedback()                                  # 예외가 밖으로 나오지 않는다
    app.root.update()
    text = log_text(app)
    assert "앞서 남은 줄" in text                         # 결과 칸을 지우지 않는다
    assert i18n.STRINGS[lang]["feedback_failed"] in text
    assert expected(lang) in text.splitlines()            # 주소가 한 줄 통째로 있어 복사할 수 있다
    assert _state(app) == before
    assert env["cfg"].read_text(encoding="utf-8") == settings_before
    assert app.root.winfo_exists() and len(env["opened"]) == 1
    env["result"] = True                                 # 다음 클릭은 다시 된다
    app.open_feedback()
    assert len(env["opened"]) == 2 and log_text(app).count(expected(lang)) == 1
    close(app)


def test_none_from_a_browser_is_not_treated_as_failure(env):
    """webbrowser.open 은 bool 을 돌려준다. False 만 실패로 본다."""
    app = start(env)
    env["result"] = None
    app.open_feedback()
    assert i18n.STRINGS["en"]["feedback_failed"] not in log_text(app)
    close(app)


def test_failed_message_survives_language_switch(env):
    app = start(env, "en")
    env["result"] = False
    app.open_feedback()
    switch(app, "ko")
    assert expected("en") in log_text(app)               # 남긴 주소는 다시 그려도 남는다
    close(app)


# ------------------------------------------------------------------ e. i18n

def test_new_keys_exist_in_every_language_and_are_not_empty():
    for lang in i18n.LANGS:
        for key in ("btn_feedback", "feedback_failed"):
            assert i18n.STRINGS[lang].get(key, "").strip(), (lang, key)


def test_wording():
    assert i18n.STRINGS["ko"]["btn_feedback"] == "의견 보내기"
    assert i18n.STRINGS["en"]["btn_feedback"] == "Send feedback"
    assert i18n.STRINGS["zh"]["btn_feedback"] == "发送反馈"


def test_link_is_next_to_the_update_checkbox(env):
    app = start(env, "ko")
    siblings = app.feedback_link.master.winfo_children()
    kinds = [w.winfo_class() for w in siblings]
    assert kinds == ["TCheckbutton", "TLabel"]
    assert siblings[0].cget("text") == "새 버전 확인"
    assert app.feedback_link.winfo_ismapped()
    close(app)


def test_link_text_follows_the_language(env):
    app = start(env, "ko")
    assert app.feedback_link.cget("text") == "의견 보내기"
    for lang in ("en", "zh", "ko", "en"):
        switch(app, lang)
        assert app.feedback_link.cget("text") == i18n.STRINGS[lang]["btn_feedback"]
        assert app.feedback_link.winfo_exists()
    close(app)


# ------------------------------------------------------------------ f. 회귀

def test_cli_help_is_unchanged(capsys):
    with pytest.raises(SystemExit) as ei:
        core.main(["--lang", "en", "--help"])
    assert ei.value.code == 0
    out = capsys.readouterr().out
    assert i18n.STRINGS["en"]["cli_desc"] in out and "--auto-offset" in out
    assert "feedback" not in out.lower()


def test_cli_version_behaves_as_before(capsys):
    """이 도구에는 --version 이 없다(이번에 만들지 않았다). 예전처럼 인수 오류로 끝난다."""
    with pytest.raises(SystemExit) as ei:
        core.main(["--version"])
    assert ei.value.code == 2


def test_feedback_does_not_touch_the_update_check(env):
    """의견 보내기는 새 버전 확인 설정·날짜·알림을 건드리지 않는다."""
    s = {"lang": "en", "update_check": False, "update_check_last": "2026-10-01", "update_check_skipped": "9.9"}
    app = start(env, "en", s)
    app.open_feedback()
    env["result"] = False
    app.open_feedback()
    app.root.update()
    assert json.loads(env["cfg"].read_text(encoding="utf-8")) == s
    assert app.var_update_check.get() is False and not app.frm_update.winfo_manager()
    close(app)


def test_update_notice_still_opens_its_own_page(env):
    app = start(env, "en")
    app._update_info = uc.UpdateInfo("9.0.0", version.APP_VERSION, "https://chaekgalpi.co.kr/tools/pdftoc")
    app._show_update_notice()
    app.open_feedback()
    app._update_open()
    assert env["opened"] == [expected("en"), "https://chaekgalpi.co.kr/tools/pdftoc"]
    close(app)

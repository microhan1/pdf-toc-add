"""실제 창에서의 새 버전 알림: 가짜 서버 답과 임시 폴더의 config.json 으로만 돌린다.
실제 책갈피 서버나 사용자의 설정 파일에는 손대지 않는다."""

from __future__ import annotations

import functools
import json
import sys
import time
import tkinter as tk
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import i18n  # noqa: E402
import update_check as uc  # noqa: E402
import version  # noqa: E402

OK = {"latest": "1.2.0", "updateAvailable": True,
      "url": "https://chaekgalpi.co.kr/tools/pdftoc?utm_source=app&utm_medium=update"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    """임시 설정 파일, 가짜 서버, 기록만 하는 브라우저."""
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(i18n, "config_path", lambda: cfg)
    i18n.set_lang("en")
    import pdf_toc_gui as gui

    state = {"answer": OK, "calls": 0, "opened": [], "cfg": cfg, "gui": gui}

    def fetcher(slug, version_):
        state["calls"] += 1
        return state["answer"]

    monkeypatch.setattr(gui.update_check, "check_async", functools.partial(uc.check_async, fetcher=fetcher))
    import webbrowser

    monkeypatch.setattr(webbrowser, "open", lambda url: state["opened"].append(url))
    yield state
    # 닫힌 App 은 참조 고리다. 메인 스레드인 여기서 거둔다: 순환 GC 에 맡기면 다음 테스트의
    # 백그라운드 스레드에서 풀릴 수 있고, Tk 변수가 메인 스레드 밖에서 풀리면 Tcl 이 망가진다.
    import gc

    gc.collect()


def pump(app, cond, timeout=8.0):
    """진짜 mainloop 를 돌린다(확인은 root.after 로 돌아온다). cond 가 참이 되면 멈춘다."""
    end = time.time() + timeout
    box = {"ok": False}

    def poll():
        if cond():
            box["ok"] = True
            app.root.quit()
        elif time.time() > end:
            app.root.quit()
        else:
            app.root.after(20, poll)

    app.root.after(20, poll)
    app.root.mainloop()
    return box["ok"] or cond()


def start(env, settings=None):
    if settings is not None:
        env["cfg"].write_text(json.dumps(settings, ensure_ascii=False), encoding="utf-8")
    gui = env["gui"]
    root = gui.TkinterDnD.Tk() if gui._DND else tk.Tk()
    return gui.App(root)


def close(app):
    """창을 없애기 전에 백그라운드 스레드(새 버전 확인, offset 감지)를 끝내 준다."""
    import threading

    def idle():
        return not any(t.is_alive() for t in threading.enumerate() if t is not threading.main_thread())

    pump(app, idle, timeout=10)
    app._on_close()
    try:
        app.root.update()
    except Exception:
        pass


def saved(env):
    return json.loads(env["cfg"].read_text(encoding="utf-8")) if env["cfg"].exists() else {}


def shown(app):
    return bool(app.frm_update.winfo_manager())


def test_newer_version_shows_one_line_and_records_the_day(env):
    app = start(env, {"lang": "en", "update_check": True})
    assert pump(app, lambda: shown(app))
    assert app.lbl_update.cget("text") == f"Version 1.2.0 is available (current {version.APP_VERSION})"
    s = saved(env)
    assert s["update_check_last"] == uc.today() and env["calls"] == 1
    assert s["lang"] == "en"  # 다른 설정은 그대로
    close(app)


def test_the_notice_is_not_a_dialog(env):
    """대화상자를 띄우지 않는다: 알림이 떠도 창은 계속 쓸 수 있다."""
    app = start(env)
    assert pump(app, lambda: shown(app))
    app.toc_text.insert("1.0", "1장, 12")  # 알림이 뜬 뒤에도 입력이 된다
    assert app.toc_text.get("1.0", "end-1c") == "1장, 12"
    assert app.frm_update.winfo_toplevel() is app.root  # 별도 창이 아니다
    close(app)


def test_later_hides_and_remembers_that_version(env):
    app = start(env)
    assert pump(app, lambda: shown(app))
    app._update_later()
    app.root.update()
    assert not shown(app) and saved(env)["update_check_skipped"] == "1.2.0" and env["opened"] == []
    close(app)


def test_update_opens_the_tools_page_only(env):
    app = start(env)
    assert pump(app, lambda: shown(app))
    app._update_open()
    app.root.update()
    assert env["opened"] == [OK["url"]] and not shown(app)
    close(app)


EN_URL = "https://chaekgalpi.co.kr/en/tools/pdftoc?utm_source=app&utm_medium=update"


def test_an_english_screen_opens_the_english_page(env):
    env["answer"] = dict(OK, urlEn=EN_URL)
    app = start(env, {"lang": "en"})
    assert pump(app, lambda: shown(app))
    app._update_open()
    app.root.update()
    assert env["opened"] == [EN_URL]
    close(app)


def test_switching_to_korean_opens_the_korean_page(env):
    env["answer"] = dict(OK, urlEn=EN_URL)
    app = start(env, {"lang": "en"})
    assert pump(app, lambda: shown(app))
    app.lang_var.set(i18n.LANG_NAMES["ko"])
    app._on_lang_change()
    app.root.update()
    app._update_open()
    app.root.update()
    assert env["opened"] == [OK["url"]]
    close(app)


def test_another_domain_is_never_opened(env):
    """서버가 다른 주소를 돌려주면 알림 자체가 뜨지 않고, 억지로 넣어도 열지 않는다."""
    env["answer"] = dict(OK, url="https://evil.example/pdftoc")
    app = start(env)
    pump(app, lambda: env["calls"] == 1)
    pump(app, lambda: False, timeout=0.3)
    assert not shown(app)
    app._update_info = uc.UpdateInfo("1.2.0", version.APP_VERSION, "https://evil.example/pdftoc")
    app._update_open()
    assert env["opened"] == []
    close(app)


def test_offline_shows_nothing_and_keeps_the_day_open(env):
    env["answer"] = None
    app = start(env)
    pump(app, lambda: env["calls"] == 1)
    pump(app, lambda: False, timeout=0.3)
    assert not shown(app) and "update_check_last" not in saved(env)
    close(app)


def test_switched_off_never_asks(env):
    app = start(env, {"update_check": False})
    pump(app, lambda: False, timeout=2.2)
    assert env["calls"] == 0 and not shown(app) and not app.var_update_check.get()
    close(app)


def test_already_checked_today_does_not_ask_again(env):
    app = start(env, {"update_check_last": uc.today()})
    pump(app, lambda: False, timeout=2.2)
    assert env["calls"] == 0 and not shown(app)
    close(app)


def test_unticking_the_box_hides_the_notice_and_saves(env):
    app = start(env)
    assert pump(app, lambda: shown(app))
    app.var_update_check.set(False)
    app._on_update_toggle()
    app.root.update()
    assert not shown(app) and saved(env)["update_check"] is False
    close(app)


def test_language_switch_rewords_the_notice(env):
    app = start(env)
    assert pump(app, lambda: shown(app))
    app.lang_var.set(i18n.LANG_NAMES["ko"])
    app._on_lang_change()
    app.root.update()
    assert shown(app)  # 다시 그려도 알림은 남아 있다
    assert app.lbl_update.cget("text") == f"새 버전이 나왔습니다: 1.2.0 (현재 {version.APP_VERSION})"
    assert app.btn_update_open.cget("text") == "업데이트" and app.btn_update_later.cget("text") == "다음에"
    close(app)


def test_the_checkbox_is_in_the_settings_section(env):
    app = start(env, {"update_check": True})
    found = []

    def walk(w):
        for c in w.winfo_children():
            if c.winfo_class() == "TCheckbutton":
                found.append(c.cget("text"))
            walk(c)

    walk(app.root)
    assert i18n.tr("opt_update_check") in found, found
    assert app.var_update_check.get() is True
    close(app)


def test_notice_leaves_the_rest_of_the_window_in_place(env):
    """알림 줄은 창 맨 아래에 붙는다: 머리말과 3단계 버튼은 크기가 그대로이고 모두 창 안에 있다.
    늘어날 수 있는 입력칸·결과칸만 그만큼 양보한다."""
    app = start(env)
    app.root.geometry("720x800")
    pump(app, lambda: False, timeout=0.5)

    def sizes():
        app.root.update_idletasks()
        ws = {"lang": app.lang_cb, "pdf": app.pdf_label, "run": app.run_btn,
              "preview": app.preview_btn, "detect": app.detect_btn}
        return {k: (w.winfo_width(), w.winfo_height()) for k, w in ws.items()}

    def flexible():
        app.root.update_idletasks()
        return (app.toc_text.winfo_height(), app.log.winfo_height())

    before, flex_before = sizes(), flexible()
    assert pump(app, lambda: shown(app))
    pump(app, lambda: False, timeout=0.3)
    after, flex_after = sizes(), flexible()

    assert before == after, (before, after)
    assert all(a <= b for a, b in zip(flex_after, flex_before))      # 늘어나는 칸만 양보한다
    assert all(a > 60 for a in flex_after), flex_after               # 쓸 수 없을 만큼 쪼그라들지 않는다
    r = app.root
    for name, w in (("run", app.run_btn), ("update", app.btn_update_open), ("later", app.btn_update_later)):
        assert w.winfo_rooty() + w.winfo_height() <= r.winfo_rooty() + r.winfo_height() + 1, name
    close(app)


def test_the_window_keeps_working_after_the_notice(env):
    """알림이 뜬 뒤에도 미리보기 같은 평소 기능이 그대로 돈다(알림이 입력을 막지 않는다)."""
    app = start(env)
    assert pump(app, lambda: shown(app))
    app.toc_text.insert("1.0", "1장 제목, 12\n2장 제목, 30")
    app.preview()
    app.root.update()
    assert shown(app)
    close(app)


CLOSE_WHILE_ASKING = r"""
import functools, json, os, sys, tempfile, time, urllib.error, urllib.request
sys.path.insert(0, {root!r})
def _blocked(req, *a, **kw):      # 자식 프로세스에는 conftest 가 없으므로 여기서 막는다
    raise urllib.error.URLError("시험에서는 운영 서버에 접속하지 않는다")
urllib.request.urlopen = _blocked
import i18n
_cfg = os.path.join(tempfile.mkdtemp(), "config.json")
i18n.config_path = lambda: __import__("pathlib").Path(_cfg)
i18n.set_lang("en")
import tkinter as tk
import pdf_toc_gui as gui, update_check as uc
uc.fetch.__kwdefaults__["opener"] = _blocked
uc.check_async.__kwdefaults__["fetcher"] = lambda slug, version: None
def slow(slug, version):
    time.sleep(1.5)          # 답을 기다리는 중에 창이 닫힌다
    return {{"latest": "1.2.0", "updateAvailable": True, "url": "https://chaekgalpi.co.kr/tools/pdftoc"}}
gui.update_check.check_async = functools.partial(uc.check_async, fetcher=slow)
for _ in range(3):
    root = gui.TkinterDnD.Tk() if gui._DND else tk.Tk()
    app = gui.App(root)
    root.after(1700, app._on_close)      # 요청이 나간 지 0.2초
    root.mainloop()
    del app, root
    time.sleep(2.0)          # 창이 없는 사이에 스레드가 끝난다
print("survived")
"""


def test_closing_while_the_request_is_out_does_not_abort_tcl(tmp_path):
    """고치기 전에는 "Tcl_AsyncDelete: async handler deleted by the wrong thread" 로 죽었다."""
    import subprocess

    script = tmp_path / "close_while_asking.py"
    script.write_text(CLOSE_WHILE_ASKING.format(root=str(ROOT)), encoding="utf-8")
    p = subprocess.run([sys.executable, "-W", "ignore", str(script)], capture_output=True, timeout=180)
    out = (p.stdout + p.stderr).decode("utf-8", "replace")
    assert p.returncode == 0 and "survived" in out and "Tcl_AsyncDelete" not in out, out[-800:]

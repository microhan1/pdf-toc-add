"""새 버전 확인: 하루 한 번, 끄기, 조용한 실패, 보내는 내용, 알림을 보여 주는 조건.

서버는 언제나 가짜다 - 이 테스트는 실제 책갈피 서버에 접속하지 않는다.
"""

from __future__ import annotations

import io
import json
import socket
import sys
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import i18n  # noqa: E402
import prefs as prefs_mod  # noqa: E402
import update_check as uc  # noqa: E402
import version  # noqa: E402

DAY = "2026-10-14"
CUR = version.APP_VERSION
OK = {"slug": "pdftoc", "latest": "1.2.0", "tag": "v1.2.0", "client": CUR, "updateAvailable": True,
      "url": "https://chaekgalpi.co.kr/tools/pdftoc?utm_source=app&utm_medium=update"}


class FakeRoot:
    """after() 는 콜백을 바로 부른다. 백그라운드 스레드도 그 자리에서 돈다(아래 fixture)."""

    def __init__(self):
        self.delays = []

    def after(self, ms, fn):
        self.delays.append(ms)
        fn()


@pytest.fixture(autouse=True)
def inline_threads(monkeypatch):
    class InlineThread:
        def __init__(self, target, name=None, daemon=None):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(uc.threading, "Thread", InlineThread)


def run(p, fetcher, day=DAY):
    """프로그램 한 번 실행: 확인을 예약하고, 서버가 답했을 때만 날짜를 적는다(GUI 와 같은 방식)."""
    results = []

    def on_result(info, answered):
        results.append(info)
        if answered:
            p.update_check_last = day

    root = FakeRoot()
    scheduled = uc.check_async(root, version.UPDATE_SLUG, CUR, p, on_result, fetcher=fetcher, day=day)
    return scheduled, results, root


def counting(answer):
    calls = []

    def fetcher(slug, version_):
        calls.append((slug, version_))
        return answer

    return fetcher, calls


# ------------------------------------------------------------------ 얼마나 자주
def test_same_day_twice_asks_once():
    p = prefs_mod.Prefs()
    fetcher, calls = counting(OK)
    run(p, fetcher)
    run(p, fetcher)
    assert len(calls) == 1
    run(p, fetcher, day="2026-10-15")
    assert len(calls) == 2


def test_switched_off_never_asks():
    p = prefs_mod.Prefs(update_check=False)
    fetcher, calls = counting(OK)
    scheduled, results, root = run(p, fetcher)
    assert not scheduled and calls == [] and results == [] and root.delays == []


def test_offline_does_not_use_up_the_day():
    p = prefs_mod.Prefs()
    fetcher, calls = counting(None)  # 답이 없다
    run(p, fetcher)
    run(p, fetcher)
    assert len(calls) == 2 and p.update_check_last == ""


def test_waits_one_and_a_half_seconds_first():
    _, _, root = run(prefs_mod.Prefs(), counting(OK)[0])
    assert root.delays[0] == 1500


def test_asks_with_this_tools_slug_and_version():
    fetcher, calls = counting(OK)
    run(prefs_mod.Prefs(), fetcher)
    assert calls == [("pdftoc", CUR)]


# ------------------------------------------------------------------ 보내는 내용
class FakeResp(io.BytesIO):
    def __init__(self, body: bytes, status: int = 200):
        super().__init__(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_request_carries_only_slug_version_and_os():
    seen = {}

    def opener(req, timeout):
        seen["url"], seen["timeout"] = req.full_url, timeout
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        return FakeResp(json.dumps(OK).encode())

    assert uc.fetch("pdftoc", CUR, opener=opener) == OK
    url = urllib.parse.urlsplit(seen["url"])
    assert (url.scheme, url.netloc, url.path) == ("https", "chaekgalpi.co.kr", "/api/tools/pdftoc/latest")
    assert urllib.parse.parse_qs(url.query) == {"v": [CUR], "os": ["win"]}
    assert seen["timeout"] == 4.0
    assert seen["headers"]["user-agent"] == f"chaekgalpi-tool/pdftoc/{CUR}"
    assert set(seen["headers"]) <= {"user-agent", "accept"}  # 기기·사용자에 대한 것은 아무것도 없다


def test_nothing_about_the_pdf_or_the_machine_is_sent():
    """질의 문자열과 헤더를 통째로 봐도 경로·파일명·사용자 이름이 없다."""
    seen = {}

    def opener(req, timeout):
        seen["text"] = req.full_url + " " + " ".join(f"{k}:{v}" for k, v in req.header_items())
        return FakeResp(json.dumps(OK).encode())

    uc.fetch("pdftoc", CUR, opener=opener)
    low = seen["text"].lower()
    import os
    names = [n for n in (os.environ.get("USERNAME"), os.environ.get("COMPUTERNAME")) if n]
    for forbidden in [".pdf", ".txt", "\\", "c:", "appdata", "offset"] + [n.lower() for n in names]:
        assert forbidden not in low, (forbidden, seen["text"])


@pytest.mark.parametrize("behaviour", ["urlerror", "timeout", "http500", "badjson", "list", "status500", "oserror"])
def test_failures_are_silent(behaviour):
    def opener(req, timeout):
        if behaviour == "urlerror":
            raise urllib.error.URLError("offline")
        if behaviour == "timeout":
            raise socket.timeout("slow")
        if behaviour == "http500":
            raise urllib.error.HTTPError(req.full_url, 500, "boom", {}, None)
        if behaviour == "oserror":
            raise OSError("reset")
        if behaviour == "badjson":
            return FakeResp(b"<html>not json")
        if behaviour == "list":
            return FakeResp(b"[1, 2]")
        return FakeResp(json.dumps(OK).encode(), status=500)

    assert uc.fetch("pdftoc", CUR, opener=opener) is None


def test_a_huge_answer_is_cut_off():
    body = json.dumps(dict(OK, pad="x" * (uc.MAX_BYTES * 2))).encode()
    assert uc.fetch("pdftoc", CUR, opener=lambda req, timeout: FakeResp(body)) is None


# ------------------------------------------------------------------ 알림을 보여 주는 조건
@pytest.mark.parametrize("flag", [False, None, "true", 1, "", {}])
def test_no_notice_unless_server_says_true(flag):
    assert uc.interpret(dict(OK, updateAvailable=flag), CUR) is None


def test_no_notice_when_the_key_is_missing():
    assert uc.interpret({"latest": "1.2.0", "url": OK["url"]}, CUR) is None
    assert uc.interpret(None, CUR) is None
    assert uc.interpret([1, 2], CUR) is None


def test_notice_once_when_newer():
    p = prefs_mod.Prefs()
    fetcher, _ = counting(OK)
    _, results, _ = run(p, fetcher)
    assert len(results) == 1 and results[0] == uc.UpdateInfo("1.2.0", CUR, OK["url"])


def test_later_hides_that_version_but_not_a_newer_one():
    p = prefs_mod.Prefs(update_check_skipped="1.2.0")
    assert uc.interpret(OK, CUR, p.update_check_skipped) is None
    newer = dict(OK, latest="1.2.1")
    assert uc.interpret(newer, CUR, p.update_check_skipped).latest == "1.2.1"


@pytest.mark.parametrize("url", ["https://github.com/microhan1/pdf-toc-add/releases",
                                 "http://chaekgalpi.co.kr/tools/pdftoc",
                                 "https://chaekgalpi.co.kr.evil.example/",
                                 "https://evil.example/?x=https://chaekgalpi.co.kr/",
                                 "javascript:alert(1)", "file:///C:/Windows", None, 5, ""])
def test_only_pages_of_the_tools_site_are_opened(url):
    assert uc.interpret(dict(OK, url=url), CUR) is None


@pytest.mark.parametrize("latest", ["", "   ", None, 3, "x" * 40])
def test_odd_versions_show_nothing(latest):
    assert uc.interpret(dict(OK, latest=latest), CUR) is None


def test_the_version_is_trimmed():
    assert uc.interpret(dict(OK, latest=" 1.2.0 "), CUR).latest == "1.2.0"


# ------------------------------------------------------------------ 스레드와 Tk
def test_the_thread_holds_no_tk_object(monkeypatch):
    """받아오는 스레드가 창을 붙들고 있으면 안 된다: 마지막 참조가 스레드에 남으면 Tk 물건이
    메인 스레드 밖에서 풀리고 Tcl 이 죽는다."""
    captured = {}

    class CaptureThread:
        def __init__(self, target, name=None, daemon=None):
            captured["target"] = target

        def start(self):
            pass

    monkeypatch.setattr(uc.threading, "Thread", CaptureThread)

    class Root:
        def after(self, ms, fn):
            if ms == uc.DELAY_MS:
                fn()

    root, on_result = Root(), lambda info, answered: None
    uc.check_async(root, version.UPDATE_SLUG, CUR, prefs_mod.Prefs(), on_result, fetcher=lambda s, v: OK, day=DAY)
    target = captured["target"]
    held = [c.cell_contents for c in (target.__closure__ or ())] + list(target.__defaults__ or ())
    assert not any(x is root or x is on_result for x in held)


def test_the_answer_is_picked_up_by_polling(monkeypatch):
    """답이 아직 없으면 Tk 가 POLL_MS 뒤에 다시 들여다보기만 한다. 스레드는 Tk 를 부르지 않는다."""
    fetches, results, scheduled = [], [], []

    class Deferred:  # 스레드를 아직 돌리지 않는다: 답이 늦게 오는 상황
        def __init__(self, target, name=None, daemon=None):
            self.target = target
            fetches.append(target)

        def start(self):
            pass

    monkeypatch.setattr(uc.threading, "Thread", Deferred)

    class Root:
        def after(self, ms, fn):
            if ms == uc.DELAY_MS:
                fn()
            else:
                scheduled.append((ms, fn))  # 다시 들여다보기로 예약된 것

    uc.check_async(Root(), version.UPDATE_SLUG, CUR, prefs_mod.Prefs(),
                   lambda info, answered: results.append(info), fetcher=lambda s, v: OK, day=DAY)
    assert results == [] and [ms for ms, _ in scheduled] == [uc.POLL_MS]

    fetches[0]()                 # 이제 답이 도착했다
    scheduled[-1][1]()           # 다음 들여다보기
    assert results == [uc.UpdateInfo("1.2.0", CUR, OK["url"])]


# ------------------------------------------------------------------ 설정
def test_settings_are_type_checked(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(i18n, "config_path", lambda: cfg)

    cfg.write_text(json.dumps({"update_check": "no", "update_check_last": 20261014,
                               "update_check_skipped": ["1.2.0"]}), encoding="utf-8")
    assert prefs_mod.load() == prefs_mod.Prefs(True, "", "")

    cfg.write_text("[1, 2]", encoding="utf-8")
    assert prefs_mod.load() == prefs_mod.Prefs()

    cfg.write_text("not json at all", encoding="utf-8")
    assert prefs_mod.load() == prefs_mod.Prefs()

    cfg.write_text(json.dumps({"update_check": False, "update_check_last": DAY}), encoding="utf-8")
    assert prefs_mod.load() == prefs_mod.Prefs(False, DAY, "")


def test_saving_keeps_the_other_settings(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(i18n, "config_path", lambda: cfg)
    cfg.write_text(json.dumps({"lang": "zh", "something_else": 7}), encoding="utf-8")

    prefs_mod.save(prefs_mod.Prefs(update_check=False, update_check_last=DAY))
    saved = json.loads(cfg.read_text(encoding="utf-8"))
    assert saved["lang"] == "zh" and saved["something_else"] == 7
    assert saved["update_check"] is False and saved["update_check_last"] == DAY

    i18n.save_lang("en")  # 언어를 저장해도 새 버전 확인 설정이 지워지지 않는다
    saved = json.loads(cfg.read_text(encoding="utf-8"))
    assert saved["lang"] == "en" and saved["update_check"] is False


def test_an_unwritable_settings_file_is_not_fatal(tmp_path, monkeypatch):
    blocker = tmp_path / "blocker"        # 폴더가 있어야 할 자리에 파일이 있다
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(i18n, "config_path", lambda: blocker / "pdf_toc_add" / "config.json")
    prefs_mod.save(prefs_mod.Prefs())  # 예외가 나지 않는다
    assert prefs_mod.load() == prefs_mod.Prefs()


def test_version_is_one_value():
    assert version.APP_VERSION == CUR and version.UPDATE_SLUG == "pdftoc"
    assert uc.SITE == "https://chaekgalpi.co.kr/"


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_every_language_has_the_update_strings(lang):
    keys = ("opt_update_check", "update_available", "btn_update", "btn_later")
    assert all(i18n.STRINGS[lang].get(k) for k in keys)
    i18n.set_lang(lang)
    assert "1.2.0" in i18n.tr("update_available", latest="1.2.0", current=CUR)


def test_the_korean_notice_reads_as_agreed():
    i18n.set_lang("ko")
    assert i18n.tr("update_available", latest="1.2.0", current="1.1.1") == "새 버전이 나왔습니다: 1.2.0 (현재 1.1.1)"

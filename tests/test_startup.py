"""시작 그림(PyInstaller --splash)과 pypdf 늦게 불러오기 (2026-11-10, 허브 공통 지시서).

- import pdf_toc_add / pdf_toc_gui 만으로는 pypdf 가 올라오지 않는다 (새 파이썬 프로세스에서 확인).
- 창이 뜨자마자(배경 불러오기가 끝나기 전에) 실행해도 결과가 같다.
- 시작 그림은 창을 다 그린 뒤 한 번 닫히고, 창을 만들다 실패해도 닫힌다. pyi_splash 가 없으면 아무 일도 없다.
"""

from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

import pdf_toc_add as core
import pdf_toc_gui

ROOT = Path(__file__).resolve().parents[1]


def run_fresh(code: str) -> str:
    """새 파이썬 프로세스에서 저장소 루트를 경로에 넣고 code 를 돌린다. 이 프로세스는 이미 pypdf 가 올라와 있어서."""
    proc = subprocess.run([sys.executable, "-c", f"import sys; sys.path.insert(0, {str(ROOT)!r})\n" + code],
                          capture_output=True, text=True, encoding="utf-8", timeout=120, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


# ---------------------------------------------------------------- 늦게 불러오기

def test_importing_core_and_gui_does_not_load_pypdf():
    out = run_fresh(
        "import pdf_toc_add, offset_detect, pdf_toc_gui\n"
        "print('pypdf' in sys.modules, type(pdf_toc_add.PdfReader).__name__, pdf_toc_add._heavy_loaded)\n"
        "pdf_toc_add.load_heavy()\n"
        "print('pypdf' in sys.modules, pdf_toc_add.PdfReader.__name__, pdf_toc_add._heavy_loaded)\n")
    assert out.splitlines() == ["False _Deferred False", "True PdfReader True"]


def test_deferred_name_calls_the_real_class_once_loaded(tmp_path: Path):
    pdf = tmp_path / "a.pdf"
    w = PdfWriter()
    w.add_blank_page(width=100, height=100)
    with pdf.open("wb") as fh:
        w.write(fh)
    d = core._Deferred("PdfReader")
    assert len(d(str(pdf)).pages) == 1          # __call__ 이 진짜 PdfReader 를 부른다
    assert d.__name__ == "PdfReader"            # __getattr__ 도 진짜 클래스로 간다


def test_build_right_after_window_matches_normal_result(tmp_path: Path):
    """배경 불러오기(preload_heavy)가 도는 동안 바로 실행해도 결과가 같다."""
    pdf = tmp_path / "scan.pdf"
    w = PdfWriter()
    for _ in range(12):
        w.add_blank_page(width=400, height=600)
    with pdf.open("wb") as fh:
        w.write(fh)
    toc = tmp_path / "toc.txt"
    toc.write_text("1장 시작 1\n  1.1 절 3\n2장 다음 7\n", encoding="utf-8")
    out = tmp_path / "out.pdf"
    run_fresh(
        "import threading, pathlib\n"
        "import pdf_toc_add as core\n"
        "assert 'pypdf' not in sys.modules\n"
        "t = threading.Thread(target=core.preload_heavy, daemon=True); t.start()\n"
        f"parsed = core.parse_toc(pathlib.Path({str(toc)!r}).read_text(encoding='utf-8'))\n"
        f"core.build_pdf(pathlib.Path({str(pdf)!r}), pathlib.Path({str(out)!r}), parsed.entries, 2, keep_existing=False)\n"
        "t.join(10)\n"
        "assert core._heavy_loaded\n")
    assert _flat(PdfReader(str(out))) == [("1장 시작", 2), ("1.1 절", 4), ("2장 다음", 8)]


def _flat(r: PdfReader):
    out = []

    def walk(items):
        for o in items:
            if isinstance(o, list):
                walk(o)
            else:
                out.append((o.title, r.get_destination_page_number(o)))
    walk(r.outline)
    return out


def test_concurrent_loaders_do_not_break(tmp_path: Path):
    out = run_fresh(
        "import threading\n"
        "import pdf_toc_add as core\n"
        "errs = []\n"
        "def go():\n"
        "    try:\n"
        "        core.load_heavy(); core.PdfWriter()\n"
        "    except Exception as e: errs.append(repr(e))\n"
        "ts = [threading.Thread(target=go) for _ in range(8)]\n"
        "[t.start() for t in ts]; [t.join(30) for t in ts]\n"
        "print(len(errs), core.PdfWriter.__name__)\n")
    assert out.strip() == "0 PdfWriter"


# ---------------------------------------------------------------- 시작 그림

@pytest.fixture
def fake_splash(monkeypatch):
    mod = types.ModuleType("pyi_splash")
    mod.calls = []
    mod.close = lambda: mod.calls.append(1)
    monkeypatch.setitem(sys.modules, "pyi_splash", mod)
    return mod


def test_close_splash_without_pyi_splash_is_a_noop(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyi_splash", None)   # import 가 ImportError 를 낸다
    core.close_splash()


def test_close_splash_swallows_errors(fake_splash):
    def boom():
        raise RuntimeError("already closed")
    fake_splash.close = boom
    core.close_splash()


def test_run_closes_splash_once_after_window_is_drawn(monkeypatch, fake_splash):
    seen = {}

    class FakeRoot:
        def update(self):
            seen["update_before_close"] = len(fake_splash.calls)

        def mainloop(self):
            seen["mainloop_after_close"] = len(fake_splash.calls)

    class FakeApp:
        def __init__(self, root, pdf, toc):
            seen["app_splash_open"] = len(fake_splash.calls) == 0

    monkeypatch.setattr(pdf_toc_gui, "_DND", False)
    monkeypatch.setattr(pdf_toc_gui.tk, "Tk", FakeRoot)
    monkeypatch.setattr(pdf_toc_gui, "App", FakeApp)
    started = []
    monkeypatch.setattr(pdf_toc_gui.threading, "Thread",
                        lambda **kw: types.SimpleNamespace(start=lambda: started.append(kw["target"])))
    assert pdf_toc_gui.run() == 0
    assert seen == {"app_splash_open": True, "update_before_close": 0, "mainloop_after_close": 1}
    assert fake_splash.calls == [1]
    assert started == [core.preload_heavy]      # 창이 뜬 뒤에 배경 불러오기를 시작한다


def test_run_closes_splash_when_window_creation_fails(monkeypatch, fake_splash):
    class FakeRoot:
        def update(self):
            pass

    def failing_app(root, pdf, toc):
        raise RuntimeError("no display")

    monkeypatch.setattr(pdf_toc_gui, "_DND", False)
    monkeypatch.setattr(pdf_toc_gui.tk, "Tk", FakeRoot)
    monkeypatch.setattr(pdf_toc_gui, "App", failing_app)
    with pytest.raises(RuntimeError):
        pdf_toc_gui.run()
    assert fake_splash.calls == [1]


def test_cli_closes_splash(monkeypatch, fake_splash, tmp_path: Path, capsys):
    pdf = tmp_path / "a.pdf"
    w = PdfWriter()
    w.add_blank_page(width=100, height=100)
    with pdf.open("wb") as fh:
        w.write(fh)
    toc = tmp_path / "toc.txt"
    toc.write_text("1장 1\n", encoding="utf-8")
    core.main([str(pdf), str(toc), "--dry-run"])
    assert fake_splash.calls == [1]

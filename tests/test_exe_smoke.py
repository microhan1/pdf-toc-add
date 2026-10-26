"""빌드한 exe 점검: 창이 뜨고 닫히는지만 본다. PDF_TOC_EXE 에 exe 경로를 줄 때만 돈다.

    PDF_TOC_EXE=dist\\pdf_toc_add.exe python -m pytest tests/test_exe_smoke.py

exe 는 conftest 의 차단이 닿지 않으므로 죽은 프록시(127.0.0.1:9) 환경으로 띄워 새 버전 확인이
운영 서버에 닿지 못하게 한다. 설정은 임시 폴더(APPDATA)에만 쓰인다. 메뉴는 누르지 않는다
(실제 브라우저를 열지 않는다). 창은 HWND 로 찾아 WM_CLOSE 로 닫는다.
"""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

import pytest

EXE = os.environ.get("PDF_TOC_EXE", "")
pytestmark = pytest.mark.skipif(not (sys.platform == "win32" and EXE and Path(EXE).is_file()),
                                reason="PDF_TOC_EXE 로 빌드한 exe 를 줄 때만 돈다")

DEAD_PROXY = "http://127.0.0.1:9"
WM_CLOSE = 0x0010


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


def process_tree(root_pid: int) -> set[int]:
    """root_pid 와 그 자손(onefile exe 는 부트로더가 자식 프로세스로 앱을 띄운다)."""
    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    parent: dict[int, int] = {}
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    ok = k32.Process32FirstW(snap, ctypes.byref(entry))
    while ok:
        parent[entry.th32ProcessID] = entry.th32ParentProcessID
        ok = k32.Process32NextW(snap, ctypes.byref(entry))
    k32.CloseHandle(snap)
    tree, grew = {root_pid}, True
    while grew:
        more = {p for p, pp in parent.items() if pp in tree} - tree
        tree |= more
        grew = bool(more)
    return tree


def visible_windows(pids: set[int]) -> list[int]:
    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
            found.append(hwnd)
        return True

    user32.EnumWindows(each, 0)
    return found


def test_window_opens_and_closes_with_a_dead_proxy(tmp_path):
    env = dict(os.environ, HTTP_PROXY=DEAD_PROXY, HTTPS_PROXY=DEAD_PROXY, http_proxy=DEAD_PROXY,
               https_proxy=DEAD_PROXY, NO_PROXY="", APPDATA=str(tmp_path), PDF_TOC_LANG="ko")
    proc = subprocess.Popen([EXE], env=env)
    try:
        hwnds: list[int] = []
        end = time.time() + 60
        while not hwnds and time.time() < end and proc.poll() is None:
            time.sleep(0.5)
            hwnds = visible_windows(process_tree(proc.pid))
        assert hwnds, "창이 뜨지 않았다"
        time.sleep(4)  # 새 버전 확인(1.5초 뒤)이 죽은 프록시에 막혀 조용히 끝날 시간
        assert proc.poll() is None, "창이 뜬 뒤 저절로 죽었다"
        for h in hwnds:
            ctypes.windll.user32.PostMessageW(h, WM_CLOSE, 0, 0)
        assert proc.wait(timeout=30) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
    cfg = tmp_path / "pdf_toc_add" / "config.json"
    # 서버가 답했을 때만 날짜를 쓴다: 죽은 프록시라 답이 없었어야 한다
    assert not cfg.exists() or "update_check_last" not in cfg.read_text(encoding="utf-8")

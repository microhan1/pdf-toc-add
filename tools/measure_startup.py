"""exe 를 켜서 시작 그림과 창이 뜨기까지 걸리는 시간을 잰다 (2026-11-10, 허브 공통 지시서 「시작 그림」).

    python tools/measure_startup.py <exe> [횟수=3] [--shot 그림.png]

- 인터넷은 죽은 프록시(127.0.0.1:9)로 막아 새 버전 확인이 운영 서버에 닿지 않게 한다(전역 규칙 §8).
- APPDATA·TEMP 를 임시 폴더로 돌려서 사용자 설정을 건드리지 않고, 강제 종료로 남은 _MEI* 도 그 폴더째 지운다.
- 이 exe 가 띄운 프로세스(부모·자식)의 창만 본다. 사용자가 켜 둔 창은 세지 않는다.
- 창 구분: 제목 표시줄(WS_CAPTION)이 있고 제목이 「PDF」로 시작하는 창 = 프로그램 창, 제목 표시줄이 없는 창 = 시작 그림.
- 작업 표시줄 칸: 보이고, 주인 창이 없고, WS_EX_TOOLWINDOW 가 아닌 창의 수.
TrimPDF regress/measure_startup.py 를 이 저장소에 맞춰 옮긴 것.
"""
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes

sys.stdout.reconfigure(encoding="utf-8")

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
user32.SetProcessDPIAware()

GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_CAPTION, WS_EX_TOOLWINDOW = 0x00C00000, 0x00000080
GW_OWNER = 4
user32.GetWindowLongW.restype = ctypes.c_long
user32.GetWindow.restype = wintypes.HWND
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
DEAD_PROXY = "http://127.0.0.1:9"


class PE(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]


def family(root_pid):
    """root_pid 와 그 자손 pid 집합(onefile exe 는 부트로더가 자식으로 앱을 띄운다)."""
    snap = kernel32.CreateToolhelp32Snapshot(2, 0)
    pe = PE()
    pe.dwSize = ctypes.sizeof(PE)
    parents = {}
    ok = kernel32.Process32FirstW(snap, ctypes.byref(pe))
    while ok:
        parents[pe.th32ProcessID] = pe.th32ParentProcessID
        ok = kernel32.Process32NextW(snap, ctypes.byref(pe))
    kernel32.CloseHandle(snap)
    found = {root_pid}
    grew = True
    while grew:
        grew = False
        for pid, parent in parents.items():
            if parent in found and pid not in found:
                found.add(pid)
                grew = True
    return found


def windows_of(pids):
    """pids 가 가진 보이는 최상위 창 목록."""
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            n = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            out.append(dict(hwnd=hwnd, title=buf.value, pid=pid.value,
                            caption=bool((style & WS_CAPTION) == WS_CAPTION),
                            taskbar=not (ex & WS_EX_TOOLWINDOW) and not user32.GetWindow(hwnd, GW_OWNER),
                            size=(r.right - r.left, r.bottom - r.top)))
        return True
    user32.EnumWindows(cb, 0)
    return out


def shot(hwnd, path):
    """화면에 실제로 보이는 모습을 찍는다(시작 그림은 DPI 미인식 창이라 PrintWindow 로는 배율이 빠진다)."""
    from PIL import ImageGrab
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    ImageGrab.grab((r.left, r.top, r.right, r.bottom), all_screens=True).save(path)


def measure(exe, shot_path=None, limit=60):
    root = tempfile.mkdtemp(prefix="pdftoc_measure_")
    tmp = os.path.join(root, "tmp")
    os.makedirs(tmp)
    env = dict(os.environ, APPDATA=os.path.join(root, "appdata"), TEMP=tmp, TMP=tmp,
               HTTP_PROXY=DEAD_PROXY, HTTPS_PROXY=DEAD_PROXY, http_proxy=DEAD_PROXY, https_proxy=DEAD_PROXY,
               NO_PROXY="")
    env.pop("PDF_TOC_LANG", None)
    t0 = time.perf_counter()
    proc = subprocess.Popen([exe], env=env)
    res = dict(splash=None, window=None, splash_gone=None, tasks_max=0, tasks_after=None, leftover=None, mei=0)
    try:
        pids = family(proc.pid)
        last_family = 0.0
        settled = None
        while time.perf_counter() - t0 < limit:
            now = time.perf_counter() - t0
            if now - last_family > 0.1:
                pids = family(proc.pid)
                last_family = now
            ws = windows_of(pids)
            plain = [w for w in ws if not w["caption"]]
            main = [w for w in ws if w["caption"] and w["title"].startswith("PDF")]
            res["tasks_max"] = max(res["tasks_max"], sum(w["taskbar"] for w in ws))
            if plain and res["splash"] is None:
                res["splash"] = now
                res["splash_info"] = plain[0]
                if shot_path:
                    time.sleep(0.15)
                    shot(plain[0]["hwnd"], shot_path)
            if main and res["window"] is None:
                res["window"] = now
                res["window_title"] = main[0]["title"]
                settled = now
            if res["window"] is not None and not plain and res["splash_gone"] is None:
                res["splash_gone"] = now
            # 창이 뜨고 시작 그림이 사라진 뒤 0.5초, 또는 안 사라지면 창이 뜨고 5초 뒤의 모습
            if settled is not None and ((res["splash_gone"] is not None and now - res["splash_gone"] > 0.5)
                                        or now - settled > 5.0):
                res["tasks_after"] = sum(w["taskbar"] for w in ws)
                res["leftover"] = len(plain)
                break
            time.sleep(0.01)
        res["mei"] = len([d for d in os.listdir(tmp) if d.startswith("_MEI")])
    finally:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        time.sleep(1.0)
        shutil.rmtree(root, ignore_errors=True)     # 강제 종료로 남은 _MEI* 는 이 임시 폴더 안에만 있다
    return res


def fmt(v):
    return f"{v:.2f}" if isinstance(v, float) else "-"


def main():
    args = list(sys.argv[1:])
    shot_path = None
    if "--shot" in args:
        i = args.index("--shot")
        shot_path = args[i + 1]
        del args[i:i + 2]
    # exe 를 둘 이상 주면 번갈아 잰다(전·후를 같은 때에 비교하려고). 숫자는 횟수.
    exes = [a for a in args if not a.isdigit()]
    n = next((int(a) for a in args if a.isdigit()), 3)
    for exe in exes:
        print(f"{exe}  ({os.path.getsize(exe) / 1024 / 1024:.1f}MB)")
    print("exe | 회 | 시작 그림(초) | 창(초) | 시작 그림 사라짐(초) | 작업 표시줄 최대 | 창 뜬 뒤 칸 | 남은 시작 그림 | _MEI")
    rows = {exe: [] for exe in exes}
    for k in range(1, n + 1):
        for i, exe in enumerate(exes):
            r = measure(exe, shot_path if k == 1 and i == len(exes) - 1 else None)
            rows[exe].append(r)
            print(f"{chr(65 + i)} | {k} | {fmt(r['splash'])} | {fmt(r['window'])} | {fmt(r['splash_gone'])} | {r['tasks_max']} | "
                  f"{r['tasks_after']} | {r['leftover']} | {r['mei']}", flush=True)
            if r.get("splash_info"):
                print("   시작 그림 창:", {k2: r["splash_info"][k2] for k2 in ("title", "taskbar", "size")}, flush=True)
            if r.get("window_title"):
                print("   프로그램 창:", r["window_title"], flush=True)
    for i, exe in enumerate(exes):
        win = [r["window"] for r in rows[exe] if r["window"]]
        spl = [r["splash"] for r in rows[exe] if r["splash"]]
        if win:
            print(f"{chr(65 + i)} 평균: 창 {sum(win) / len(win):.2f}초" + (f" · 시작 그림 {sum(spl) / len(spl):.2f}초" if spl else ""))


if __name__ == "__main__":
    main()

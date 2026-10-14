"""시작할 때 하루 한 번, 책갈피 툴 사이트에 새 버전이 있는지 묻는다.

보내는 것은 도구 이름(slug), 버전, "win" 뿐이다. 파일, 경로, 기기, 사용자 정보는 보내지 않는다.
창이 뜨고 1.5초 뒤 백그라운드 스레드에서 한 번만 돌고 화면을 막지 않는다. 실패(오프라인, 시간 초과,
HTTP 오류, 잘못된 JSON)는 조용히 지나간다. 버전 비교는 서버가 한다(`updateAvailable`).
null 이면 "비교할 수 없음"이므로 아무것도 보여 주지 않는다. 표준 라이브러리만 쓴다.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import threading
import urllib.parse
import urllib.request
from typing import Callable

API = "https://chaekgalpi.co.kr/api/tools/{slug}/latest"
SITE = "https://chaekgalpi.co.kr/"  # 알림은 이 사이트의 페이지만 연다
TIMEOUT = 4.0
DELAY_MS = 1500
POLL_MS = 100       # Tk 스레드가 답을 들여다보는 간격
MAX_BYTES = 64 * 1024


@dataclasses.dataclass
class UpdateInfo:
    latest: str
    current: str
    url: str
    url_en: str = ""   # 영어 판 툴 페이지. 서버가 주지 않으면 빈 문자열

    def page_for(self, lang: str) -> str:
        """화면 언어에 맞는 페이지. 영어·중국어 화면은 영어 판이 있으면 그쪽을 연다."""
        return self.url_en if (lang in ("en", "zh") and self.url_en) else self.url


def today() -> str:
    return datetime.date.today().isoformat()


def should_check(prefs, day: str) -> bool:
    """확인이 켜져 있고, 오늘 아직 묻지 않았다."""
    return bool(getattr(prefs, "update_check", True)) and getattr(prefs, "update_check_last", "") != day


def fetch(slug: str, version: str, *, opener: Callable = urllib.request.urlopen) -> dict | None:
    """서버의 답. 어떤 이유로든 실패하면 None."""
    query = urllib.parse.urlencode({"v": version, "os": "win"})
    req = urllib.request.Request(f"{API.format(slug=slug)}?{query}",
                                 headers={"User-Agent": f"chaekgalpi-tool/{slug}/{version}",
                                          "Accept": "application/json"})
    try:
        with opener(req, timeout=TIMEOUT) as resp:
            if getattr(resp, "status", 200) != 200:
                return None
            data = json.loads(resp.read(MAX_BYTES).decode("utf-8"))
    except Exception:  # 오프라인, 시간 초과, HTTP 오류, 잘못된 JSON: 아무 말도 하지 않는다
        return None
    return data if isinstance(data, dict) else None


def interpret(data: dict | None, version: str, skipped: str = "") -> UpdateInfo | None:
    """서버가 새 버전이 있다고 했고, 사용자가 "다음에"로 넘긴 버전이 아니며, 링크가 툴 사이트를
    가리킬 때만 UpdateInfo 를 돌려준다."""
    if not isinstance(data, dict) or data.get("updateAvailable") is not True:
        return None
    latest, url = data.get("latest"), data.get("url")
    if not isinstance(latest, str) or not latest.strip() or len(latest) > 32:
        return None
    if not isinstance(url, str) or not url.startswith(SITE):
        return None
    latest = latest.strip()
    if latest == (skipped or "").strip():
        return None
    url_en = data.get("urlEn")
    if not isinstance(url_en, str) or not url_en.startswith(SITE):  # 없거나 책갈피 밖이면 안 쓴다
        url_en = ""
    return UpdateInfo(latest, version, url, url_en)


def check_async(root, slug: str, version: str, prefs, on_result: Callable[[UpdateInfo | None, bool], None], *,
                fetcher: Callable = fetch, day: str | None = None) -> bool:
    """지금부터 DELAY_MS 뒤에 한 번 확인하도록 예약한다. on_result(info, answered) 는 Tk 스레드에서
    돈다. answered 는 서버가 답했는지이고(그때만 호출한 쪽이 날짜를 기록한다), info 는 알림을 보여 줘야
    할 때만 들어 있다. 확인할 필요가 없으면 False."""
    if not should_check(prefs, day or today()):
        return False
    skipped = getattr(prefs, "update_check_skipped", "")
    box: dict = {}

    # 스레드는 box 에 답만 담고 Tk 물건(창·App·콜백)을 쥐지 않는다. 전에는 root.after(0, on_result)
    # 로 넘겼는데, 그러면 답을 기다리는 동안 창을 닫았을 때 App 의 마지막 참조가 이 스레드에 남아
    # Tk 변수가 메인 스레드 밖에서 풀리고 Tcl 이 죽었다("Tcl_AsyncDelete: async handler deleted by
    # the wrong thread"). 대신 Tk 스레드가 POLL_MS 마다 들여다본다.
    def work(box=box) -> None:
        box["data"] = fetcher(slug, version)

    def poll() -> None:
        if "data" not in box:
            root.after(POLL_MS, poll)
            return
        data = box["data"]
        on_result(interpret(data, version, skipped), data is not None)

    def start() -> None:
        threading.Thread(target=work, name="update-check", daemon=True).start()
        poll()

    try:
        root.after(DELAY_MS, start)
    except Exception:
        return False
    return True

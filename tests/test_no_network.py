"""차단 자체를 검사한다: 시험이 실수로 책갈피 운영 서버를 치지 못하는지.

conftest 의 no_real_server 가 autouse 로 걸려 있어야 하고, 걸려 있으면 기본값으로 부른
fetch·check_async 가 밖으로 나가지 않는다.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prefs as prefs_mod  # noqa: E402
import update_check as uc  # noqa: E402
import version  # noqa: E402


def test_the_default_opener_is_the_guard():
    assert uc.fetch.__kwdefaults__["opener"] is urllib.request.urlopen
    assert urllib.request.urlopen.__name__ == "guard"


def test_a_default_fetch_is_blocked_and_recorded(blocked_requests):
    """인자 없이 부른 fetch 는 기록되고 None 을 돌려준다(예외가 밖으로 새지 않는다)."""
    assert uc.fetch(version.UPDATE_SLUG, version.APP_VERSION) is None
    assert len(blocked_requests) == 1 and "chaekgalpi.co.kr" in blocked_requests[0]
    blocked_requests.clear()  # 일부러 낸 요청이므로 치운다(안 치우면 이 시험이 실패한다)


def test_the_default_fetcher_never_asks_the_server(blocked_requests):
    """fetcher 를 주지 않은 check_async 는 서버에 묻지 않고 '답 없음'으로 끝난다."""
    import time

    calls = []

    class Root:
        """DELAY_MS 는 바로, 다시 들여다보기는 모아 두었다가 아래에서 돌린다."""

        def __init__(self):
            self.pending = []

        def after(self, ms, fn):
            if ms == uc.DELAY_MS:
                fn()
            else:
                self.pending.append(fn)

    root = Root()
    uc.check_async(root, version.UPDATE_SLUG, version.APP_VERSION, prefs_mod.Prefs(),
                   lambda info, answered: calls.append((info, answered)), day="2026-10-15")
    end = time.time() + 5
    while not calls and time.time() < end:
        while root.pending:
            root.pending.pop(0)()
        time.sleep(0.01)
    assert calls == [(None, False)] and blocked_requests == []


def test_other_hosts_are_left_alone(blocked_requests):
    """막는 것은 책갈피 주소뿐이다. 다른 주소는 가로채지 않고 그대로 내보낸다
    (여기서는 아무도 듣지 않는 127.0.0.1:9 로 보내 바로 거절당한다)."""
    import urllib.error

    try:
        urllib.request.urlopen("http://127.0.0.1:9/", timeout=1)
    except urllib.error.URLError as exc:
        assert "시험에서는" not in str(exc)  # 가드가 던진 것이 아니다
    except Exception:
        pass
    assert blocked_requests == []

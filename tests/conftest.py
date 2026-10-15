import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import i18n  # noqa: E402
import update_check  # noqa: E402

SITE_HOST = "chaekgalpi.co.kr"


@pytest.fixture(autouse=True)
def korean_messages():
    """기존 테스트는 한국어 메시지를 기준으로 작성됨."""
    i18n.set_lang("ko")
    yield
    i18n.set_lang("ko")


# ------------------------------------------------------------------ 운영 서버 차단
# 시험이 책갈피 운영 서버를 치지 않게 막는다. 창 시험은 App 을 만들 때마다 새 버전 확인을
# 예약하고, 설정이 임시 폴더라 날짜 가드가 늘 열려 있어서 1.5초 넘게 도는 시험에서 진짜 요청이
# 나갈 수 있다(photo-organizer 에서 이틀 511건이 운영 「실행 확인」 통계에 사람 실행으로 잡힘).
# fetch(opener=...)·check_async(fetcher=...) 는 기본값이 정의 시점에 묶여 모듈 속성만 바꿔서는
# 막히지 않으므로 __kwdefaults__ 와 urllib.request.urlopen 을 함께 바꾼다.

def _url_of(req) -> str:
    return req.full_url if hasattr(req, "full_url") else str(req)


@pytest.fixture(autouse=True)
def no_real_server(monkeypatch, request):
    """나가려 한 요청을 기록하고 막는다. 기록이 남은 채 끝나는 시험은 실패시킨다."""
    blocked: list[str] = []
    real_urlopen = urllib.request.urlopen

    def guard(req, *a, **kw):
        url = _url_of(req)
        if SITE_HOST in url:
            blocked.append(url)
            raise urllib.error.URLError("시험에서는 운영 서버에 접속하지 않는다")
        return real_urlopen(req, *a, **kw)

    def no_server(slug, version):
        """기본 fetcher: 서버에 묻지 않고 '답 없음'."""
        return None

    monkeypatch.setattr(urllib.request, "urlopen", guard)
    if getattr(update_check.fetch, "__kwdefaults__", None):
        monkeypatch.setitem(update_check.fetch.__kwdefaults__, "opener", guard)
    if getattr(update_check.check_async, "__kwdefaults__", None):
        monkeypatch.setitem(update_check.check_async.__kwdefaults__, "fetcher", no_server)

    request.node._blocked_requests = blocked
    yield blocked

    if blocked:
        pytest.fail("시험이 운영 서버로 요청을 보내려 했습니다 ({}건): {}".format(len(blocked), blocked[:3]))


@pytest.fixture
def blocked_requests(no_real_server):
    """차단된 요청 목록. 일부러 요청을 낸 시험은 끝내기 전에 비운다."""
    return no_real_server

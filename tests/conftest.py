import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import i18n  # noqa: E402


@pytest.fixture(autouse=True)
def korean_messages():
    """기존 테스트는 한국어 메시지를 기준으로 작성됨."""
    i18n.set_lang("ko")
    yield
    i18n.set_lang("ko")

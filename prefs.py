"""설정 파일(config.json)의 값. 타입을 검사해서 읽는다.

설정 파일은 누구나 고칠 수 있으므로 내용을 믿지 않는다. 타입이 다르거나 범위를 벗어난 값은 기본값을 쓴다.
언어(lang)는 i18n 이 따로 다루므로 여기서는 건드리지 않는다.
"""

from __future__ import annotations

import dataclasses

import i18n


@dataclasses.dataclass
class Prefs:
    update_check: bool = True       # 하루 한 번, 툴 사이트에 새 버전이 있는지 묻는다
    update_check_last: str = ""     # 서버가 답한 마지막 확인 날짜 (YYYY-MM-DD)
    update_check_skipped: str = ""  # 이 버전에서 "다음에"를 눌렀다: 다시 보여 주지 않는다


def load() -> Prefs:
    raw = i18n.load_settings()
    default = Prefs()

    def typed(key: str, kind: type):
        value = raw.get(key)
        ok = isinstance(value, kind) and (kind is bool or not isinstance(value, bool))
        return value if ok else getattr(default, key)

    return Prefs(
        update_check=typed("update_check", bool),
        update_check_last=typed("update_check_last", str).strip()[:10],
        update_check_skipped=typed("update_check_skipped", str).strip()[:32],
    )


def save(p: Prefs) -> None:
    settings = i18n.load_settings()
    settings.update(dataclasses.asdict(p))
    i18n.save_settings(settings)

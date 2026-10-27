"""i18n.py - 한국어 / English / 中文 / 日本語 메시지 모음.

사용:  from i18n import tr, set_lang
       tr("btn_browse")            -> 현재 언어의 문자열
       tr("log_pdf", path=..., n=3) -> 자리표시자 채움
"""

from __future__ import annotations

import json
import os
from pathlib import Path

LANGS = ("ko", "en", "zh", "ja")
LANG_NAMES = {"ko": "한국어", "en": "English", "zh": "中文", "ja": "日本語"}
_lang = "en"


# ---------------------------------------------------------------- 언어 선택 / 저장

def config_path() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home())
    return Path(base) / "pdf_toc_add" / "config.json"


def load_settings() -> dict:
    """설정 파일 전체. 없거나 깨졌으면 빈 사전. 값의 타입은 쓰는 쪽에서 검사한다."""
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(settings: dict) -> None:
    try:
        p = config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(settings, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # 저장 실패는 치명적이지 않음


def load_saved_lang() -> str | None:
    lang = load_settings().get("lang")
    return lang if lang in LANGS else None


def save_lang(lang: str) -> None:
    settings = load_settings()  # 다른 설정(새 버전 확인 등)을 지우지 않도록 합쳐서 쓴다
    settings["lang"] = lang
    save_settings(settings)


def detect_lang() -> str:
    """환경변수 → 저장된 설정 → Windows UI 언어 → 로케일 순으로 판별."""
    env = os.environ.get("PDF_TOC_LANG", "").lower()[:2]
    if env in LANGS:
        return env
    saved = load_saved_lang()
    if saved:
        return saved
    try:
        import ctypes
        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        return {0x12: "ko", 0x04: "zh", 0x11: "ja", 0x09: "en"}.get(langid, "en")
    except Exception:
        pass
    try:
        import locale
        loc = (locale.getlocale()[0] or os.environ.get("LANG", "")).lower()
        if loc.startswith(("ko", "korean")):
            return "ko"
        if loc.startswith(("zh", "chinese")):
            return "zh"
        if loc.startswith(("ja", "japanese")):
            return "ja"
    except Exception:
        pass
    return "en"


def set_lang(lang: str) -> None:
    global _lang
    _lang = lang if lang in LANGS else "en"


def get_lang() -> str:
    return _lang


def tr(key: str, **kw) -> str:
    table = STRINGS.get(_lang, STRINGS["en"])
    text = table.get(key) or STRINGS["en"].get(key) or key
    return text.format(**kw) if kw else text


# ---------------------------------------------------------------- 문자열

STRINGS: dict[str, dict[str, str]] = {}

STRINGS["ko"] = {
    # ---- 새 버전 확인
    "opt_update_check": "새 버전 확인",
    "update_available": "새 버전이 나왔습니다: {latest} (현재 {current})",
    "btn_update": "업데이트",
    "btn_later": "다음에",
    # ---- 의견 보내기
    "btn_feedback": "의견 보내기",
    "feedback_failed": "브라우저를 열지 못했습니다. 아래 주소를 복사해 브라우저 주소창에 붙여 넣으면 로그인 없이 의견을 보낼 수 있습니다.",
    "feedback_tip": "안 되는 것·불편한 것·바라는 기능을 알려 주세요(브라우저가 열립니다)",
    # ---- offset 자동 감지
    "btn_detect": "자동 감지",
    "detect_start": "offset 자동 감지: 책 본문에서 {n}쪽을 골라 쪽 번호를 찾습니다.",
    "detect_progress": "쪽 번호를 찾는 중… {i}/{n}쪽",
    "detect_ok": "offset {offset:+d} 을(를) 찾았습니다. 쪽 번호가 보인 {pages}쪽 중 {votes}쪽이 같은 값을 가리킵니다 {how}.",
    "detect_how_text": "(PDF 글자 층 사용)",
    "detect_how_ocr": "(Windows OCR 사용)",
    "detect_evidence": "    PDF {pdf}페이지 = 인쇄 {page}쪽",
    "detect_applied": "offset 칸에 {offset} 을(를) 넣었습니다. 미리보기로 한두 개 확인해 보세요.",
    "detect_kept": "목차의 offset={current} 과 감지값 {found} 이 다릅니다. 목차 값을 그대로 두었습니다. 감지값을 쓰려면 [자동 감지] 를 누르세요.",
    "detect_fail_title": "offset 을 자동으로 찾지 못했습니다",
    "detect_fail_no_numbers": "쪽 번호로 보이는 숫자를 찾지 못했습니다. 쪽 번호가 없는 책이거나 글자가 너무 흐릴 수 있습니다.",
    "detect_fail_inconsistent": "쪽 번호 후보가 서로 맞지 않습니다 ({votes}/{pages}쪽 일치). 두 쪽을 한 장에 스캔했거나 쪽 번호가 불규칙할 수 있습니다.",
    "detect_fail_ocr_unavailable": "이 PDF 에는 글자 층이 없고, 이 컴퓨터에서 Windows OCR 을 쓸 수 없습니다.",
    "detect_fail_no_pages": "PDF 에 살펴볼 페이지가 없습니다.",
    "detect_fail_hint": "PDF 뷰어에서 책 1쪽이 PDF 몇 페이지인지 보고 offset 을 직접 입력하세요.",
    "detect_cancelled": "offset 자동 감지를 취소했습니다.",
    "detect_error": "자동 감지 중 오류가 났습니다: {err}",
    "cli_auto_offset": "스캔 이미지의 쪽 번호를 읽어 offset 을 자동으로 찾는다 (--offset 이 있으면 무시)",
    "cli_detect_differs": "목차 파일의 offset={file} 대신 자동 감지한 {found} 을(를) 씁니다.",
    # ---- 목차 파일 읽기
    "read_err": "목차 파일을 읽을 수 없습니다: {path}\n      ({err})",
    "empty_file": "목차 파일이 비어 있습니다: {name}",
    "decode_fail": "목차 파일을 '{enc}' 인코딩으로 읽지 못했습니다: {err}",
    "toc_is_pdf": "'{name}' 은 PDF 파일입니다. 목차 자리에는 텍스트(.txt) 파일을 넣어 주세요.",
    "toc_is_binary": "'{name}' 은 텍스트 파일이 아닌 것 같습니다 (이미지, Word 문서, 압축 파일 등).\n      메모장으로 만든 .txt 파일을 넣어 주세요.",
    "unknown_encoding": "'{name}' 의 인코딩을 알 수 없습니다.\n      메모장에서 '다른 이름으로 저장' → 인코딩을 UTF-8 로 바꿔 저장해 보세요.",
    # ---- 파싱
    "line_fmt": "{n}행: {reason}\n      → {raw}",
    "hint_fmt": "\n      ※ {hint}",
    "offset_not_int": "offset 값이 정수가 아닙니다.",
    "offset_hint": "예) offset=8",
    "range_warn": "{n}행 '{title}': 쪽수가 {a}-{b} 범위로 적혀 있어 앞 숫자 {page}을(를) 사용했습니다.",
    "roman_reason": "로마 숫자 쪽수('{roman}')는 지원하지 않습니다.",
    "roman_hint": "PDF 뷰어에서 실제 페이지 번호를 확인해 아라비아 숫자로 적거나, 이 줄을 지우세요",
    "no_page": "줄 끝에서 쪽수를 찾지 못했습니다.",
    "example_hint": "예)  1장 서론, 12",
    "no_title": "제목이 없습니다 (숫자만 있는 줄).",
    "page_lt_1": "쪽수는 1 이상이어야 합니다.",
    "commented_entry": "{n}행은 # 으로 시작해 주석으로 건너뛰었습니다: {text}",
    "multi_offset": "offset 줄이 {k}개 있습니다 ({lines}행). 마지막 값 {value}을(를) 사용합니다.",
    "parse_head": "목차에서 {n}개 줄을 읽지 못했습니다.",
    "only_first": " (처음 {m}개만 표시)",
    "no_entries": "목차 항목이 하나도 없습니다.\n      파일이 비어 있거나, 모든 줄이 주석(#)이거나 offset 줄뿐입니다.\n      {example}",
    # ---- 검증
    "val_too_big": "{n}행 '{title}': {page}쪽 + offset {offset} = PDF {pdf}페이지 → PDF 는 {total}페이지까지입니다.",
    "val_too_small": "{n}행 '{title}': {page}쪽 + offset {offset} = PDF {pdf}페이지 → 1페이지보다 앞입니다.",
    "val_backwards": "{n}행 '{title}' ({page}쪽)이 앞 항목 '{prev}' ({prevpage}쪽)보다 앞에 있습니다. 오타인지 확인하세요.",
    "val_head": "{n}개 항목이 PDF 페이지 범위(1~{total})를 벗어납니다.",
    "val_all_big": "\n      모든 항목이 범위를 넘습니다. offset({offset})이 너무 크거나 PDF 가 다른 파일일 수 있습니다.",
    "val_all_small": "\n      모든 항목이 1페이지보다 앞입니다. offset({offset})이 너무 작습니다.",
    "val_max_hint": "\n      가장 큰 쪽수는 {n}행 '{title}' {page}쪽입니다. offset 또는 이 줄의 쪽수를 확인하세요.",
    "tree_line": "(인쇄 {page}쪽 -> PDF {pdf}페이지)",
    # ---- PDF
    "pdf_missing": "PDF 파일이 없습니다: {path}",
    "pdf_read_err": "PDF 파일을 읽을 수 없습니다: {path}\n      ({err})",
    "pdf_empty": "'{name}' 은 빈 파일입니다.",
    "pdf_not_pdf": "'{name}' 은 PDF 파일이 아닙니다 (파일 머리에 %PDF 표식이 없습니다).\n      확장자만 .pdf 로 바뀐 파일이거나 손상된 파일일 수 있습니다.",
    "pdf_corrupt": "'{name}' 을 읽지 못했습니다. 파일이 손상됐을 수 있습니다.\n      ({err})",
    "pdf_encrypted_unsupported": "'{name}' 은 암호화된 PDF 입니다. 먼저 암호를 해제한 뒤 사용하세요.\n      ({err})",
    "pdf_encrypted": "'{name}' 은 열람 암호가 걸린 PDF 입니다. 먼저 암호를 해제한 뒤 사용하세요.",
    "pdf_count_fail": "'{name}' 의 페이지를 셀 수 없습니다. 파일이 손상됐을 수 있습니다.\n      ({err})",
    "pdf_zero_pages": "'{name}' 에 페이지가 없습니다.",
    "out_dir_missing": "출력 폴더가 없습니다: {dir}",
    "out_locked": "출력 파일을 쓸 수 없습니다: {path}\n      PDF 뷰어 등 다른 프로그램에서 열려 있으면 닫고 다시 시도하세요.",
    "out_write_fail": "출력 파일을 쓰지 못했습니다: {path}\n      ({err})",
    # ---- CLI
    "cli_desc": "텍스트 목차 파일을 PDF 북마크로 넣습니다.",
    "cli_pdf": "원본 PDF",
    "cli_toc": "목차 텍스트 파일",
    "cli_out": "출력 PDF (기본: 원본이름_toc.pdf)",
    "cli_offset": "PDF 페이지 = 인쇄 쪽수 + offset. 예: 책 1쪽이 PDF 9페이지면 --offset 8. 목차 파일 안의 offset= 줄보다 우선합니다.",
    "cli_encoding": "목차 파일 인코딩 (기본: 자동 판별)",
    "cli_keep": "PDF에 이미 있는 북마크를 지우지 않고 뒤에 추가",
    "cli_dry": "PDF를 쓰지 않고 파싱 결과만 출력",
    "cli_lang": "표시 언어: ko, en, zh, ja (기본: 자동)",
    "cli_epilog": (
        "목차 파일 형식 (한 줄에 항목 하나):\n"
        "    1장 서론, 12쪽\n"
        "    2장 배경, 25\n"
        "      2.1 역사, 26          <- 들여쓰기하면 하위 항목\n"
        "      2.2 현황, 31\n"
        "    3장 결론 p.40\n\n"
        "    # 으로 시작하는 줄은 주석. 빈 줄은 무시.\n"
        "    offset=8                <- 인쇄 쪽수와 PDF 페이지 번호의 차이 (선택)"
    ),
    "cli_toc_missing": "목차 파일이 없습니다: {path}",
    "cli_error": "오류: ",
    "cli_warn": "경고: ",
    "cli_summary": "PDF: {pdf}  ({total}페이지)   offset: {offset:+d}   항목: {n}개",
    "cli_dry_note": "\n(dry-run) PDF는 쓰지 않았습니다.",
    "cli_same": "출력 파일이 원본과 같습니다. -o 로 다른 이름을 지정하세요.",
    "cli_done": "\n완료: {path}",
    # ---- GUI
    "app_title": "PDF 목차 넣기",
    "app_subtitle": "스캔한 책 PDF에 북마크를 넣어 원하는 장으로 바로 건너뛸 수 있게 합니다.",
    "lbl_language": "언어",
    "sec_pdf": "PDF",
    "sec_pdf_hint_dnd": "끌어다 놓거나 찾아보기",
    "sec_pdf_hint_nodnd": "찾아보기로 선택",
    "pdf_drop_hint": "PDF 파일을 여기로 끌어다 놓으세요",
    "pdf_click_hint": "클릭해서 PDF 를 고르세요",
    "pdf_pages": "{name}\n{n}페이지",
    "btn_browse": "찾아보기…",
    "sec_toc": "목차",
    "sec_toc_hint": "한 줄에 하나:  1장 제목, 12쪽   ·   들여쓰기는 하위 항목",
    "btn_open_txt": "텍스트 파일 열기…",
    "btn_example": "예시 채우기",
    "btn_clear": "지우기",
    "toc_drop_hint": "텍스트 파일을 창에 끌어다 놓아도 됩니다",
    "sec_settings": "설정",
    "lbl_offset": "쪽수 보정 (offset)",
    "offset_hint": "책 1쪽이 PDF 9페이지에 있으면 8",
    "lbl_output": "출력 파일",
    "btn_change": "변경…",
    "btn_preview": "미리보기",
    "btn_build": "PDF 만들기",
    "sec_result": "결과",
    "sec_result_hint": "미리보기 또는 PDF 만들기를 누르면 여기에 표시됩니다",
    "dlg_pdf": "원본 PDF 선택",
    "dlg_toc": "목차 텍스트 파일 선택",
    "dlg_out": "출력 PDF",
    "ft_all": "모든 파일",
    "ft_text": "텍스트",
    "log_pdf": "PDF: {path}  ({n}페이지)",
    "warn_few_pages": "페이지가 {n}장뿐입니다. 책 전체 PDF 가 맞는지 확인하세요.",
    "warn_multi_pdf": "PDF 를 {n}개 놓았습니다. 첫 번째({name})만 사용하고 나머지는 무시합니다. 한 번에 한 권씩 처리합니다.",
    "err_is_dir": "'{name}' 은 폴더입니다. PDF 파일이나 목차 텍스트 파일을 놓아 주세요.",
    "err_not_found": "'{path}' 을 찾을 수 없습니다.",
    "err_pdf_open": "PDF 를 열 수 없습니다",
    "err_toc_read": "목차 파일을 읽을 수 없습니다",
    "warn_not_txt": "'{name}' 은 .txt 가 아니지만 텍스트로 읽었습니다. 내용이 이상하면 확인하세요.",
    "log_toc": "목차 파일: {path}",
    "warn_toc_format": "목차 형식에 문제가 있습니다. [미리보기] 를 누르면 어느 줄이 문제인지 볼 수 있습니다.",
    "log_offset_applied": "파일 안의 offset={n} 을 적용했습니다.",
    "err_no_pdf": "PDF 가 없습니다",
    "err_no_pdf_detail": "1번 칸에 PDF 를 끌어다 놓거나 [찾아보기…] 로 고르세요.",
    "err_toc_empty": "목차가 비어 있습니다",
    "err_toc_empty_detail": "2번 칸에 목차를 입력하거나 텍스트 파일을 여세요. [예시 채우기] 로 형식을 볼 수 있습니다.",
    "err_toc_format": "목차 형식 오류",
    "err_offset": "offset 오류",
    "err_offset_detail": "'{v}' 은 정수가 아닙니다. 예) 0, 8, -2",
    "err_range": "쪽수가 PDF 범위를 벗어납니다",
    "summary": "항목 {n}개  ·  offset {offset:+d}  ·  PDF {total}페이지",
    "tree_gui": "{title}  ->  PDF {pdf}페이지",
    "err_same": "출력 파일이 원본과 같습니다",
    "err_same_detail": "원본을 덮어쓰지 않도록 다른 이름을 지정하세요. [변경…] 을 누르세요.",
    "dlg_overwrite_title": "덮어쓰기",
    "dlg_overwrite": "{name} 이 이미 있습니다. 덮어쓸까요?",
    "log_cancelled": "취소했습니다.",
    "err_build": "PDF 를 만들지 못했습니다",
    "err_unexpected": "예상하지 못한 오류",
    "log_done": "완료: {path}",
    "dlg_done_title": "완료",
    "dlg_done": "북마크를 넣었습니다.\n\n{path}",
    "example_toc": (
        "# 한 줄에 항목 하나: 제목, 쪽수\n"
        "# 들여쓰기하면 하위 항목\n"
        "offset=0\n\n"
        "머리말, 1\n"
        "1장 서론, 2\n"
        "    1.1 배경, 3\n"
        "    1.2 목적, 4\n"
        "2장 본론, 5\n"
        "    2.1 방법, 6\n"
        "    2.2 결과, 8\n"
        "3장 결론, 9\n"
    ),
}

STRINGS["en"] = {
    # ---- 새 버전 확인
    "opt_update_check": "Check for updates",
    "update_available": "Version {latest} is available (current {current})",
    "btn_update": "Update",
    "btn_later": "Later",
    # ---- 의견 보내기
    "btn_feedback": "Send feedback",
    "feedback_failed": "Could not open your browser. Copy the address below into your browser's address bar to send feedback (no sign-in needed).",
    "feedback_tip": "Tell us what's broken or missing (opens your browser)",
    # ---- offset 자동 감지
    "btn_detect": "Auto-detect",
    "detect_start": "Offset auto-detect: checking page numbers on {n} pages from the body of the book.",
    "detect_progress": "Looking for page numbers… {i}/{n}",
    "detect_ok": "Found offset {offset:+d}. {votes} of the {pages} pages with a page number agree {how}.",
    "detect_how_text": "(from the PDF text layer)",
    "detect_how_ocr": "(using Windows OCR)",
    "detect_evidence": "    PDF page {pdf} = printed page {page}",
    "detect_applied": "Set the offset to {offset}. Check one or two entries with Preview.",
    "detect_kept": "The TOC says offset={current} but {found} was detected. The TOC value was kept. Press [Auto-detect] to use the detected value.",
    "detect_fail_title": "Could not detect the offset",
    "detect_fail_no_numbers": "No page numbers were found. The book may have no page numbers, or the print may be too faint.",
    "detect_fail_inconsistent": "The page-number candidates do not agree ({votes}/{pages} pages). The scan may have two book pages per sheet, or irregular numbering.",
    "detect_fail_ocr_unavailable": "This PDF has no text layer and Windows OCR is not available on this computer.",
    "detect_fail_no_pages": "The PDF has no pages to examine.",
    "detect_fail_hint": "Find which PDF page holds book page 1 in a PDF viewer and enter the offset yourself.",
    "detect_cancelled": "Offset auto-detect was cancelled.",
    "detect_error": "Auto-detect failed: {err}",
    "cli_auto_offset": "detect the offset from the page numbers in the scan (ignored when --offset is given)",
    "cli_detect_differs": "Using the detected offset {found} instead of offset={file} from the TOC file.",
    "read_err": "Cannot read the TOC file: {path}\n      ({err})",
    "empty_file": "The TOC file is empty: {name}",
    "decode_fail": "Could not decode the TOC file as '{enc}': {err}",
    "toc_is_pdf": "'{name}' is a PDF. Please provide a plain-text (.txt) file as the table of contents.",
    "toc_is_binary": "'{name}' does not look like a text file (image, Word document, archive, ...).\n      Please provide a plain .txt file, e.g. one made with Notepad.",
    "unknown_encoding": "Cannot detect the encoding of '{name}'.\n      Try 'Save As' in Notepad and choose UTF-8.",
    "line_fmt": "Line {n}: {reason}\n      → {raw}",
    "hint_fmt": "\n      ※ {hint}",
    "offset_not_int": "The offset value is not an integer.",
    "offset_hint": "e.g. offset=8",
    "range_warn": "Line {n} '{title}': page given as a range {a}-{b}; using the first number {page}.",
    "roman_reason": "Roman-numeral page numbers ('{roman}') are not supported.",
    "roman_hint": "Look up the actual page number in a PDF viewer and write it in Arabic digits, or remove this line",
    "no_page": "No page number found at the end of the line.",
    "example_hint": "e.g.  Chapter 1 Introduction, 12",
    "no_title": "Missing title (the line contains only a number).",
    "page_lt_1": "Page numbers must be 1 or greater.",
    "commented_entry": "Line {n} starts with # and was skipped as a comment: {text}",
    "multi_offset": "There are {k} offset lines (lines {lines}). Using the last value, {value}.",
    "parse_head": "{n} line(s) in the table of contents could not be read.",
    "only_first": " (showing the first {m})",
    "no_entries": "No table-of-contents entries found.\n      The file is empty, or every line is a comment (#) or an offset line.\n      {example}",
    "val_too_big": "Line {n} '{title}': page {page} + offset {offset} = PDF page {pdf} → the PDF only has {total} pages.",
    "val_too_small": "Line {n} '{title}': page {page} + offset {offset} = PDF page {pdf} → before page 1.",
    "val_backwards": "Line {n} '{title}' (p.{page}) comes before the previous entry '{prev}' (p.{prevpage}). Check for a typo.",
    "val_head": "{n} entries fall outside the PDF page range (1–{total}).",
    "val_all_big": "\n      Every entry is past the last page. The offset ({offset}) may be too large, or this may be the wrong PDF.",
    "val_all_small": "\n      Every entry is before page 1. The offset ({offset}) is too small.",
    "val_max_hint": "\n      The largest page number is on line {n} '{title}': {page}. Check the offset or that line.",
    "tree_line": "(printed p.{page} -> PDF page {pdf})",
    "pdf_missing": "PDF file not found: {path}",
    "pdf_read_err": "Cannot read the PDF file: {path}\n      ({err})",
    "pdf_empty": "'{name}' is an empty file.",
    "pdf_not_pdf": "'{name}' is not a PDF (no %PDF marker at the start of the file).\n      It may be a renamed file or a damaged one.",
    "pdf_corrupt": "Could not read '{name}'. The file may be damaged.\n      ({err})",
    "pdf_encrypted_unsupported": "'{name}' is an encrypted PDF. Remove the password first.\n      ({err})",
    "pdf_encrypted": "'{name}' needs a password to open. Remove the password first.",
    "pdf_count_fail": "Cannot count the pages of '{name}'. The file may be damaged.\n      ({err})",
    "pdf_zero_pages": "'{name}' has no pages.",
    "out_dir_missing": "The output folder does not exist: {dir}",
    "out_locked": "Cannot write the output file: {path}\n      If it is open in another program (e.g. a PDF viewer), close it and try again.",
    "out_write_fail": "Failed to write the output file: {path}\n      ({err})",
    "cli_desc": "Add bookmarks to a PDF from a plain-text table of contents.",
    "cli_pdf": "source PDF",
    "cli_toc": "TOC text file",
    "cli_out": "output PDF (default: <name>_toc.pdf)",
    "cli_offset": "PDF page = printed page + offset. E.g. if book page 1 is PDF page 9, use --offset 8. Overrides an offset= line in the TOC file.",
    "cli_encoding": "TOC file encoding (default: auto-detect)",
    "cli_keep": "keep existing bookmarks and append instead of replacing",
    "cli_dry": "parse and report only; do not write a PDF",
    "cli_lang": "display language: ko, en, zh, ja (default: auto)",
    "cli_epilog": (
        "TOC file format (one entry per line):\n"
        "    Chapter 1 Introduction, 12\n"
        "    Chapter 2 Background, 25\n"
        "      2.1 History, 26         <- indent for sub-entries\n"
        "      2.2 Today, 31\n"
        "    Chapter 3 Conclusion p.40\n\n"
        "    Lines starting with # are comments. Blank lines are ignored.\n"
        "    offset=8                <- difference between printed and PDF page numbers (optional)"
    ),
    "cli_toc_missing": "TOC file not found: {path}",
    "cli_error": "Error: ",
    "cli_warn": "Warning: ",
    "cli_summary": "PDF: {pdf}  ({total} pages)   offset: {offset:+d}   entries: {n}",
    "cli_dry_note": "\n(dry-run) No PDF was written.",
    "cli_same": "The output file is the same as the source. Use -o to choose another name.",
    "cli_done": "\nDone: {path}",
    "app_title": "PDF TOC Bookmarks",
    "app_subtitle": "Add bookmarks to a scanned book PDF so you can jump straight to any chapter.",
    "lbl_language": "Language",
    "sec_pdf": "PDF",
    "sec_pdf_hint_dnd": "drag & drop or browse",
    "sec_pdf_hint_nodnd": "choose with Browse",
    "pdf_drop_hint": "Drop a PDF file here",
    "pdf_click_hint": "Click to choose a PDF",
    "pdf_pages": "{name}\n{n} pages",
    "btn_browse": "Browse…",
    "sec_toc": "Table of contents",
    "sec_toc_hint": "one per line:  Chapter 1 Title, 12   ·   indent for sub-entries",
    "btn_open_txt": "Open text file…",
    "btn_example": "Fill example",
    "btn_clear": "Clear",
    "toc_drop_hint": "You can also drop a text file on the window",
    "sec_settings": "Settings",
    "lbl_offset": "Page offset",
    "offset_hint": "if book page 1 is PDF page 9, enter 8",
    "lbl_output": "Output file",
    "btn_change": "Change…",
    "btn_preview": "Preview",
    "btn_build": "Create PDF",
    "sec_result": "Result",
    "sec_result_hint": "Preview or Create PDF output appears here",
    "dlg_pdf": "Select the source PDF",
    "dlg_toc": "Select the TOC text file",
    "dlg_out": "Output PDF",
    "ft_all": "All files",
    "ft_text": "Text",
    "log_pdf": "PDF: {path}  ({n} pages)",
    "warn_few_pages": "Only {n} pages. Make sure this is the whole book.",
    "warn_multi_pdf": "{n} PDFs were dropped. Using only the first ({name}); one book at a time.",
    "err_is_dir": "'{name}' is a folder. Drop a PDF or a TOC text file.",
    "err_not_found": "'{path}' was not found.",
    "err_pdf_open": "Cannot open the PDF",
    "err_toc_read": "Cannot read the TOC file",
    "warn_not_txt": "'{name}' is not a .txt file but was read as text. Check the content if it looks wrong.",
    "log_toc": "TOC file: {path}",
    "warn_toc_format": "The table of contents has format problems. Press [Preview] to see which lines.",
    "log_offset_applied": "Applied offset={n} from the file.",
    "err_no_pdf": "No PDF",
    "err_no_pdf_detail": "Drop a PDF into box 1 or use [Browse…].",
    "err_toc_empty": "The table of contents is empty",
    "err_toc_empty_detail": "Type the TOC into box 2 or open a text file. [Fill example] shows the format.",
    "err_toc_format": "TOC format error",
    "err_offset": "Offset error",
    "err_offset_detail": "'{v}' is not an integer. e.g. 0, 8, -2",
    "err_range": "Pages outside the PDF range",
    "summary": "{n} entries  ·  offset {offset:+d}  ·  PDF {total} pages",
    "tree_gui": "{title}  ->  PDF page {pdf}",
    "err_same": "The output file is the same as the source",
    "err_same_detail": "Choose a different name so the source is not overwritten. Press [Change…].",
    "dlg_overwrite_title": "Overwrite",
    "dlg_overwrite": "{name} already exists. Overwrite it?",
    "log_cancelled": "Cancelled.",
    "err_build": "Could not create the PDF",
    "err_unexpected": "Unexpected error",
    "log_done": "Done: {path}",
    "dlg_done_title": "Done",
    "dlg_done": "Bookmarks added.\n\n{path}",
    "example_toc": (
        "# One entry per line: title, page\n"
        "# Indent for sub-entries\n"
        "offset=0\n\n"
        "Preface, 1\n"
        "Chapter 1 Introduction, 2\n"
        "    1.1 Background, 3\n"
        "    1.2 Goals, 4\n"
        "Chapter 2 Body, 5\n"
        "    2.1 Method, 6\n"
        "    2.2 Results, 8\n"
        "Chapter 3 Conclusion, 9\n"
    ),
}

STRINGS["zh"] = {
    # ---- 새 버전 확인
    "opt_update_check": "检查新版本",
    "update_available": "有新版本 {latest}（当前 {current}）",
    "btn_update": "更新",
    "btn_later": "以后",
    # ---- 의견 보내기
    "btn_feedback": "发送反馈",
    "feedback_failed": "无法打开浏览器。请复制下面的地址并粘贴到浏览器地址栏，无需登录即可发送反馈。",
    "feedback_tip": "告诉我们问题或建议（将打开浏览器）",
    # ---- offset 자동 감지
    "btn_detect": "自动检测",
    "detect_start": "自动检测 offset：从正文中选取 {n} 页查找页码。",
    "detect_progress": "正在查找页码… {i}/{n}",
    "detect_ok": "检测到 offset {offset:+d}。在找到页码的 {pages} 页中，有 {votes} 页指向同一个值{how}。",
    "detect_how_text": "（使用 PDF 文字层）",
    "detect_how_ocr": "（使用 Windows OCR）",
    "detect_evidence": "    PDF 第 {pdf} 页 = 印刷页 {page}",
    "detect_applied": "已将 offset 设为 {offset}。请用“预览”核对一两项。",
    "detect_kept": "目录中的 offset={current} 与检测值 {found} 不同，已保留目录中的值。若要使用检测值，请点击“自动检测”。",
    "detect_fail_title": "无法自动检测 offset",
    "detect_fail_no_numbers": "没有找到像页码的数字。这本书可能没有页码，或者字迹太淡。",
    "detect_fail_inconsistent": "页码候选互相不一致（{votes}/{pages} 页一致）。可能是一张扫描了两页，或页码不规则。",
    "detect_fail_ocr_unavailable": "此 PDF 没有文字层，且这台电脑无法使用 Windows OCR。",
    "detect_fail_no_pages": "PDF 中没有可检查的页面。",
    "detect_fail_hint": "请在 PDF 阅读器中查看书的第 1 页位于 PDF 第几页，并手动输入 offset。",
    "detect_cancelled": "已取消自动检测 offset。",
    "detect_error": "自动检测出错：{err}",
    "cli_auto_offset": "读取扫描图像中的页码自动检测 offset（指定 --offset 时忽略）",
    "cli_detect_differs": "使用自动检测的 {found}，而不是目录文件中的 offset={file}。",
    "read_err": "无法读取目录文件：{path}\n      （{err}）",
    "empty_file": "目录文件为空：{name}",
    "decode_fail": "无法以“{enc}”编码读取目录文件：{err}",
    "toc_is_pdf": "“{name}”是 PDF 文件。目录处请提供文本（.txt）文件。",
    "toc_is_binary": "“{name}”似乎不是文本文件（图片、Word 文档、压缩包等）。\n      请提供用记事本创建的 .txt 文件。",
    "unknown_encoding": "无法识别“{name}”的编码。\n      请在记事本中“另存为”并选择 UTF-8 编码。",
    "line_fmt": "第 {n} 行：{reason}\n      → {raw}",
    "hint_fmt": "\n      ※ {hint}",
    "offset_not_int": "offset 的值不是整数。",
    "offset_hint": "例：offset=8",
    "range_warn": "第 {n} 行“{title}”：页码写成了范围 {a}-{b}，已使用前一个数字 {page}。",
    "roman_reason": "不支持罗马数字页码（“{roman}”）。",
    "roman_hint": "请在 PDF 阅读器中查看实际页码并改为阿拉伯数字，或删除此行",
    "no_page": "在行尾未找到页码。",
    "example_hint": "例：第1章 绪论, 12",
    "no_title": "缺少标题（该行只有数字）。",
    "page_lt_1": "页码必须大于等于 1。",
    "commented_entry": "第 {n} 行以 # 开头，已作为注释跳过：{text}",
    "multi_offset": "有 {k} 行 offset（第 {lines} 行）。使用最后一个值 {value}。",
    "parse_head": "目录中有 {n} 行无法识别。",
    "only_first": "（仅显示前 {m} 个）",
    "no_entries": "没有找到任何目录条目。\n      文件为空，或所有行都是注释（#）或 offset 行。\n      {example}",
    "val_too_big": "第 {n} 行“{title}”：第 {page} 页 + offset {offset} = PDF 第 {pdf} 页 → PDF 只有 {total} 页。",
    "val_too_small": "第 {n} 行“{title}”：第 {page} 页 + offset {offset} = PDF 第 {pdf} 页 → 在第 1 页之前。",
    "val_backwards": "第 {n} 行“{title}”（第 {page} 页）在前一项“{prev}”（第 {prevpage} 页）之前。请检查是否有笔误。",
    "val_head": "有 {n} 项超出 PDF 页码范围（1～{total}）。",
    "val_all_big": "\n      所有项都超出末页。offset（{offset}）可能过大，或 PDF 文件不对。",
    "val_all_small": "\n      所有项都在第 1 页之前。offset（{offset}）过小。",
    "val_max_hint": "\n      最大页码在第 {n} 行“{title}”：第 {page} 页。请检查 offset 或该行页码。",
    "tree_line": "（印刷页 {page} -> PDF 第 {pdf} 页）",
    "pdf_missing": "找不到 PDF 文件：{path}",
    "pdf_read_err": "无法读取 PDF 文件：{path}\n      （{err}）",
    "pdf_empty": "“{name}”是空文件。",
    "pdf_not_pdf": "“{name}”不是 PDF 文件（文件开头没有 %PDF 标记）。\n      可能只是改了扩展名，或文件已损坏。",
    "pdf_corrupt": "无法读取“{name}”。文件可能已损坏。\n      （{err}）",
    "pdf_encrypted_unsupported": "“{name}”是加密的 PDF。请先解除密码。\n      （{err}）",
    "pdf_encrypted": "“{name}”需要打开密码。请先解除密码。",
    "pdf_count_fail": "无法统计“{name}”的页数。文件可能已损坏。\n      （{err}）",
    "pdf_zero_pages": "“{name}”没有页面。",
    "out_dir_missing": "输出文件夹不存在：{dir}",
    "out_locked": "无法写入输出文件：{path}\n      如果该文件已在其他程序（如 PDF 阅读器）中打开，请关闭后重试。",
    "out_write_fail": "写入输出文件失败：{path}\n      （{err}）",
    "cli_desc": "根据文本目录文件为 PDF 添加书签。",
    "cli_pdf": "原始 PDF",
    "cli_toc": "目录文本文件",
    "cli_out": "输出 PDF（默认：原文件名_toc.pdf）",
    "cli_offset": "PDF 页 = 印刷页 + offset。例如书的第 1 页是 PDF 第 9 页，则 --offset 8。优先于目录文件中的 offset= 行。",
    "cli_encoding": "目录文件编码（默认：自动识别）",
    "cli_keep": "保留 PDF 已有书签并追加，而不是替换",
    "cli_dry": "只解析并显示结果，不写入 PDF",
    "cli_lang": "显示语言：ko、en、zh、ja（默认：自动）",
    "cli_epilog": (
        "目录文件格式（每行一项）：\n"
        "    第1章 绪论, 12\n"
        "    第2章 背景, 25\n"
        "      2.1 历史, 26            <- 缩进表示子项\n"
        "      2.2 现状, 31\n"
        "    第3章 结论 第40页\n\n"
        "    以 # 开头的行是注释，空行忽略。\n"
        "    offset=8                <- 印刷页码与 PDF 页码之差（可选）"
    ),
    "cli_toc_missing": "找不到目录文件：{path}",
    "cli_error": "错误：",
    "cli_warn": "警告：",
    "cli_summary": "PDF：{pdf}（{total} 页）   offset：{offset:+d}   条目：{n}",
    "cli_dry_note": "\n（dry-run）未写入 PDF。",
    "cli_same": "输出文件与原文件相同。请用 -o 指定其他文件名。",
    "cli_done": "\n完成：{path}",
    "app_title": "PDF 目录书签",
    "app_subtitle": "为扫描的图书 PDF 添加书签，可直接跳转到任意章节。",
    "lbl_language": "语言",
    "sec_pdf": "PDF",
    "sec_pdf_hint_dnd": "拖放或浏览",
    "sec_pdf_hint_nodnd": "点击浏览选择",
    "pdf_drop_hint": "将 PDF 文件拖到此处",
    "pdf_click_hint": "点击选择 PDF",
    "pdf_pages": "{name}\n{n} 页",
    "btn_browse": "浏览…",
    "sec_toc": "目录",
    "sec_toc_hint": "每行一项：第1章 标题, 12   ·   缩进表示子项",
    "btn_open_txt": "打开文本文件…",
    "btn_example": "填入示例",
    "btn_clear": "清空",
    "toc_drop_hint": "也可以将文本文件拖到窗口中",
    "sec_settings": "设置",
    "lbl_offset": "页码偏移 (offset)",
    "offset_hint": "若书的第 1 页是 PDF 第 9 页，填 8",
    "lbl_output": "输出文件",
    "btn_change": "更改…",
    "btn_preview": "预览",
    "btn_build": "生成 PDF",
    "sec_result": "结果",
    "sec_result_hint": "点击“预览”或“生成 PDF”后在此显示",
    "dlg_pdf": "选择原始 PDF",
    "dlg_toc": "选择目录文本文件",
    "dlg_out": "输出 PDF",
    "ft_all": "所有文件",
    "ft_text": "文本",
    "log_pdf": "PDF：{path}（{n} 页）",
    "warn_few_pages": "只有 {n} 页。请确认这是整本书的 PDF。",
    "warn_multi_pdf": "拖入了 {n} 个 PDF。只使用第一个（{name}），一次处理一本。",
    "err_is_dir": "“{name}”是文件夹。请拖入 PDF 或目录文本文件。",
    "err_not_found": "找不到“{path}”。",
    "err_pdf_open": "无法打开 PDF",
    "err_toc_read": "无法读取目录文件",
    "warn_not_txt": "“{name}”不是 .txt，但已按文本读取。若内容异常请检查。",
    "log_toc": "目录文件：{path}",
    "warn_toc_format": "目录格式有问题。点击“预览”可查看是哪些行。",
    "log_offset_applied": "已应用文件中的 offset={n}。",
    "err_no_pdf": "没有 PDF",
    "err_no_pdf_detail": "请将 PDF 拖入第 1 栏，或点击“浏览…”。",
    "err_toc_empty": "目录为空",
    "err_toc_empty_detail": "请在第 2 栏输入目录或打开文本文件。点击“填入示例”可查看格式。",
    "err_toc_format": "目录格式错误",
    "err_offset": "offset 错误",
    "err_offset_detail": "“{v}”不是整数。例：0、8、-2",
    "err_range": "页码超出 PDF 范围",
    "summary": "{n} 项  ·  offset {offset:+d}  ·  PDF {total} 页",
    "tree_gui": "{title}  ->  PDF 第 {pdf} 页",
    "err_same": "输出文件与原文件相同",
    "err_same_detail": "请指定其他文件名以免覆盖原文件。点击“更改…”。",
    "dlg_overwrite_title": "覆盖",
    "dlg_overwrite": "{name} 已存在。要覆盖吗？",
    "log_cancelled": "已取消。",
    "err_build": "无法生成 PDF",
    "err_unexpected": "意外错误",
    "log_done": "完成：{path}",
    "dlg_done_title": "完成",
    "dlg_done": "已添加书签。\n\n{path}",
    "example_toc": (
        "# 每行一项：标题, 页码\n"
        "# 缩进表示子项\n"
        "offset=0\n\n"
        "前言, 1\n"
        "第1章 绪论, 2\n"
        "    1.1 背景, 3\n"
        "    1.2 目的, 4\n"
        "第2章 正文, 5\n"
        "    2.1 方法, 6\n"
        "    2.2 结果, 8\n"
        "第3章 结论, 9\n"
    ),
}

STRINGS["ja"] = {
    # ---- 새 버전 확인
    "opt_update_check": "新しいバージョンを確認",
    "update_available": "新しいバージョン {latest} が出ています（現在 {current}）",
    "btn_update": "更新",
    "btn_later": "後で",
    # ---- 의견 보내기
    "btn_feedback": "ご意見を送る",
    "feedback_failed": "ブラウザーを開けませんでした。下のアドレスをコピーしてブラウザーのアドレス欄に貼り付けると、ログインなしでご意見を送れます。",
    "feedback_tip": "不具合・ご要望をお知らせください（ブラウザが開きます）",
    # ---- offset 자동 감지
    "btn_detect": "自動検出",
    "detect_start": "offset の自動検出: 本文から {n} ページを選んでページ番号を探します。",
    "detect_progress": "ページ番号を探しています… {i}/{n}",
    "detect_ok": "offset {offset:+d} が見つかりました。ページ番号が読めた {pages} ページのうち {votes} ページが同じ値を示しています{how}。",
    "detect_how_text": "（PDF のテキスト層を使用）",
    "detect_how_ocr": "（Windows OCR を使用）",
    "detect_evidence": "    PDF {pdf} ページ目 = 本の {page} ページ",
    "detect_applied": "offset 欄に {offset} を入れました。プレビューで 1～2 項目を確かめてください。",
    "detect_kept": "目次の offset={current} と検出値 {found} が違います。目次の値をそのまま使います。検出値を使うには［自動検出］を押してください。",
    "detect_fail_title": "offset を自動で見つけられませんでした",
    "detect_fail_no_numbers": "ページ番号らしい数字が見つかりませんでした。ページ番号のない本か、文字が薄すぎる可能性があります。",
    "detect_fail_inconsistent": "ページ番号の候補が互いに合いません（{votes}/{pages} ページが一致）。見開きを 1 枚でスキャンしたか、ページ番号が不規則な可能性があります。",
    "detect_fail_ocr_unavailable": "この PDF にはテキスト層がなく、このパソコンでは Windows OCR を使えません。",
    "detect_fail_no_pages": "PDF に調べられるページがありません。",
    "detect_fail_hint": "PDF ビューアーで本の 1 ページ目が PDF の何ページ目かを確かめ、offset を直接入力してください。",
    "detect_cancelled": "offset の自動検出を取り消しました。",
    "detect_error": "自動検出中にエラーが起きました: {err}",
    "cli_auto_offset": "スキャン画像のページ番号を読んで offset を自動で求める（--offset を指定すると無視）",
    "cli_detect_differs": "目次ファイルの offset={file} の代わりに、自動検出した {found} を使います。",
    # ---- 목차 파일 읽기
    "read_err": "目次ファイルを読み込めません: {path}\n      （{err}）",
    "empty_file": "目次ファイルが空です: {name}",
    "decode_fail": "目次ファイルを「{enc}」エンコーディングで読み込めませんでした: {err}",
    "toc_is_pdf": "「{name}」は PDF ファイルです。目次にはテキスト（.txt）ファイルを指定してください。",
    "toc_is_binary": "「{name}」はテキストファイルではないようです（画像、Word 文書、圧縮ファイルなど）。\n      メモ帳で作った .txt ファイルを指定してください。",
    "unknown_encoding": "「{name}」のエンコーディングがわかりません。\n      メモ帳の「名前を付けて保存」で、エンコードを UTF-8 にして保存し直してください。",
    # ---- 파싱
    "line_fmt": "{n} 行目: {reason}\n      → {raw}",
    "hint_fmt": "\n      ※ {hint}",
    "offset_not_int": "offset の値が整数ではありません。",
    "offset_hint": "例）offset=8",
    "range_warn": "{n} 行目「{title}」: ページが {a}-{b} の範囲で書かれているため、前の数字 {page} を使いました。",
    "roman_reason": "ローマ数字のページ番号（「{roman}」）には対応していません。",
    "roman_hint": "PDF ビューアーで実際のページ番号を確かめてアラビア数字で書くか、この行を削除してください",
    "no_page": "行末にページ番号が見つかりません。",
    "example_hint": "例）第1章 序論, 12",
    "no_title": "タイトルがありません（数字だけの行です）。",
    "page_lt_1": "ページ番号は 1 以上にしてください。",
    "commented_entry": "{n} 行目は # で始まるため、コメントとして読み飛ばしました: {text}",
    "multi_offset": "offset の行が {k} 個あります（{lines} 行目）。最後の値 {value} を使います。",
    "parse_head": "目次のうち {n} 行を読み取れませんでした。",
    "only_first": "（最初の {m} 件のみ表示）",
    "no_entries": "目次の項目が一つもありません。\n      ファイルが空か、すべての行がコメント（#）か offset 行です。\n      {example}",
    # ---- 검증
    "val_too_big": "{n} 行目「{title}」: {page} ページ + offset {offset} = PDF {pdf} ページ目 → PDF は {total} ページまでです。",
    "val_too_small": "{n} 行目「{title}」: {page} ページ + offset {offset} = PDF {pdf} ページ目 → 1 ページ目より前です。",
    "val_backwards": "{n} 行目「{title}」（{page} ページ）が前の項目「{prev}」（{prevpage} ページ）より前にあります。書き間違いがないか確かめてください。",
    "val_head": "{n} 個の項目が PDF のページ範囲（1～{total}）から外れています。",
    "val_all_big": "\n      すべての項目が最終ページを超えています。offset（{offset}）が大きすぎるか、別の PDF の可能性があります。",
    "val_all_small": "\n      すべての項目が 1 ページ目より前です。offset（{offset}）が小さすぎます。",
    "val_max_hint": "\n      最大のページ番号は {n} 行目「{title}」の {page} ページです。offset かこの行のページ番号を確かめてください。",
    "tree_line": "（本の {page} ページ -> PDF {pdf} ページ目）",
    # ---- PDF
    "pdf_missing": "PDF ファイルがありません: {path}",
    "pdf_read_err": "PDF ファイルを読み込めません: {path}\n      （{err}）",
    "pdf_empty": "「{name}」は空のファイルです。",
    "pdf_not_pdf": "「{name}」は PDF ファイルではありません（ファイルの先頭に %PDF の印がありません）。\n      拡張子だけ .pdf に変えたファイルか、壊れたファイルの可能性があります。",
    "pdf_corrupt": "「{name}」を読み込めませんでした。ファイルが壊れている可能性があります。\n      （{err}）",
    "pdf_encrypted_unsupported": "「{name}」は暗号化された PDF です。先にパスワードを解除してからお使いください。\n      （{err}）",
    "pdf_encrypted": "「{name}」は開くのにパスワードが必要な PDF です。先にパスワードを解除してからお使いください。",
    "pdf_count_fail": "「{name}」のページ数を数えられません。ファイルが壊れている可能性があります。\n      （{err}）",
    "pdf_zero_pages": "「{name}」にはページがありません。",
    "out_dir_missing": "出力先のフォルダーがありません: {dir}",
    "out_locked": "出力ファイルに書き込めません: {path}\n      PDF ビューアーなど別のプログラムで開いている場合は、閉じてからやり直してください。",
    "out_write_fail": "出力ファイルを書き込めませんでした: {path}\n      （{err}）",
    # ---- CLI
    "cli_desc": "テキストの目次ファイルから PDF にしおりを入れます。",
    "cli_pdf": "元の PDF",
    "cli_toc": "目次のテキストファイル",
    "cli_out": "出力 PDF（既定: 元の名前_toc.pdf）",
    "cli_offset": "PDF のページ = 本のページ + offset。例: 本の 1 ページ目が PDF の 9 ページ目なら --offset 8。目次ファイル内の offset= 行より優先します。",
    "cli_encoding": "目次ファイルのエンコーディング（既定: 自動判別）",
    "cli_keep": "PDF にもとからあるしおりを消さずに、後ろに追加する",
    "cli_dry": "PDF を書き出さず、読み取り結果だけを表示する",
    "cli_lang": "表示言語: ko, en, zh, ja（既定: 自動）",
    "cli_epilog": (
        "目次ファイルの書き方（1 行に 1 項目）:\n"
        "    第1章 序論, 12\n"
        "    第2章 背景, 25\n"
        "      2.1 歴史, 26           <- 字下げすると下位の項目\n"
        "      2.2 現状, 31\n"
        "    第3章 結論 p.40\n\n"
        "    # で始まる行はコメント。空行は無視します。\n"
        "    offset=8                <- 本のページ番号と PDF のページ番号の差（省略可）"
    ),
    "cli_toc_missing": "目次ファイルがありません: {path}",
    "cli_error": "エラー: ",
    "cli_warn": "警告: ",
    "cli_summary": "PDF: {pdf}  （{total} ページ）   offset: {offset:+d}   項目: {n} 個",
    "cli_dry_note": "\n（dry-run）PDF は書き出していません。",
    "cli_same": "出力ファイルが元のファイルと同じです。-o で別の名前を指定してください。",
    "cli_done": "\n完了: {path}",
    # ---- GUI
    "app_title": "PDF 目次しおり",
    "app_subtitle": "スキャンした本の PDF にしおりを入れて、読みたい章へすぐ移動できるようにします。",
    "lbl_language": "言語",
    "sec_pdf": "PDF",
    "sec_pdf_hint_dnd": "ドラッグ＆ドロップまたは参照",
    "sec_pdf_hint_nodnd": "［参照］で選択",
    "pdf_drop_hint": "PDF ファイルをここにドロップしてください",
    "pdf_click_hint": "クリックして PDF を選んでください",
    "pdf_pages": "{name}\n{n} ページ",
    "btn_browse": "参照…",
    "sec_toc": "目次",
    "sec_toc_hint": "1 行に 1 項目:  第1章 タイトル, 12   ·   字下げで下位の項目",
    "btn_open_txt": "テキストファイルを開く…",
    "btn_example": "例を入れる",
    "btn_clear": "消去",
    "toc_drop_hint": "テキストファイルをドロップしても開けます",
    "sec_settings": "設定",
    "lbl_offset": "ページのずれ (offset)",
    "offset_hint": "本の 1 ページ目が PDF の 9 ページ目なら 8",
    "lbl_output": "出力ファイル",
    "btn_change": "変更…",
    "btn_preview": "プレビュー",
    "btn_build": "PDF を作成",
    "sec_result": "結果",
    "sec_result_hint": "［プレビュー］か［PDF を作成］を押すとここに表示されます",
    "dlg_pdf": "元の PDF を選択",
    "dlg_toc": "目次のテキストファイルを選択",
    "dlg_out": "出力 PDF",
    "ft_all": "すべてのファイル",
    "ft_text": "テキスト",
    "log_pdf": "PDF: {path}  （{n} ページ）",
    "warn_few_pages": "ページが {n} ページしかありません。本全体の PDF か確かめてください。",
    "warn_multi_pdf": "PDF を {n} 個ドロップしました。最初の 1 個（{name}）だけを使い、残りは無視します。一度に 1 冊ずつ処理します。",
    "err_is_dir": "「{name}」はフォルダーです。PDF ファイルか目次のテキストファイルをドロップしてください。",
    "err_not_found": "「{path}」が見つかりません。",
    "err_pdf_open": "PDF を開けません",
    "err_toc_read": "目次ファイルを読み込めません",
    "warn_not_txt": "「{name}」は .txt ではありませんが、テキストとして読み込みました。内容がおかしければ確かめてください。",
    "log_toc": "目次ファイル: {path}",
    "warn_toc_format": "目次の書き方に問題があります。［プレビュー］を押すと、どの行が問題か確かめられます。",
    "log_offset_applied": "ファイル内の offset={n} を適用しました。",
    "err_no_pdf": "PDF がありません",
    "err_no_pdf_detail": "1 番の欄に PDF をドロップするか、［参照…］で選んでください。",
    "err_toc_empty": "目次が空です",
    "err_toc_empty_detail": "2 番の欄に目次を入力するか、テキストファイルを開いてください。［例を入れる］で書き方を確かめられます。",
    "err_toc_format": "目次の書き方のエラー",
    "err_offset": "offset のエラー",
    "err_offset_detail": "「{v}」は整数ではありません。例）0、8、-2",
    "err_range": "ページ番号が PDF の範囲を外れています",
    "summary": "項目 {n} 個  ·  offset {offset:+d}  ·  PDF {total} ページ",
    "tree_gui": "{title}  ->  PDF {pdf} ページ目",
    "err_same": "出力ファイルが元のファイルと同じです",
    "err_same_detail": "元のファイルを上書きしないよう、別の名前を指定してください。［変更…］を押してください。",
    "dlg_overwrite_title": "上書き",
    "dlg_overwrite": "{name} はすでにあります。上書きしますか？",
    "log_cancelled": "取り消しました。",
    "err_build": "PDF を作成できませんでした",
    "err_unexpected": "予期しないエラー",
    "log_done": "完了: {path}",
    "dlg_done_title": "完了",
    "dlg_done": "しおりを入れました。\n\n{path}",
    "example_toc": (
        "# 1 行に 1 項目: タイトル, ページ\n"
        "# 字下げすると下位の項目\n"
        "offset=0\n\n"
        "はじめに, 1\n"
        "第1章 序論, 2\n"
        "    1.1 背景, 3\n"
        "    1.2 目的, 4\n"
        "第2章 本論, 5\n"
        "    2.1 方法, 6\n"
        "    2.2 結果, 8\n"
        "第3章 結論, 9\n"
    ),
}

set_lang(detect_lang())

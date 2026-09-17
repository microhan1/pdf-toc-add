"""i18n.py - 한국어 / English / 中文 메시지 모음.

사용:  from i18n import tr, set_lang
       tr("btn_browse")            -> 현재 언어의 문자열
       tr("log_pdf", path=..., n=3) -> 자리표시자 채움
"""

from __future__ import annotations

import json
import os
from pathlib import Path

LANGS = ("ko", "en", "zh")
LANG_NAMES = {"ko": "한국어", "en": "English", "zh": "中文"}
_lang = "en"


# ---------------------------------------------------------------- 언어 선택 / 저장

def config_path() -> Path:
    base = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home())
    return Path(base) / "pdf_toc_add" / "config.json"


def load_saved_lang() -> str | None:
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
        lang = data.get("lang")
        return lang if lang in LANGS else None
    except (OSError, ValueError, AttributeError):
        return None


def save_lang(lang: str) -> None:
    try:
        p = config_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"lang": lang}), encoding="utf-8")
    except OSError:
        pass  # 저장 실패는 치명적이지 않음


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
        return {0x12: "ko", 0x04: "zh", 0x09: "en"}.get(langid, "en")
    except Exception:
        pass
    try:
        import locale
        loc = (locale.getlocale()[0] or os.environ.get("LANG", "")).lower()
        if loc.startswith(("ko", "korean")):
            return "ko"
        if loc.startswith(("zh", "chinese")):
            return "zh"
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
    "cli_lang": "표시 언어: ko, en, zh (기본: 자동)",
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
    "cli_lang": "display language: ko, en, zh (default: auto)",
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
    "toc_drop_hint": "You can also drop a text file onto the window",
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
    "cli_lang": "显示语言：ko、en、zh（默认：自动）",
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

set_lang(detect_lang())

#!/usr/bin/env python3
"""pdf_toc_add.py - 텍스트 목차 파일을 읽어 PDF에 북마크(아웃라인)를 넣는 툴.
Add bookmarks to a PDF from a plain-text table of contents.  根据文本目录为 PDF 添加书签。

    python pdf_toc_add.py book.pdf toc.txt [-o out.pdf] [--offset 8] [--dry-run] [--lang ko|en|zh]
    python pdf_toc_add.py                      (no arguments: GUI)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:  # pragma: no cover
    sys.exit("pypdf is required:  pip install pypdf")

from i18n import LANGS, set_lang, tr


# ---------------------------------------------------------------- 오류 타입

class ToolError(Exception):
    """사용자에게 그대로 보여줄 수 있는 오류 메시지. lines: 관련된 목차 행 번호."""

    def __init__(self, message: str, lines: list[int] | None = None):
        super().__init__(message)
        self.lines: list[int] = lines or []


class TocParseError(ToolError):
    """목차 텍스트 파일 문제."""


class PdfError(ToolError):
    """PDF 파일 문제."""


class LineMsg(str):
    """행 번호가 붙은 경고 문자열 (str 처럼 쓰되 .lineno 로 줄을 알 수 있음)."""

    lineno: int | None

    def __new__(cls, text: str, lineno: int | None = None):
        obj = super().__new__(cls, text)
        obj.lineno = lineno
        return obj


MAX_REPORTED = 20  # 오류 줄이 아주 많을 때 보여줄 최대 개수


# ---------------------------------------------------------------- 파싱

_SEP = r"[\s,，、:：\.·…\-–—~〜]*"
_PREFIX = r"(?:p\.?|pp\.?|page|第)?\s*"
_SUFFIX = r"\s*(?:쪽|페이지|p|page|面|页|頁)?\.?\s*"

# "제목, 12쪽" / "Title p.12" / "标题 第12页" / "제목 ... 12"
_LINE_RE = re.compile(
    rf"^(?P<title>.*?){_SEP}{_PREFIX}(?P<page>\d+){_SUFFIX}$",
    re.IGNORECASE,
)
# "제목, 12-15" 처럼 범위로 적은 경우: 앞 숫자를 쓴다
_RANGE_RE = re.compile(
    rf"^(?P<title>.*?){_SEP}{_PREFIX}(?P<a>\d+)\s*[-–—~〜]\s*(?P<b>\d+){_SUFFIX}$",
    re.IGNORECASE,
)
# "머리말 ...... iii" 로마 숫자 쪽수
_ROMAN_RE = re.compile(rf"^(?P<title>.+?){_SEP}(?P<roman>[ivxlcdm]+)\.?\s*$", re.IGNORECASE)
_OFFSET_RE = re.compile(r"^\s*offset\s*[=:：]\s*(?P<n>[+-]?\d+)\s*$", re.IGNORECASE)
_OFFSET_ANY_RE = re.compile(r"^\s*offset\b", re.IGNORECASE)
_BULLET_RE = re.compile(r"^[\-\*•>▪◦·]+\s*")
_TITLE_STRIP = " ,，、:：\t\"'“”‘’"


@dataclass
class Entry:
    title: str
    page: int  # 목차 파일에 적힌 인쇄 쪽수 (1부터)
    level: int
    lineno: int
    children: list["Entry"] = field(default_factory=list)


@dataclass
class ParsedToc:
    entries: list[Entry]
    offset: int | None          # 파일 안의 offset= 값 (없으면 None)
    warnings: list[LineMsg] = field(default_factory=list)


def _fmt_line(lineno: int, raw: str, reason: str, hint: str = "") -> str:
    msg = tr("line_fmt", n=lineno, reason=reason, raw=raw.strip())
    if hint:
        msg += tr("hint_fmt", hint=hint)
    return msg


def read_text(path: Path, encoding: str | None) -> str:
    """텍스트 파일을 읽는다. 인코딩 자동 판별, 바이너리 파일 거부."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise TocParseError(tr("read_err", path=path, err=exc.strerror or exc)) from exc

    if not raw.strip():
        raise TocParseError(tr("empty_file", name=path.name))

    if encoding:
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError) as exc:
            raise TocParseError(tr("decode_fail", enc=encoding, err=exc)) from exc

    # BOM 으로 확실히 알 수 있는 경우
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig")

    # PDF / 이미지 / Word 등 바이너리 파일을 목차로 넣은 경우
    head = raw[:4096]
    if head.startswith(b"%PDF"):
        raise TocParseError(tr("toc_is_pdf", name=path.name))
    if b"\x00" in head or head.startswith((b"PK\x03\x04", b"\xff\xd8", b"\x89PNG", b"\xd0\xcf\x11\xe0")):
        raise TocParseError(tr("toc_is_binary", name=path.name))

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass

    return _decode_legacy(raw, path.name)


def _count_hangul(s: str) -> int:
    return sum(1 for ch in s if "가" <= ch <= "힣")


def _count_cjk(s: str) -> int:
    return sum(1 for ch in s if "一" <= ch <= "鿿")


def _decode_legacy(raw: bytes, name: str) -> str:
    """cp949(한국어 Windows) 또는 gb18030(중국어 Windows).

    두 인코딩은 바이트가 겹쳐 서로 잘못 풀려도 오류가 안 난다. 한국어 바이트를 gb18030 으로 풀면
    깨끗한 한자만 나오고, 중국어 바이트를 cp949 로 풀면 한글과 한자가 섞여 나온다.
    그래서 cp949 로 풀었을 때 한자 비율이 높으면 중국어 파일로 본다.
    """
    from i18n import get_lang

    try:
        ko = raw.decode("cp949")
    except UnicodeDecodeError:
        ko = None
    try:
        zh = raw.decode("gb18030")
    except UnicodeDecodeError:
        zh = None

    if ko is None and zh is None:
        raise TocParseError(tr("unknown_encoding", name=name))
    if ko is None:
        return zh
    if zh is None:
        return ko

    h, c = _count_hangul(ko), _count_cjk(ko)
    if h == 0 and c == 0:
        return ko  # 영문/숫자뿐 → 어느 쪽이든 같다
    if h == 0:
        return zh
    ratio = c / (h + c)
    threshold = 0.2 if get_lang() == "zh" else 0.3
    return zh if ratio > threshold else ko


def parse_toc(text: str) -> ParsedToc:
    """텍스트를 트리 형태의 Entry 목록으로 변환. 문제 있는 줄은 전부 모아서 한 번에 알린다."""
    roots: list[Entry] = []
    stack: list[tuple[int, Entry]] = []  # (들여쓰기 폭, 항목)
    file_offset: int | None = None
    errors: list[str] = []
    error_lines: list[int] = []
    warnings: list[LineMsg] = []
    offset_lines: list[int] = []

    def err(lineno: int, raw: str, reason: str, hint: str = "") -> None:
        errors.append(_fmt_line(lineno, raw, reason, hint))
        error_lines.append(lineno)

    text = text.lstrip("﻿")  # 문자열로 직접 들어온 BOM
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("#"):
            # "# 1장, 12" 처럼 항목을 주석 처리한 줄이면 알려준다 (실수로 # 를 붙였을 수 있음)
            if _LINE_RE.match(stripped.lstrip("#").strip() or "x"):
                warnings.append(LineMsg(tr("commented_entry", n=lineno, text=stripped), lineno))
            continue

        if _OFFSET_ANY_RE.match(line):
            m = _OFFSET_RE.match(line)
            if not m:
                err(lineno, raw, tr("offset_not_int"), tr("offset_hint"))
                continue
            file_offset = int(m.group("n"))
            offset_lines.append(lineno)
            continue

        expanded = line.expandtabs(4)
        indent = len(expanded) - len(expanded.lstrip())
        body = _BULLET_RE.sub("", expanded.strip())

        page: int | None = None
        title = ""
        m = _RANGE_RE.match(body)
        if m and m.group("title").strip(_TITLE_STRIP):
            title = m.group("title").strip(_TITLE_STRIP)
            page = int(m.group("a"))
            warnings.append(LineMsg(
                tr("range_warn", n=lineno, title=title, a=m.group("a"), b=m.group("b"), page=page), lineno,
            ))
        else:
            m = _LINE_RE.match(body)
            if m:
                title = m.group("title").strip(_TITLE_STRIP)
                page = int(m.group("page"))

        if page is None:
            rm = _ROMAN_RE.match(body)
            if rm and not re.search(r"\d", body):
                err(lineno, raw, tr("roman_reason", roman=rm.group("roman")), tr("roman_hint"))
            else:
                err(lineno, raw, tr("no_page"), tr("example_hint"))
            continue
        if not title:
            err(lineno, raw, tr("no_title"), tr("example_hint"))
            continue
        if page < 1:
            err(lineno, raw, tr("page_lt_1"))
            continue

        while stack and indent <= stack[-1][0]:
            stack.pop()
        level = len(stack)
        entry = Entry(title=title, page=page, level=level, lineno=lineno)
        if stack:
            stack[-1][1].children.append(entry)
        else:
            roots.append(entry)
        stack.append((indent, entry))

    if len(offset_lines) > 1:
        warnings.append(LineMsg(
            tr("multi_offset", k=len(offset_lines), lines=", ".join(map(str, offset_lines)), value=file_offset),
            offset_lines[-1],
        ))

    if errors:
        head = tr("parse_head", n=len(errors))
        if len(errors) > MAX_REPORTED:
            head += tr("only_first", m=MAX_REPORTED)
        raise TocParseError(head + "\n" + "\n".join(errors[:MAX_REPORTED]), error_lines)

    if not roots:
        raise TocParseError(tr("no_entries", example=tr("example_hint")))
    return ParsedToc(roots, file_offset, warnings)


def flatten(entries: list[Entry]) -> list[Entry]:
    out: list[Entry] = []
    for e in entries:
        out.append(e)
        out.extend(flatten(e.children))
    return out


# ---------------------------------------------------------------- 검증 / 출력

def validate(entries: list[Entry], offset: int, num_pages: int) -> list[LineMsg]:
    """PDF 범위 밖 항목은 에러, 쪽수 역행은 경고."""
    errors: list[str] = []
    error_lines: list[int] = []
    warnings: list[LineMsg] = []
    prev: Entry | None = None
    flat = flatten(entries)
    too_big = too_small = 0
    for e in flat:
        pdf_page = e.page + offset
        kw = dict(n=e.lineno, title=e.title, page=e.page, offset=offset, pdf=pdf_page, total=num_pages)
        if pdf_page > num_pages:
            too_big += 1
            errors.append(tr("val_too_big", **kw))
            error_lines.append(e.lineno)
        elif pdf_page < 1:
            too_small += 1
            errors.append(tr("val_too_small", **kw))
            error_lines.append(e.lineno)
        if prev and e.page < prev.page:
            warnings.append(LineMsg(
                tr("val_backwards", n=e.lineno, title=e.title, page=e.page, prev=prev.title, prevpage=prev.page),
                e.lineno,
            ))
        prev = e

    if errors:
        head = tr("val_head", n=len(errors), total=num_pages)
        if too_big == len(flat):
            head += tr("val_all_big", offset=offset)
        elif too_small == len(flat):
            head += tr("val_all_small", offset=offset)
        elif too_big:
            max_e = max(flat, key=lambda e: e.page)
            head += tr("val_max_hint", n=max_e.lineno, title=max_e.title, page=max_e.page)
        if len(errors) > MAX_REPORTED:
            head += tr("only_first", m=MAX_REPORTED)
        raise TocParseError(head + "\n" + "\n".join("      " + s for s in errors[:MAX_REPORTED]), error_lines)
    return warnings


def print_tree(entries: list[Entry], offset: int) -> None:
    for e in flatten(entries):
        print(f"{'    ' * e.level}{e.title}  {tr('tree_line', page=e.page, pdf=e.page + offset)}")


# ---------------------------------------------------------------- PDF 읽기 / 쓰기

def open_pdf(path: Path) -> PdfReader:
    """PDF 를 열어 페이지를 셀 수 있는 상태로 돌려준다. 문제가 있으면 PdfError."""
    if not path.is_file():
        raise PdfError(tr("pdf_missing", path=path))
    try:
        with path.open("rb") as fh:
            head = fh.read(1024)
    except OSError as exc:
        raise PdfError(tr("pdf_read_err", path=path, err=exc.strerror or exc)) from exc
    if not head.strip():
        raise PdfError(tr("pdf_empty", name=path.name))
    if b"%PDF" not in head:
        raise PdfError(tr("pdf_not_pdf", name=path.name))
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise PdfError(tr("pdf_corrupt", name=path.name, err=exc)) from exc

    if reader.is_encrypted:
        try:
            ok = reader.decrypt("")
        except Exception as exc:  # AES 등 지원 안 되는 방식
            raise PdfError(tr("pdf_encrypted_unsupported", name=path.name, err=exc)) from exc
        if not ok:
            raise PdfError(tr("pdf_encrypted", name=path.name))

    try:
        n = len(reader.pages)
    except Exception as exc:
        raise PdfError(tr("pdf_count_fail", name=path.name, err=exc)) from exc
    if n == 0:
        raise PdfError(tr("pdf_zero_pages", name=path.name))
    return reader


def build_pdf(src: Path, dst: Path, entries: list[Entry], offset: int, keep_existing: bool) -> None:
    """북마크를 넣은 PDF 를 dst 에 쓴다. 임시 파일에 먼저 쓰고 성공하면 바꿔치기한다."""
    reader = open_pdf(src)
    writer = PdfWriter(clone_from=reader)

    if not keep_existing:
        # 기존 아웃라인 제거 (스캔 PDF는 보통 없지만, 다시 실행할 때 중복 방지)
        root = writer._root_object
        if "/Outlines" in root:
            del root["/Outlines"]

    def add(items: list[Entry], parent) -> None:
        for e in items:
            node = writer.add_outline_item(e.title, e.page + offset - 1, parent=parent)
            add(e.children, node)

    add(entries, None)
    writer.page_mode = "/UseOutlines"  # 열자마자 북마크 패널이 보이도록

    if not dst.parent.is_dir():
        raise PdfError(tr("out_dir_missing", dir=dst.parent))
    tmp = dst.with_name(dst.name + ".part")
    try:
        with tmp.open("wb") as fh:
            writer.write(fh)
        os.replace(tmp, dst)
    except PermissionError as exc:
        raise PdfError(tr("out_locked", path=dst)) from exc
    except OSError as exc:
        raise PdfError(tr("out_write_fail", path=dst, err=exc.strerror or exc)) from exc
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------- GUI (더블클릭 실행용)

def gui_main(pdf: str | None = None) -> int:
    """인수 없이 실행됐거나 PDF 하나만 끌어다 놓았을 때: pdf_toc_gui 창을 띄운다."""
    import pdf_toc_gui
    return pdf_toc_gui.run(pdf)


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    # 콘솔이 못 찍는 글자(구형 cmd 등) 때문에 죽지 않도록
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    raw_args = list(argv if argv is not None else sys.argv[1:])

    # --lang 은 도움말 문구에도 영향을 주므로 먼저 처리
    for i, a in enumerate(raw_args):
        if a.startswith("--lang="):
            set_lang(a.split("=", 1)[1])
            del raw_args[i]
            break
        if a == "--lang" and i + 1 < len(raw_args):
            set_lang(raw_args[i + 1])
            del raw_args[i:i + 2]
            break

    if not raw_args:
        return gui_main()
    if len(raw_args) == 1 and raw_args[0].lower().endswith(".pdf"):
        return gui_main(raw_args[0])  # exe 아이콘에 PDF 를 끌어다 놓은 경우

    ap = argparse.ArgumentParser(
        description=tr("cli_desc"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=tr("cli_epilog"),
    )
    ap.add_argument("pdf", type=Path, help=tr("cli_pdf"))
    ap.add_argument("toc", type=Path, help=tr("cli_toc"))
    ap.add_argument("-o", "--output", type=Path, help=tr("cli_out"))
    ap.add_argument("--offset", type=int, help=tr("cli_offset"))
    ap.add_argument("--encoding", help=tr("cli_encoding"))
    ap.add_argument("--keep-existing", action="store_true", help=tr("cli_keep"))
    ap.add_argument("--dry-run", action="store_true", help=tr("cli_dry"))
    ap.add_argument("--lang", choices=LANGS, help=tr("cli_lang"))
    args = ap.parse_args(raw_args)

    if not args.toc.is_file():
        ap.error(tr("cli_toc_missing", path=args.toc))

    try:
        parsed = parse_toc(read_text(args.toc, args.encoding))
        offset = args.offset if args.offset is not None else (parsed.offset or 0)
        num_pages = len(open_pdf(args.pdf).pages)
        warnings = parsed.warnings + validate(parsed.entries, offset, num_pages)
    except ToolError as exc:
        print(tr("cli_error") + str(exc), file=sys.stderr)
        return 1

    print(tr("cli_summary", pdf=args.pdf, total=num_pages, offset=offset, n=len(flatten(parsed.entries))))
    print_tree(parsed.entries, offset)
    for w in warnings:
        print(tr("cli_warn") + w, file=sys.stderr)

    if args.dry_run:
        print(tr("cli_dry_note"))
        return 0

    out = args.output or args.pdf.with_name(f"{args.pdf.stem}_toc.pdf")
    if out.resolve() == args.pdf.resolve():
        print(tr("cli_error") + tr("cli_same"), file=sys.stderr)
        return 1
    try:
        build_pdf(args.pdf, out, parsed.entries, offset, args.keep_existing)
    except ToolError as exc:
        print(tr("cli_error") + str(exc), file=sys.stderr)
        return 1
    print(tr("cli_done", path=out))
    return 0


if __name__ == "__main__":
    sys.exit(main())

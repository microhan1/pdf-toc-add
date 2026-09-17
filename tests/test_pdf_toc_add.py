"""pdf_toc_add 예외 상황 테스트.  실행:  python -m pytest tests -q"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pdf_toc_add as core  # noqa: E402


# ---------------------------------------------------------------- 픽스처

@pytest.fixture
def pdf12(tmp_path: Path) -> Path:
    """이미지 없이 빈 페이지 12장짜리 PDF (스캔본 대용)."""
    w = PdfWriter()
    for _ in range(12):
        w.add_blank_page(width=400, height=600)
    p = tmp_path / "scan.pdf"
    with p.open("wb") as fh:
        w.write(fh)
    return p


def toc_file(tmp_path: Path, content: str | bytes, name: str = "toc.txt") -> Path:
    p = tmp_path / name
    if isinstance(content, bytes):
        p.write_bytes(content)
    else:
        p.write_text(content, encoding="utf-8")
    return p


def titles(parsed: core.ParsedToc) -> list[tuple[int, str, int]]:
    return [(e.level, e.title, e.page) for e in core.flatten(parsed.entries)]


# ---------------------------------------------------------------- 정상 파싱

class TestParseOk:
    def test_various_separators(self):
        p = core.parse_toc(
            "머리말, 1\n1장 서론, 12쪽\n2장 본론 ...... 25\n3장 결론\t40\n부록 p.50\n찾아보기 페이지 60\n"
        )
        assert titles(p) == [
            (0, "머리말", 1), (0, "1장 서론", 12), (0, "2장 본론", 25),
            (0, "3장 결론", 40), (0, "부록", 50), (0, "찾아보기 페이지", 60),  # '페이지'는 접미어로만 인식
        ]

    def test_nesting_by_indent(self):
        p = core.parse_toc("1장, 1\n    1.1, 2\n        1.1.1, 3\n    1.2, 4\n2장, 5\n")
        assert [(lvl, t) for lvl, t, _ in titles(p)] == [
            (0, "1장"), (1, "1.1"), (2, "1.1.1"), (1, "1.2"), (0, "2장"),
        ]

    def test_tabs_and_mixed_indent(self):
        p = core.parse_toc("1장, 1\n\t1.1, 2\n  1.2, 3\n2장, 4\n")
        assert [lvl for lvl, _, _ in titles(p)] == [0, 1, 1, 0]

    def test_bullets_and_quotes_stripped(self):
        p = core.parse_toc('- 1장, 1\n* "2장", 2\n• 3장: 3\n')
        assert [t for _, t, _ in titles(p)] == ["1장", "2장", "3장"]

    def test_comments_blank_crlf_bom(self):
        p = core.parse_toc("﻿# 주석\r\n\r\n1장, 1\r\n   \r\n2장, 2\r\n")
        assert [t for _, t, _ in titles(p)] == ["1장", "2장"]

    def test_offset_line(self):
        assert core.parse_toc("offset=8\n1장, 1\n").offset == 8
        assert core.parse_toc("OFFSET : -3\n1장, 1\n").offset == -3
        assert core.parse_toc("1장, 1\n").offset is None

    def test_title_with_numbers_inside(self):
        p = core.parse_toc("제2차 세계대전 1939년의 유럽, 45\n1.1 2020년 현황, 7\n")
        assert titles(p) == [(0, "제2차 세계대전 1939년의 유럽", 45), (1 if False else 0, "1.1 2020년 현황", 7)]

    def test_fullwidth_digits_and_spaces(self):
        p = core.parse_toc("１장　서론，　１２\n")
        assert titles(p) == [(0, "１장　서론", 12)]

    def test_emoji_and_long_title(self):
        long = "아주 " * 100 + "긴 제목 🙂"
        p = core.parse_toc(f"{long}, 3\n")
        assert titles(p)[0][1] == long.strip()

    def test_page_range_uses_first_and_warns(self):
        p = core.parse_toc("1장 서론, 12-15\n2장, 20~25쪽\n")
        assert [pg for _, _, pg in titles(p)] == [12, 20]
        assert len(p.warnings) == 2 and "범위" in p.warnings[0]

    def test_commented_entry_warns(self):
        p = core.parse_toc("# 1장 서론, 12\n2장, 20\n")
        assert [t for _, t, _ in titles(p)] == ["2장"]
        assert any("주석" in w for w in p.warnings)

    def test_multiple_offsets_warn_last_wins(self):
        p = core.parse_toc("offset=3\n1장, 1\noffset=5\n")
        assert p.offset == 5
        assert any("offset 줄이 2개" in w for w in p.warnings)


# ---------------------------------------------------------------- 파싱 오류

class TestParseErrors:
    def test_no_page_number_reports_all_bad_lines(self):
        with pytest.raises(core.TocParseError) as ei:
            core.parse_toc("1장 서론\n2장 본론, 5\n3장 결론 없음\n")
        msg = str(ei.value)
        assert "2개 줄" in msg and "1행" in msg and "3행" in msg and "2행" not in msg
        assert "예)" in msg  # 고치는 방법 힌트

    def test_roman_numeral_hint(self):
        with pytest.raises(core.TocParseError) as ei:
            core.parse_toc("머리말 ..... iii\n")
        assert "로마 숫자" in str(ei.value)

    def test_number_only_line(self):
        with pytest.raises(core.TocParseError) as ei:
            core.parse_toc("12\n")
        assert "제목이 없습니다" in str(ei.value)

    def test_page_zero(self):
        with pytest.raises(core.TocParseError) as ei:
            core.parse_toc("표지, 0\n")
        assert "1 이상" in str(ei.value)

    def test_bad_offset_value(self):
        with pytest.raises(core.TocParseError) as ei:
            core.parse_toc("offset=abc\n1장, 1\n")
        assert "offset 값이 정수가 아닙니다" in str(ei.value)

    def test_empty_and_comment_only(self):
        for text in ("", "   \n\n", "# 주석만\n# 또 주석\n", "offset=3\n"):
            with pytest.raises(core.TocParseError) as ei:
                core.parse_toc(text)
            assert "하나도 없습니다" in str(ei.value)

    def test_error_count_capped(self):
        text = "\n".join(f"항목 {i} 쪽수없음" for i in range(50))  # 50줄 전부 쪽수 없음
        with pytest.raises(core.TocParseError) as ei:
            core.parse_toc(text)
        msg = str(ei.value)
        assert "50개 줄" in msg and f"처음 {core.MAX_REPORTED}개만" in msg
        assert msg.count("행:") == core.MAX_REPORTED


# ---------------------------------------------------------------- 파일 읽기 / 인코딩

class TestReadText:
    def test_utf8_cp949_utf16(self, tmp_path):
        body = "1장 서론, 2\n  1.1 배경, 3\n"
        for enc in ("utf-8", "utf-8-sig", "cp949", "utf-16", "utf-16-be"):
            p = toc_file(tmp_path, body.encode(enc), f"{enc}.txt")
            if enc == "utf-16-be":
                p.write_bytes(b"\xfe\xff" + body.encode("utf-16-be"))
            assert core.read_text(p, None) == body, enc

    def test_explicit_encoding_wrong(self, tmp_path):
        p = toc_file(tmp_path, "한글, 1\n".encode("cp949"))
        with pytest.raises(core.TocParseError) as ei:
            core.read_text(p, "utf-8")
        assert "utf-8" in str(ei.value)

    def test_pdf_as_toc(self, tmp_path, pdf12):
        with pytest.raises(core.TocParseError) as ei:
            core.read_text(pdf12, None)
        assert "PDF 파일입니다" in str(ei.value)

    @pytest.mark.parametrize("name,head", [
        ("photo.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 100),
        ("doc.docx", b"PK\x03\x04" + b"\x00" * 100),
        ("old.doc", b"\xd0\xcf\x11\xe0" + b"\x00" * 100),
        ("weird.txt", b"abc\x00def"),
    ])
    def test_binary_rejected(self, tmp_path, name, head):
        p = toc_file(tmp_path, head, name)
        with pytest.raises(core.TocParseError) as ei:
            core.read_text(p, None)
        assert "텍스트 파일이 아닌" in str(ei.value)

    def test_empty_file(self, tmp_path):
        p = toc_file(tmp_path, b"")
        with pytest.raises(core.TocParseError) as ei:
            core.read_text(p, None)
        assert "비어 있습니다" in str(ei.value)

    def test_missing_file(self, tmp_path):
        with pytest.raises(core.TocParseError):
            core.read_text(tmp_path / "없음.txt", None)


# ---------------------------------------------------------------- 검증

class TestValidate:
    def _entries(self, text):
        return core.parse_toc(text).entries

    def test_out_of_range_lists_each_and_hints_offset(self):
        with pytest.raises(core.TocParseError) as ei:
            core.validate(self._entries("1장, 5\n2장, 30\n3장, 40\n"), 0, 12)
        msg = str(ei.value)
        assert "2개 항목" in msg and "2행" in msg and "3행" in msg
        assert "가장 큰 쪽수는 3행" in msg

    def test_all_too_big_hints_offset_too_large(self):
        with pytest.raises(core.TocParseError) as ei:
            core.validate(self._entries("1장, 5\n2장, 8\n"), 100, 12)
        assert "offset(100)이 너무 크" in str(ei.value)

    def test_negative_offset_below_one(self):
        with pytest.raises(core.TocParseError) as ei:
            core.validate(self._entries("1장, 2\n2장, 3\n"), -5, 12)
        assert "너무 작습니다" in str(ei.value)

    def test_boundaries_ok(self):
        assert core.validate(self._entries("첫, 1\n끝, 12\n"), 0, 12) == []
        assert core.validate(self._entries("첫, 1\n끝, 4\n"), 8, 12) == []

    def test_backwards_page_warns_not_errors(self):
        w = core.validate(self._entries("1장, 5\n2장, 3\n"), 0, 12)
        assert len(w) == 1 and "앞에 있습니다" in w[0]


# ---------------------------------------------------------------- PDF 열기

class TestOpenPdf:
    def test_ok(self, pdf12):
        assert len(core.open_pdf(pdf12).pages) == 12

    def test_missing(self, tmp_path):
        with pytest.raises(core.PdfError) as ei:
            core.open_pdf(tmp_path / "없음.pdf")
        assert "없습니다" in str(ei.value)

    def test_text_renamed_to_pdf(self, tmp_path):
        p = toc_file(tmp_path, "이건 텍스트입니다\n", "fake.pdf")
        with pytest.raises(core.PdfError) as ei:
            core.open_pdf(p)
        assert "PDF 파일이 아닙니다" in str(ei.value)

    def test_empty_pdf_file(self, tmp_path):
        p = toc_file(tmp_path, b"", "empty.pdf")
        with pytest.raises(core.PdfError) as ei:
            core.open_pdf(p)
        assert "빈 파일" in str(ei.value)

    def test_truncated_pdf(self, tmp_path, pdf12):
        data = pdf12.read_bytes()
        p = tmp_path / "cut.pdf"
        p.write_bytes(data[: len(data) // 3])
        with pytest.raises(core.PdfError):
            core.open_pdf(p)

    def test_zero_pages(self, tmp_path):
        p = tmp_path / "zero.pdf"
        with p.open("wb") as fh:
            PdfWriter().write(fh)
        with pytest.raises(core.PdfError) as ei:
            core.open_pdf(p)
        assert "페이지가 없습니다" in str(ei.value)

    def test_owner_password_only_opens(self, tmp_path, pdf12):
        w = PdfWriter(clone_from=PdfReader(str(pdf12)))
        w.encrypt(user_password="", owner_password="owner")
        p = tmp_path / "owner.pdf"
        with p.open("wb") as fh:
            w.write(fh)
        assert len(core.open_pdf(p).pages) == 12

    def test_user_password_rejected(self, tmp_path, pdf12):
        w = PdfWriter(clone_from=PdfReader(str(pdf12)))
        w.encrypt(user_password="secret")
        p = tmp_path / "locked.pdf"
        with p.open("wb") as fh:
            w.write(fh)
        with pytest.raises(core.PdfError) as ei:
            core.open_pdf(p)
        assert "암호" in str(ei.value)


# ---------------------------------------------------------------- PDF 쓰기

def outline(path: Path) -> list[tuple[int, str, int]]:
    """(level, title, pdf_page) 목록으로 아웃라인을 평탄화."""
    r = PdfReader(str(path))
    out = []

    def walk(items, level):
        for it in items:
            if isinstance(it, list):
                walk(it, level + 1)
            else:
                out.append((level, it.title, r.get_destination_page_number(it) + 1))

    walk(r.outline, 0)
    return out


class TestBuild:
    def test_roundtrip_nested_offset(self, tmp_path, pdf12):
        parsed = core.parse_toc("1장, 1\n    1.1, 2\n2장, 5\n")
        out = tmp_path / "out.pdf"
        core.build_pdf(pdf12, out, parsed.entries, 2, keep_existing=False)
        assert outline(out) == [(0, "1장", 3), (1, "1.1", 4), (0, "2장", 7)]
        assert "/UseOutlines" in str(PdfReader(str(out)).trailer["/Root"].get("/PageMode"))

    def test_rerun_replaces_not_duplicates(self, tmp_path, pdf12):
        out1, out2 = tmp_path / "o1.pdf", tmp_path / "o2.pdf"
        core.build_pdf(pdf12, out1, core.parse_toc("A, 1\nB, 2\n").entries, 0, False)
        core.build_pdf(out1, out2, core.parse_toc("C, 3\n").entries, 0, False)
        assert outline(out2) == [(0, "C", 3)]

    def test_keep_existing_appends(self, tmp_path, pdf12):
        out1, out2 = tmp_path / "o1.pdf", tmp_path / "o2.pdf"
        core.build_pdf(pdf12, out1, core.parse_toc("A, 1\n").entries, 0, False)
        core.build_pdf(out1, out2, core.parse_toc("B, 2\n").entries, 0, True)
        assert outline(out2) == [(0, "A", 1), (0, "B", 2)]

    def test_unicode_titles_survive(self, tmp_path, pdf12):
        out = tmp_path / "u.pdf"
        core.build_pdf(pdf12, out, core.parse_toc("한글 제목 🙂 «guillemets», 1\n").entries, 0, False)
        assert outline(out)[0][1] == "한글 제목 🙂 «guillemets»"

    def test_output_dir_missing(self, tmp_path, pdf12):
        with pytest.raises(core.PdfError) as ei:
            core.build_pdf(pdf12, tmp_path / "없는폴더" / "o.pdf", core.parse_toc("A, 1\n").entries, 0, False)
        assert "출력 폴더가 없습니다" in str(ei.value)

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows 파일 잠금")
    def test_output_locked_by_other_program(self, tmp_path, pdf12):
        out = tmp_path / "locked.pdf"
        out.write_bytes(b"x")
        import msvcrt
        with out.open("r+b") as fh:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                with pytest.raises(core.PdfError) as ei:
                    core.build_pdf(pdf12, out, core.parse_toc("A, 1\n").entries, 0, False)
            finally:
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        assert "다른 프로그램" in str(ei.value)
        assert not out.with_name("locked.pdf.part").exists()  # 임시 파일 정리

    def test_no_partial_file_left_on_failure(self, tmp_path, pdf12):
        # 쓰기 실패 → .part 임시 파일이 남지 않아야 함
        target = tmp_path / "ro"
        target.mkdir()
        out = target / "o.pdf"
        out.write_bytes(b"x")
        import msvcrt
        with out.open("r+b") as fh:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            try:
                with pytest.raises(core.PdfError):
                    core.build_pdf(pdf12, out, core.parse_toc("A, 1\n").entries, 0, False)
            finally:
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        assert list(target.glob("*.part")) == []


# ---------------------------------------------------------------- CLI

class TestCli:
    def test_dry_run_ok(self, tmp_path, pdf12, capsys):
        toc = toc_file(tmp_path, "offset=2\n1장, 1\n")
        assert core.main([str(pdf12), str(toc), "--dry-run"]) == 0
        assert "PDF 3페이지" in capsys.readouterr().out

    def test_cli_offset_overrides_file(self, tmp_path, pdf12, capsys):
        toc = toc_file(tmp_path, "offset=2\n1장, 1\n")
        assert core.main([str(pdf12), str(toc), "--dry-run", "--offset", "5"]) == 0
        assert "PDF 6페이지" in capsys.readouterr().out

    def test_bad_toc_exit_1(self, tmp_path, pdf12, capsys):
        toc = toc_file(tmp_path, "쪽수 없는 줄\n")
        assert core.main([str(pdf12), str(toc)]) == 1
        assert "1행" in capsys.readouterr().err

    def test_bad_pdf_exit_1(self, tmp_path, capsys):
        toc = toc_file(tmp_path, "1장, 1\n")
        fake = toc_file(tmp_path, "not pdf", "fake.pdf")
        assert core.main([str(fake), str(toc)]) == 1
        assert "PDF 파일이 아닙니다" in capsys.readouterr().err

    def test_output_same_as_input_refused(self, tmp_path, pdf12, capsys):
        toc = toc_file(tmp_path, "1장, 1\n")
        assert core.main([str(pdf12), str(toc), "-o", str(pdf12)]) == 1
        assert "원본과 같습니다" in capsys.readouterr().err

    def test_writes_default_name(self, tmp_path, pdf12):
        toc = toc_file(tmp_path, "1장, 1\n")
        assert core.main([str(pdf12), str(toc)]) == 0
        assert (tmp_path / "scan_toc.pdf").exists()

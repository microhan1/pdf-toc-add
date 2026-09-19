"""offset 자동 감지 테스트.  OCR 시험은 Windows OCR 을 쓸 수 있을 때만 돈다."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DecodedStreamObject, DictionaryObject, NameObject

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import offset_detect as od  # noqa: E402
import pdf_toc_add as core  # noqa: E402


# ---------------------------------------------------------------- 글자 층 PDF 만들기

def _font_resources() -> DictionaryObject:
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    return DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})


def text_layer_pdf(path: Path, pages: int, offset: int, *, where: str = "bottom", rotate: int = 0,
                   header: str | None = None, numbers: bool = True) -> Path:
    """쪽 번호가 글자 층으로 들어간 A5 PDF. 앞 offset 쪽은 쪽 번호가 없는 앞부분이다."""
    w = PdfWriter()
    W, H = 420, 595
    for i in range(pages):
        page = w.add_blank_page(width=W, height=H)
        printed = i - offset + 1
        ops = ["BT /F1 10 Tf 40 300 Td (body text line) Tj ET"]
        if header:
            ops.append(f"BT /F1 8 Tf 60 570 Td ({header}) Tj ET")
        if numbers and printed >= 1:
            # 화면에서 아래(또는 위) 가운데에 보이도록 둔다. /Rotate 90 이면 화면 아래는 페이지 좌표의 오른쪽,
            # /Rotate 270 이면 왼쪽이다 (스캐너가 눕혀 저장하고 /Rotate 로 세운 경우와 같다).
            x, y = {0: (205, 20), 90: (400, 297), 270: (15, 297)}[rotate]
            if where == "top":
                x, y = {0: (205, 570), 90: (15, 297), 270: (400, 297)}[rotate]
            ops.append(f"BT /F1 9 Tf {x} {y} Td ({printed}) Tj ET")
        stream = DecodedStreamObject()
        stream.set_data("\n".join(ops).encode())
        page[NameObject("/Contents")] = w._add_object(stream)
        page[NameObject("/Resources")] = _font_resources()
        if rotate:
            page.rotate(rotate)
    with path.open("wb") as fh:
        w.write(fh)
    return path


# ---------------------------------------------------------------- 단위

class TestNumbers:
    @pytest.mark.parametrize("text,expect", [
        ("127", [127]), ("- 12 -", [12]), ("p. 12", [12]), ("第12页", [12]), ("12쪽", [12]), ("[45]", [45]),
        ("127 제3장 데이터 모델", [127]), ("Chapter 3 Data 127", [127]), ("제3장 데이터 모델", []),
        ("ISBN 978-89", []), ("12345", []), ("", []),
    ])
    def test_numbers_in(self, text, expect):
        assert od.numbers_in(text) == expect

    def test_ocr_fixups_only_touch_short_digit_words(self):
        assert od._fix_ocr_word("1O7") == "107"
        assert od._fix_ocr_word("l2") == "12"
        assert od._fix_ocr_word("Index") == "Index"  # 숫자가 없는 단어는 그대로


class TestSample:
    def test_body_range_and_cap(self):
        s = od.sample_pages(300)
        assert len(s) == od.MAX_SAMPLES and s[0] >= int(300 * od.SAMPLE_FROM) and s[-1] < 300
        assert s == sorted(set(s))

    def test_thin_documents_use_every_page(self):
        assert od.sample_pages(10) == list(range(10))
        assert od.sample_pages(0) == []


class TestVote:
    def test_consistent(self):
        cand = {p: [p - 8] for p in range(20, 44)}
        r = od.vote(cand, 200)
        assert r.offset == 8 and r.votes == 24 and r.pages_with_numbers == 24

    def test_chapter_numbers_in_header_do_not_win(self):
        # 머리글의 장 번호 3 은 페이지마다 offset 후보가 달라 표가 모이지 않는다
        cand = {p: [3, p - 5] for p in range(20, 40)}
        assert od.vote(cand, 200).offset == 5

    def test_inconsistent_gives_no_answer(self):
        cand = {20: [3], 21: [9], 22: [40], 23: [1], 24: [7]}
        r = od.vote(cand, 100)
        assert r.offset is None and r.reason == "inconsistent"

    def test_too_few_votes(self):
        assert od.vote({30: [22], 31: [23]}, 100).offset is None  # 2표뿐

    def test_close_runner_up_gives_no_answer(self):
        cand = {p: [p - 4] for p in range(10, 15)}
        cand.update({p: [p - 6] for p in range(20, 24)})
        assert od.vote(cand, 100).offset is None  # 5 대 4

    def test_nothing_found(self):
        r = od.vote({10: [], 11: []}, 50)
        assert r.offset is None and r.reason == "no_numbers"

    def test_negative_offset_for_excerpts(self):
        cand = {p: [p + 100] for p in range(3, 20)}  # 책 101쪽부터 잘라 낸 PDF
        assert od.vote(cand, 30).offset == -100


class TestImageOrientation:
    class _Page:
        def __init__(self, rot):
            self.rotation = rot

    @pytest.mark.parametrize("rot,cm,expect", [
        (0, [595, 0, 0, 842], (0, False)),        # 보통 스캔
        (90, [842, 0, 0, 595], (270, False)),     # 눕혀 저장하고 /Rotate 90 으로 세운 스캔
        (180, [595, 0, 0, 842], (180, False)),
        (270, [842, 0, 0, 595], (90, False)),
        (0, [0, 842, -595, 0], (90, False)),      # cm 안에서 90도 돌려 그린 이미지
        (0, [595, 0, 0, -842], (180, True)),      # 위아래가 뒤집힌 이미지 = 180도 + 좌우 반전
    ])
    def test_mapping(self, rot, cm, expect):
        assert od._image_to_display(self._Page(rot), cm) == expect


# ---------------------------------------------------------------- 글자 층 PDF

class TestTextLayer:
    @pytest.mark.parametrize("where,rotate", [("bottom", 0), ("top", 0), ("bottom", 90), ("bottom", 270)])
    def test_detects_offset(self, tmp_path, where, rotate):
        pdf = text_layer_pdf(tmp_path / "t.pdf", 120, 9, where=where, rotate=rotate, header="Chapter 3 Data")
        r = od.detect_offset(pdf, use_ocr=False)
        assert r.offset == 9 and not r.used_ocr

    def test_no_page_numbers(self, tmp_path):
        pdf = text_layer_pdf(tmp_path / "t.pdf", 80, 5, numbers=False, header="Chapter 3 2024")
        r = od.detect_offset(pdf, use_ocr=False)
        assert r.offset is None

    def test_image_less_pdf_without_ocr_reports_no_numbers(self, tmp_path):
        w = PdfWriter()
        for _ in range(30):
            w.add_blank_page(width=420, height=595)
        p = tmp_path / "blank.pdf"
        w.write(str(p))
        r = od.detect_offset(p, use_ocr=False)
        assert r.offset is None and r.reason == "no_numbers"

    def test_cancel(self, tmp_path):
        import threading
        pdf = text_layer_pdf(tmp_path / "t.pdf", 60, 3)
        ev = threading.Event()
        ev.set()
        assert od.detect_offset(pdf, cancel=ev).reason == "cancelled"

    def test_progress_reports_every_sample(self, tmp_path):
        pdf = text_layer_pdf(tmp_path / "t.pdf", 60, 3)
        seen = []
        od.detect_offset(pdf, use_ocr=False, early_stop=False, progress=lambda i, n: seen.append((i, n)))
        assert seen[-1][0] == seen[-1][1] == len(od.sample_pages(60))

    def test_early_stop_on_clear_books(self, tmp_path):
        pdf = text_layer_pdf(tmp_path / "t.pdf", 200, 11)
        seen = []
        r = od.detect_offset(pdf, use_ocr=False, progress=lambda i, n: seen.append(i))
        assert r.offset == 11 and len(seen) == od.EARLY_MIN_PAGES < len(od.sample_pages(200))


class TestSpreadOrder:
    def test_is_a_permutation_that_spans_the_book_early(self):
        pages = list(range(100, 124))
        order = od.spread_order(pages)
        assert sorted(order) == pages
        first = sorted(order[:8])
        assert first[0] == 100 and first[-1] - first[0] >= 18  # 처음 8쪽이 책 전체에 퍼져 있다

    def test_small(self):
        assert od.spread_order([]) == []
        assert od.spread_order([5]) == [5]
        assert od.spread_order(list(range(8))) == [0, 4, 2, 6, 1, 3, 5, 7]


class TestCli:
    def test_auto_offset(self, tmp_path, capsys):
        pdf = text_layer_pdf(tmp_path / "book.pdf", 100, 7)
        toc = tmp_path / "toc.txt"
        toc.write_text("offset=2\n1장, 1\n2장, 30\n", encoding="utf-8")
        assert core.main([str(pdf), str(toc), "--auto-offset", "--dry-run"]) == 0
        out = capsys.readouterr()
        assert "PDF 8페이지" in out.out and "offset=2" in out.err  # 감지값 7 사용, 목차의 2 와 다르다고 경고

    def test_explicit_offset_wins(self, tmp_path, capsys):
        pdf = text_layer_pdf(tmp_path / "book.pdf", 100, 7)
        toc = tmp_path / "toc.txt"
        toc.write_text("1장, 1\n", encoding="utf-8")
        assert core.main([str(pdf), str(toc), "--auto-offset", "--offset", "4", "--dry-run"]) == 0
        assert "PDF 5페이지" in capsys.readouterr().out

    def test_auto_offset_failure_exits_1(self, tmp_path, capsys):
        pdf = text_layer_pdf(tmp_path / "book.pdf", 60, 4, numbers=False)
        toc = tmp_path / "toc.txt"
        toc.write_text("1장, 1\n", encoding="utf-8")
        assert core.main([str(pdf), str(toc), "--auto-offset", "--dry-run"]) == 1
        assert "offset" in capsys.readouterr().err


# ---------------------------------------------------------------- Windows OCR (스캔 이미지)

@pytest.mark.skipif(not od.WindowsOcr.available(), reason="Windows OCR 을 쓸 수 없음")
class TestOcr:
    @pytest.mark.parametrize("layout,rotate", [("bottom_outer", 0), ("top_header", 90)])
    def test_synthetic_scan(self, tmp_path, monkeypatch, layout, rotate):
        import validate_offset as v
        monkeypatch.setattr(v, "WORK", tmp_path)
        spec = v.BookSpec(f"ocr_{layout}", layout=layout, pages=40, offset=6, dpi=150, rotate_attr=rotate, seed=5)
        r = od.detect_offset(v.make_book(spec))
        assert r.offset == 6 and r.used_ocr

    def test_two_page_spread_gives_no_answer(self, tmp_path, monkeypatch):
        import validate_offset as v
        monkeypatch.setattr(v, "WORK", tmp_path)
        spec = v.BookSpec("ocr_spread", layout="spread", pages=30, dpi=120, seed=6)
        assert od.detect_offset(v.make_book(spec)).offset is None

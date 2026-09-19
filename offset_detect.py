"""offset_detect.py - 스캔 PDF 에서 "책의 인쇄 쪽수"와 "PDF 페이지 번호"의 차이(offset)를 자동으로 찾는다.

방법
    1. 책 본문 구간(앞 8% ~ 끝 95%)에서 페이지를 고르게 뽑는다. 앞쪽 머리말의 로마 숫자 쪽수를 피하기 위해서다.
    2. 각 페이지의 위, 아래 띠(높이의 12%)에서 쪽 번호처럼 생긴 숫자를 찾는다.
       - 텍스트 층(ScanSnap, vFlat, ABBYY 등이 넣는 OCR 글자)이 있으면 그것을 쓴다. 빠르고 정확하다.
       - 없으면 페이지 이미지의 띠를 잘라 Windows 내장 OCR 로 읽는다.
    3. 숫자 n 이 PDF p 페이지에서 나오면 offset 후보는 p - n 이다. 페이지마다 한 표씩 던져 가장 많이 나온
       값을 고른다. 장 번호("Chapter 3")나 연도처럼 쪽 번호가 아닌 숫자는 페이지마다 후보가 제각각이라
       표가 모이지 않는다.
    4. 표가 충분히 모이고(MIN_VOTES), 전체에서 차지하는 비율이 높고(MIN_SHARE), 2위와 차이가 날 때만
       결과를 낸다. 애매하면 답을 내지 않는다. 틀린 offset 은 북마크 전체를 망치지만, 답을 안 내면 사용자가
       직접 입력하면 되기 때문이다.

PyMuPDF 는 AGPL 이라 MIT 인 이 저장소의 exe 에 넣지 않는다. 이미지는 pypdf 로 꺼내고, JPEG 은 PIL 의
draft 모드로 줄여서 디코딩한다.
"""

from __future__ import annotations

import io
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from pypdf import PdfReader

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

# ---------------------------------------------------------------- 기준값
# 기준값은 합성 스캔 책으로 정했다 (tools/validate_offset.py). 학습 세트(바탕체, 300dpi, 쪽 번호 배치 4종 ×
# 씨앗 2 + 음성 대조군 3권)에서는 모든 조합이 만점이라 오답 위험이 가장 적은 보수적인 값을 골랐다.
# 검증 세트(맑은 고딕/Times/SimSun, 150·300·400dpi, 어두운 종이, 흐린 잉크, /Rotate 90, 책 48권 + 음성 9권):
#   정답 48/48, 오답 0, 음성 대조군 거짓양성 0/9. 조기 종료 시 표본 24쪽 중 평균 14.4쪽만 본다.
#   명암 늘림 전(v1)에는 흐린 중국어 책 2권이 답 없음이었다. 쪽 번호 띠만 따로 펴면 20권이 답을 못 냈다.
SAMPLE_FROM, SAMPLE_TO = 0.08, 0.95   # 표본을 뽑을 구간 (문서 길이에 대한 비율)
MAX_SAMPLES = 24                      # 표본 페이지 수 상한
BAND = 0.12                           # 위, 아래 띠 높이 (페이지 높이에 대한 비율)
MIN_VOTES = 3                         # 같은 offset 을 가리킨 페이지가 이만큼은 있어야 한다
MIN_SHARE = 0.5                       # 숫자가 하나라도 나온 페이지 중 이 비율 이상이 같은 offset 이어야 한다
MIN_MARGIN = 2                        # 1위 표가 2위보다 이만큼은 많아야 한다
MAX_IMAGE_PIXELS = 60_000_000         # 이보다 큰 이미지는 OCR 하지 않는다 (포스터급 페이지의 메모리 보호)
OCR_TARGET_HEIGHT = 2200              # 페이지 이미지를 이 높이 근처로 줄여 OCR 한다 (300dpi A4 ≈ 3500)
OCR_MIN_HEIGHT = 1300                 # 이보다 작은 저해상도 스캔은 2배로 키워 OCR 한다

_NUM_RE = re.compile(
    r"^[\s\-–—\[\(（【|·•]*(?:p\.?\s*|pp\.?\s*|page\s*|第\s*)?(\d{1,4})\s*(?:쪽|페이지|页|頁|p)?[\s\-–—\]\)）】|·•.]*$",
    re.IGNORECASE,
)
# OCR 이 숫자를 비슷한 글자로 읽는 흔한 경우. 숫자가 하나 이상 섞인 짧은 단어에만 적용한다.
_OCR_FIX = str.maketrans({"O": "0", "o": "0", "D": "0", "l": "1", "I": "1", "|": "1", "i": "1", "S": "5", "B": "8", "Z": "2"})


@dataclass
class OffsetResult:
    offset: int | None                     # 찾은 offset. 확신이 없으면 None
    reason: str = ""                       # 실패 이유 키: no_pages, no_numbers, inconsistent, ocr_unavailable, cancelled
    votes: int = 0                         # 찾은 offset 을 가리킨 페이지 수
    pages_with_numbers: int = 0            # 쪽 번호 후보가 하나라도 나온 페이지 수
    sampled: int = 0                       # 살펴본 페이지 수
    evidence: list[tuple[int, int]] = field(default_factory=list)  # (PDF 페이지, 인쇄 쪽수) 몇 개
    used_ocr: bool = False                 # 이미지 OCR 을 한 번이라도 썼는지
    runner_up: tuple[int, int] | None = None  # (2위 offset, 표 수) — 애매할 때 설명용


# ---------------------------------------------------------------- 표본 뽑기

def sample_pages(num_pages: int, max_samples: int = MAX_SAMPLES) -> list[int]:
    """0부터 시작하는 페이지 번호 목록. 본문 구간에서 고르게 뽑는다."""
    if num_pages <= 0:
        return []
    lo = int(num_pages * SAMPLE_FROM)
    hi = max(lo + 1, int(num_pages * SAMPLE_TO))
    span = list(range(lo, min(hi, num_pages)))
    if len(span) < max_samples:  # 얇은 문서는 전체를 본다
        span = list(range(num_pages))
    if len(span) <= max_samples:
        return span
    step = (len(span) - 1) / (max_samples - 1)
    return sorted({span[round(i * step)] for i in range(max_samples)})


# ---------------------------------------------------------------- 숫자 후보

def numbers_in(text: str) -> list[int]:
    """"- 12 -", "p. 12", "第12页", "12쪽" 처럼 쪽 번호로 보이는 조각에서 숫자를 꺼낸다."""
    out = []
    for piece in re.split(r"\s{2,}|\t|\n", text):
        piece = piece.strip()
        if not piece:
            continue
        m = _NUM_RE.match(piece) if len(piece) <= 12 else None
        if m:
            out.append(int(m.group(1)))
            continue
        # 한 칸 띄어쓰기로 붙은 머리글 "127 제3장 데이터 모델" / "Chapter 3 127" → 양 끝 숫자만 본다
        words = piece.split()
        for w in (words[0], words[-1]) if len(words) > 1 else ():
            m = _NUM_RE.match(w)
            if m:
                out.append(int(m.group(1)))
    return out


def _fix_ocr_word(word: str) -> str:
    if len(word) <= 5 and any(ch.isdigit() for ch in word):
        return word.translate(_OCR_FIX)
    return word


# ---------------------------------------------------------------- 좌표 변환

def _display_frac_y(page, x: float, y: float) -> float:
    """페이지 좌표 (x, y) 가 화면에 보일 때 위에서부터의 비율(0=위, 1=아래). /Rotate 를 반영한다."""
    box = page.mediabox
    x0, y0, x1, y1 = float(box.left), float(box.bottom), float(box.right), float(box.top)
    w, h = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
    rot = (page.rotation or 0) % 360
    if rot == 90:
        return (x - x0) / w
    if rot == 180:
        return (y - y0) / h
    if rot == 270:
        return (x1 - x) / w
    return (y1 - y) / h


def _to_display(page, x: float, y: float) -> tuple[float, float]:
    """페이지 좌표를 화면 좌표(오른쪽 +x, 아래 +y)로. 방향만 필요하므로 원점은 신경 쓰지 않는다."""
    rot = (page.rotation or 0) % 360
    if rot == 90:
        return y, x
    if rot == 180:
        return -x, y
    if rot == 270:
        return -y, -x
    return x, -y


def _image_to_display(page, cm) -> tuple[int, bool]:
    """이미지를 화면에 보이는 방향으로 돌리려면 PIL 로 몇 도(반시계) 돌리고 좌우를 뒤집어야 하는지.

    이미지 단위 정사각형 (u, v) 는 페이지 좌표 (a·u + c·v + e, b·u + d·v + f) 에 놓인다. 이미지 데이터의
    첫 행은 v = 1 쪽이다. 이미지의 "위"(v 증가)와 "오른쪽"(u 증가)이 화면에서 어느 쪽을 향하는지 보고 정한다.
    """
    a, b, c, d = (float(v) for v in cm[:4])
    ux, uy = _to_display(page, a, b)   # 이미지 오른쪽 방향
    vx, vy = _to_display(page, c, d)   # 이미지 위쪽 방향
    # 이미지 위쪽이 화면의 어느 쪽인가: 화면 위는 (0, -1)
    if abs(vx) >= abs(vy):
        up = "right" if vx > 0 else "left"
    else:
        up = "up" if vy < 0 else "down"
    angle = {"up": 0, "left": 90, "down": 180, "right": 270}[up]  # PIL rotate 는 반시계
    # 돌린 뒤 이미지 오른쪽이 화면 오른쪽인지 확인. 아니면 거울상이다.
    cross = ux * vy - uy * vx  # 정상 방향이면 음수 (화면 좌표계는 y 가 아래)
    return angle, cross > 0


# ---------------------------------------------------------------- 텍스트 층

def _text_layer_numbers(page) -> list[int]:
    pieces: list[tuple[str, float]] = []

    def visit(text, cm, tm, _font, _size):
        if not text or not text.strip():
            return
        x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
        y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
        pieces.append((text, _display_frac_y(page, x, y)))

    try:
        page.extract_text(visitor_text=visit)
    except Exception:
        return []
    band_text = [t for t, fy in pieces if fy <= BAND or fy >= 1 - BAND]
    out: list[int] = []
    for t in band_text:
        out.extend(numbers_in(t))
    return out


# ---------------------------------------------------------------- 이미지 + OCR

def _page_image(page) -> "Image.Image | None":
    """페이지에서 가장 큰 이미지를 화면 방향으로 돌린 회색조 PIL 이미지로. 없거나 못 읽으면 None."""
    if Image is None:
        return None
    placements: dict[str, list] = {}

    def before(op, args, cm, _tm):
        if op == b"Do" and args:
            placements.setdefault(str(args[0]), list(cm))

    try:
        page.extract_text(visitor_operand_before=before)
        xobjects = page["/Resources"].get_object().get("/XObject")
        xobjects = xobjects.get_object() if xobjects is not None else {}
    except Exception:
        return None

    best = None
    for name, ref in xobjects.items():
        try:
            obj = ref.get_object()
            if obj.get("/Subtype") != "/Image":
                continue
            w, h = int(obj["/Width"]), int(obj["/Height"])
        except Exception:
            continue
        if name in placements and (best is None or w * h > best[1] * best[2]):
            best = (name, w, h, obj)
    if best is None:
        return None
    name, w, h, obj = best
    if w * h > MAX_IMAGE_PIXELS:
        return None

    img = None
    filters = obj.get("/Filter")
    filters = [filters] if isinstance(filters, str) else list(filters or [])
    try:
        if filters == ["/DCTDecode"]:
            img = Image.open(io.BytesIO(obj._data))
            if max(w, h) > OCR_TARGET_HEIGHT:
                scale = OCR_TARGET_HEIGHT / max(w, h)
                img.draft("L", (int(w * scale), int(h * scale)))  # JPEG 을 줄여서 디코딩: 몇 배 빠르다
            img = img.convert("L")
        else:
            img = page.images[name].image.convert("L")
    except Exception:
        return None  # JBIG2 처럼 pypdf 가 못 푸는 형식

    angle, mirrored = _image_to_display(page, placements[name])
    if angle:
        img = img.rotate(angle, expand=True)
    if mirrored:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    return img


def _prepare_for_ocr(img: "Image.Image") -> "Image.Image":
    from PIL import ImageOps
    h = img.height
    if h > OCR_TARGET_HEIGHT * 1.3:
        img = img.resize((round(img.width * OCR_TARGET_HEIGHT / h), OCR_TARGET_HEIGHT), Image.LANCZOS)
    elif h < OCR_MIN_HEIGHT:
        img = img.resize((img.width * 2, h * 2), Image.LANCZOS)
    # 페이지 전체 기준으로 명암을 편다. 흐린 인쇄(종이 205, 잉크 150)를 Windows OCR 이 읽게 된다.
    # 쪽 번호 띠만 따로 펴면 잉크가 1% 도 안 돼 종이 잡음이 부풀고, 검증 세트 20권이 답을 못 냈다.
    return ImageOps.autocontrast(img, cutoff=1)


class WindowsOcr:
    """Windows 10/11 내장 OCR (Windows.Media.Ocr). 설치할 것이 없고, 설치된 언어 중 하나면 숫자는 읽는다."""

    def __init__(self) -> None:
        from winrt.windows.media.ocr import OcrEngine  # noqa: F401  (없으면 ImportError)
        self._engine = None

    @staticmethod
    def available() -> bool:
        try:
            from winrt.windows.media.ocr import OcrEngine
            return len(list(OcrEngine.available_recognizer_languages)) > 0
        except Exception:
            return False

    def _get_engine(self):
        if self._engine is None:
            from winrt.windows.globalization import Language
            from winrt.windows.media.ocr import OcrEngine
            eng = OcrEngine.try_create_from_user_profile_languages()
            if eng is None:
                for lang in OcrEngine.available_recognizer_languages:
                    eng = OcrEngine.try_create_from_language(Language(lang.language_tag))
                    if eng is not None:
                        break
            if eng is None:
                raise RuntimeError("no OCR language")
            self._engine = eng
        return self._engine

    def read_words(self, img: "Image.Image") -> list[str]:
        """이미지 속 줄마다 글자를 돌려준다 (단어 사이는 공백, 줄 사이는 두 칸 띄어 조각을 나눈다)."""
        import asyncio
        from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
        from winrt.windows.storage.streams import Buffer

        rgba = img.convert("RGBA")
        data = rgba.tobytes()
        buf = Buffer(len(data))
        buf.length = len(data)
        memoryview(buf)[:] = data
        bmp = SoftwareBitmap.create_copy_from_buffer(buf, BitmapPixelFormat.RGBA8, rgba.width, rgba.height)
        engine = self._get_engine()

        async def run():
            return await engine.recognize_async(bmp)

        result = asyncio.run(run())
        lines = []
        for line in result.lines:
            words = [_fix_ocr_word(w.text) for w in line.words]
            # 한 줄 안에서도 멀리 떨어진 단어(왼쪽 머리글과 오른쪽 쪽 번호)는 따로 본다
            groups, cur, last_right = [], [], None
            for w, word in zip(line.words, words):
                r = w.bounding_rect
                if last_right is not None and r.x - last_right > max(r.height * 2.5, 40):
                    groups.append(" ".join(cur))
                    cur = []
                cur.append(word)
                last_right = r.x + r.width
            groups.append(" ".join(cur))
            lines.extend(groups)
        return lines


def _ocr_numbers(img: "Image.Image", ocr: WindowsOcr) -> list[int]:
    img = _prepare_for_ocr(img)
    band = max(1, round(img.height * BAND))
    out: list[int] = []
    for box in ((0, 0, img.width, band), (0, img.height - band, img.width, img.height)):
        strip = img.crop(box)
        try:
            for piece in ocr.read_words(strip):
                out.extend(numbers_in(piece))
        except Exception:
            continue
    return out


# ---------------------------------------------------------------- 투표

def vote(candidates: dict[int, list[int]], num_pages: int, *, min_votes: int = MIN_VOTES,
         min_share: float = MIN_SHARE, min_margin: int = MIN_MARGIN) -> OffsetResult:
    """candidates: {PDF 페이지(1부터): [쪽 번호 후보]} → OffsetResult"""
    tally: dict[int, list[tuple[int, int]]] = {}
    pages_with = 0
    for pdf_page, nums in candidates.items():
        offs = {pdf_page - n: n for n in nums if 1 <= n <= 9999}
        if not offs:
            continue
        pages_with += 1
        for off, n in offs.items():
            tally.setdefault(off, []).append((pdf_page, n))
    res = OffsetResult(offset=None, sampled=len(candidates), pages_with_numbers=pages_with)
    if not tally:
        res.reason = "no_numbers"
        return res
    ranked = sorted(tally.items(), key=lambda kv: (-len(kv[1]), abs(kv[0])))
    best_off, best_ev = ranked[0]
    second = len(ranked[1][1]) if len(ranked) > 1 else 0
    res.votes = len(best_ev)
    res.evidence = sorted(best_ev)[:6]
    if len(ranked) > 1:
        res.runner_up = (ranked[1][0], second)
    if res.votes >= min_votes and res.votes >= min_share * pages_with and res.votes - second >= min_margin:
        res.offset = best_off
    else:
        res.reason = "inconsistent"
    return res


# ---------------------------------------------------------------- 진입점

EARLY_MIN_PAGES = 8    # 조기 종료: 최소 이만큼은 보고,
EARLY_VOTES = 8        # 1위가 이만큼 표를 얻고,
EARLY_SHARE = 0.9      # 숫자가 나온 페이지의 90% 이상이 1위이며,
EARLY_MARGIN = 6       # 2위와 이만큼 차이가 나면 멈춘다. (검증 세트에서 결과가 바뀐 책 0권)


def spread_order(pages: list[int]) -> list[int]:
    """앞에서부터가 아니라 책 전체에 고루 퍼지는 순서로. 조기 종료해도 한 구간만 보고 판단하지 않게 한다.
    [0..7] → [0, 4, 2, 6, 1, 3, 5, 7]"""
    order, seen = [], set()
    n = len(pages)
    step = 1
    while step < n:
        step *= 2
    while step >= 1:
        for i in range(0, n, step):
            if i not in seen:
                seen.add(i)
                order.append(pages[i])
        step //= 2
    return order


def _confident(by_page: dict[int, list[int]]) -> bool:
    if len(by_page) < EARLY_MIN_PAGES:
        return False
    tally: dict[int, int] = {}
    with_nums = 0
    for p, nums in by_page.items():
        offs = {p - n for n in nums if 1 <= n <= 9999}
        with_nums += bool(offs)
        for off in offs:
            tally[off] = tally.get(off, 0) + 1
    if not tally:
        return False
    ranked = sorted(tally.values(), reverse=True)
    best, second = ranked[0], (ranked[1] if len(ranked) > 1 else 0)
    return best >= EARLY_VOTES and best >= EARLY_SHARE * with_nums and best - second >= EARLY_MARGIN


@dataclass
class Candidates:
    by_page: dict[int, list[int]]   # {PDF 페이지(1부터): [쪽 번호 후보]}
    num_pages: int
    used_ocr: bool = False
    ocr_missing: bool = False       # 이미지가 있어 OCR 이 필요했는데 쓸 수 없었다
    cancelled: bool = False


def collect_candidates(
    reader: PdfReader,
    *,
    max_samples: int = MAX_SAMPLES,
    use_ocr: bool = True,
    progress: Callable[[int, int], None] | None = None,
    cancel: threading.Event | None = None,
    ocr: "WindowsOcr | None" = None,
    early_stop: bool = True,
) -> Candidates:
    num_pages = len(reader.pages)
    out = Candidates(by_page={}, num_pages=num_pages)
    pages = spread_order(sample_pages(num_pages, max_samples))
    ocr_ok = None  # 처음 필요할 때 확인
    for i, idx in enumerate(pages):
        if early_stop and _confident(out.by_page):
            break  # 이미 충분히 확실하다. 나머지 표본은 볼 필요가 없다
        if cancel is not None and cancel.is_set():
            out.cancelled = True
            return out
        page = reader.pages[idx]
        nums = _text_layer_numbers(page)
        if not nums and use_ocr:
            if ocr_ok is None:
                ocr_ok = ocr is not None or WindowsOcr.available()
                if ocr_ok and ocr is None:
                    ocr = WindowsOcr()
            img = _page_image(page)
            if img is not None:
                if ocr_ok:
                    nums = _ocr_numbers(img, ocr)
                    out.used_ocr = True
                else:
                    out.ocr_missing = True
        out.by_page[idx + 1] = nums
        if progress is not None:
            progress(i + 1, len(pages))
    return out


def detect_offset(
    pdf: Path | PdfReader,
    *,
    max_samples: int = MAX_SAMPLES,
    use_ocr: bool = True,
    progress: Callable[[int, int], None] | None = None,
    cancel: threading.Event | None = None,
    ocr: "WindowsOcr | None" = None,
    early_stop: bool = True,
) -> OffsetResult:
    reader = pdf if isinstance(pdf, PdfReader) else PdfReader(str(pdf))
    if len(reader.pages) == 0:
        return OffsetResult(offset=None, reason="no_pages")
    cand = collect_candidates(reader, max_samples=max_samples, use_ocr=use_ocr,
                              progress=progress, cancel=cancel, ocr=ocr, early_stop=early_stop)
    if cand.cancelled:
        return OffsetResult(offset=None, reason="cancelled", sampled=len(cand.by_page))
    res = vote(cand.by_page, cand.num_pages)
    res.used_ocr = cand.used_ocr
    if res.offset is None and res.pages_with_numbers == 0 and cand.ocr_missing:
        res.reason = "ocr_unavailable"
    return res

"""validate_offset.py - offset 자동 감지를 정답이 있는 합성 스캔 책으로 검증한다.

    python tools/validate_offset.py collect   # 책을 만들고 쪽 번호 후보를 모아 JSON 에 저장 (OCR 이라 느림)
    python tools/validate_offset.py tune      # 저장한 후보로 투표 기준값 조합을 평가 (빠름)

합성 방식 (책갈피 툴 품질 검증 규칙)
    - 관측값 = 반사율 × 조명 + 센서 잡음. 조명 기울기는 종이와 잉크에 함께 곱하고, 잡음은 그 뒤에 더한다.
    - 살짝 기울여 스캔하고 JPEG(품질 80)으로 저장한다.
    - 앞부분: 표지, 판권, 로마 숫자 쪽수가 붙은 차례. 본문: 장 시작 쪽(쪽 번호 없음), 빈 쪽, 머리글.
    - 머리글에는 장 번호("Chapter 3", "제3장")가 들어가 쪽 번호와 헷갈리게 한다.
    - 감지가 실제로 여는 표본 페이지만 온전히 그리고, 나머지 페이지는 빈 종이 이미지로 둔다.
      표본 페이지가 같으므로 결과는 전체를 그린 책과 같다.
    - 음성 대조군: 쪽 번호가 없는 책, 두 쪽을 한 장에 스캔한 책, 연도만 있는 머리글. 정답은 "답 없음".

지표: 정답 / 오답 / 답 없음. 오답이 가장 나쁘다 (북마크가 전부 틀어진다). 답 없음은 직접 입력하면 된다.
"""

from __future__ import annotations

import io
import itertools
import json
import random
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

Image.init()
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import offset_detect as od  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

WORK = Path(__file__).resolve().parent / "_offset_work"
FONTS = {
    "batang": "C:/Windows/Fonts/batang.ttc",
    "malgun": "C:/Windows/Fonts/malgun.ttf",
    "times": "C:/Windows/Fonts/times.ttf",
    "arial": "C:/Windows/Fonts/arial.ttf",
    "simsun": "C:/Windows/Fonts/simsun.ttc",
}
PAGE_MM = (148, 210)


@dataclass
class BookSpec:
    name: str
    lang: str = "ko"            # ko / en / zh
    font: str = "batang"
    layout: str = "bottom_center"  # bottom_center / bottom_outer / top_header / dash_center / none / spread / years
    pages: int = 160
    offset: int = 8             # 책 1쪽 = PDF offset+1 쪽
    dpi: int = 300
    paper: int = 205            # 종이 밝기
    ink: int = 40               # 잉크 밝기
    noise: float = 6.0
    tilt: float = 0.6           # 기울기 (도)
    rotate_attr: int = 0        # /Rotate 로 저장 (이미지를 반대로 돌려 넣어 화면에선 똑바로)
    seed: int = 1
    expect: int | None = None   # 정답 offset. 음성 대조군은 None

    def __post_init__(self):
        if self.expect is None and self.layout not in ("none", "spread", "years"):
            self.expect = self.offset


# ---------------------------------------------------------------- 글 재료

def filler(lang: str, rng: random.Random, n_words: int) -> str:
    if lang == "ko":
        syl = "가나다라마바사아자차카타파하고노도로모보소오조초코토포호구누두루무부수우주의이기니디리미비시지는을를에서과와"
        return " ".join("".join(rng.choice(syl) for _ in range(rng.randint(1, 4))) for _ in range(n_words))
    if lang == "zh":
        ch = "的一是在不了有和人这中大为上个国我以要他时来用们生到作地于出就分对成会可主发年动同工也能下过子说产种面而方后多定行学法所民得经十三之进着等部度家电力里如水化高自二理起小物现实加量都两体制机当使点从业本去把性好应开它合还因由其些然前外天政四日那社义事平形相全表间样与关各重新线内数正心反你明看原又么利比或但质气第向道命此变条只没结解问意建月公无系军很情者最立代想已通并提直题党程展五果料象员革位入常文总次品式活设及管特件长求老头基资边流路级少图山统接知较将组见计别她手角期根论运农指几九区强放决西被干做必战先回则任取据处府"
        return " ".join("".join(rng.choice(ch) for _ in range(rng.randint(2, 6))) for _ in range(n_words))
    words = "data model system query table index design theory method result analysis value structure process network the of and to in is for with that on as are by this".split()
    return " ".join(rng.choice(words) for _ in range(n_words))


def chapter_title(lang: str, n: int) -> str:
    return {"ko": f"제{n}장 데이터 모델", "en": f"Chapter {n}  Data Models", "zh": f"第{n}章 数据模型"}[lang]


def roman(n: int) -> str:
    vals = [(10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
    out = ""
    for v, s in vals:
        while n >= v:
            out += s
            n -= v
    return out


# ---------------------------------------------------------------- 쪽 그리기

def _font(spec: BookSpec, pt: float) -> ImageFont.FreeTypeFont:
    size = max(6, round(pt / 72 * spec.dpi))
    path = FONTS[spec.font]
    if spec.lang == "zh" and spec.font not in ("simsun",):
        path = FONTS["simsun"]
    return ImageFont.truetype(path, size)


def draw_book_page(spec: BookSpec, pdf_index: int, rng: random.Random) -> Image.Image:
    """pdf_index: 0부터. 반사율 마스크(잉크 1, 종이 0)를 그린다."""
    W = round(PAGE_MM[0] / 25.4 * spec.dpi)
    H = round(PAGE_MM[1] / 25.4 * spec.dpi)
    if spec.layout == "spread":
        W *= 2
    mask = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(mask)
    mm = spec.dpi / 25.4
    body_f, num_f, head_f = _font(spec, 10), _font(spec, 9), _font(spec, 8.5)
    book_page = pdf_index - spec.offset + 1  # 인쇄 쪽수 (1부터). 0 이하면 앞부분

    def body(x0, x1, y0, y1):
        y = y0
        while y < y1:
            d.text((x0, y), filler(spec.lang, rng, 12)[: int((x1 - x0) / (body_f.size * 0.55))], font=body_f, fill=255)
            y += body_f.size * 1.7

    def number_text(n):
        return f"- {n} -" if spec.layout == "dash_center" else str(n)

    if spec.layout == "spread":
        for half, n in ((0, 2 * book_page), (1, 2 * book_page + 1)):
            ox = half * W // 2
            body(ox + 18 * mm, ox + W // 2 - 18 * mm, 22 * mm, H - 25 * mm)
            t = str(n)
            d.text((ox + W // 4 - d.textlength(t, font=num_f) / 2, H - 14 * mm), t, font=num_f, fill=255)
        return mask

    if book_page <= 0:  # 앞부분
        front = spec.offset + book_page - 1  # 0 부터
        if front == 0:
            d.text((20 * mm, 60 * mm), "Database Systems", font=_font(spec, 28), fill=255)
        elif front == 1:
            d.text((20 * mm, H - 60 * mm), "ISBN 978-89-000-0000-0  2024", font=body_f, fill=255)
        elif front >= 3:
            for i in range(10):
                d.text((22 * mm, (30 + i * 12) * mm), f"{chapter_title(spec.lang, i + 1)} ...... {i * 14 + 1}", font=body_f, fill=255)
            t = roman(front)
            d.text((W / 2 - d.textlength(t, font=num_f) / 2, H - 14 * mm), t, font=num_f, fill=255)
        return mask

    chapter = (book_page - 1) // 14 + 1
    opener = (book_page - 1) % 14 == 0
    blank = (book_page - 1) % 14 == 13 and chapter % 3 == 0
    if blank:
        return mask
    if opener:
        d.text((20 * mm, 50 * mm), chapter_title(spec.lang, chapter), font=_font(spec, 20), fill=255)
        body(20 * mm, W - 20 * mm, 80 * mm, H - 25 * mm)
        return mask  # 장 시작 쪽에는 쪽 번호가 없다

    body(20 * mm, W - 20 * mm, 24 * mm, H - 24 * mm)
    even = book_page % 2 == 0
    if spec.layout == "years":
        d.text((20 * mm, 10 * mm), f"{chapter_title(spec.lang, chapter)}   2024", font=head_f, fill=255)
        return mask
    if spec.layout == "none":
        return mask
    if spec.layout == "top_header":
        head = chapter_title(spec.lang, chapter)
        t = str(book_page)
        if even:
            d.text((18 * mm, 10 * mm), f"{t}", font=num_f, fill=255)
            d.text((30 * mm, 10 * mm), head, font=head_f, fill=255)
        else:
            d.text((W - 60 * mm, 10 * mm), head, font=head_f, fill=255)
            d.text((W - 18 * mm - d.textlength(t, font=num_f), 10 * mm), t, font=num_f, fill=255)
        return mask
    t = number_text(book_page)
    if spec.layout == "bottom_outer":
        x = 18 * mm if even else W - 18 * mm - d.textlength(t, font=num_f)
    else:
        x = W / 2 - d.textlength(t, font=num_f) / 2
        d.text((W - 70 * mm, 10 * mm), chapter_title(spec.lang, chapter), font=head_f, fill=255)
    d.text((x, H - 14 * mm), t, font=num_f, fill=255)
    return mask


def scan(spec: BookSpec, mask: Image.Image, rng: random.Random) -> Image.Image:
    """반사율 × 조명 + 잡음. 조명 기울기는 종이와 잉크에 함께 곱한다."""
    m = np.asarray(mask, dtype=np.float32) / 255.0
    refl = spec.paper * (1 - m) + spec.ink * m
    h, w = refl.shape
    gx = np.linspace(rng.uniform(0.82, 0.95), rng.uniform(1.0, 1.08), w, dtype=np.float32)
    gy = np.linspace(rng.uniform(0.95, 1.05), rng.uniform(0.9, 1.0), h, dtype=np.float32)
    obs = refl * gy[:, None] * gx[None, :]
    obs += np.random.default_rng(rng.randint(0, 1 << 30)).normal(0, spec.noise, obs.shape).astype(np.float32)
    img = Image.fromarray(np.clip(obs, 0, 255).astype(np.uint8), "L")
    return img.rotate(rng.uniform(-spec.tilt, spec.tilt), resample=Image.BILINEAR, fillcolor=int(spec.paper * 0.9))


def make_book(spec: BookSpec) -> Path:
    WORK.mkdir(exist_ok=True)
    out = WORK / f"{spec.name}.pdf"
    if out.exists():
        return out
    rng = random.Random(spec.seed)
    sampled = set(od.sample_pages(spec.pages))
    W = round(PAGE_MM[0] / 25.4 * spec.dpi) * (2 if spec.layout == "spread" else 1)
    H = round(PAGE_MM[1] / 25.4 * spec.dpi)
    blank = Image.new("L", (W // 8, H // 8), spec.paper)  # 표본이 아닌 쪽: 빈 종이 (쪽 크기만 맞춘다)
    imgs = []
    for i in range(spec.pages):
        if i in sampled:
            img = scan(spec, draw_book_page(spec, i, rng), rng)
        else:
            img = blank
        if spec.rotate_attr:
            img = img.rotate(spec.rotate_attr, expand=True)  # 반시계로 돌려 저장 → /Rotate 가 시계로 돌려 보여 준다
        imgs.append(img)
    buf = io.BytesIO()
    imgs[0].save(buf, "PDF", save_all=True, append_images=imgs[1:], resolution=spec.dpi, quality=80)
    if spec.rotate_attr or True:
        r = PdfReader(io.BytesIO(buf.getvalue()))
        w = PdfWriter(clone_from=r)
        for i, p in enumerate(w.pages):
            if i not in sampled:  # 빈 종이 쪽의 크기를 책 쪽 크기로 맞춘다
                p.scale_to(W / spec.dpi * 72, H / spec.dpi * 72) if not spec.rotate_attr else p.scale_to(H / spec.dpi * 72, W / spec.dpi * 72)
            if spec.rotate_attr:
                p.rotate(spec.rotate_attr)
        with out.open("wb") as fh:
            w.write(fh)
    return out


# ---------------------------------------------------------------- 세트

def train_set() -> list[BookSpec]:
    books = []
    for layout, seed in itertools.product(("bottom_center", "bottom_outer", "top_header", "dash_center"), (1, 2)):
        books.append(BookSpec(f"tr_{layout}_{seed}", layout=layout, seed=seed, offset=6 + seed * 3))
    for layout in ("none", "spread", "years"):
        books.append(BookSpec(f"tr_neg_{layout}", layout=layout, seed=3))
    return books


def validation_set() -> list[BookSpec]:
    books = []
    conds = [
        dict(dpi=150, paper=205, ink=45, noise=3, tag="150dpi"),
        dict(dpi=400, paper=130, ink=30, noise=10, tag="dark"),
        dict(dpi=300, paper=205, ink=150, noise=8, tag="faint"),
        dict(dpi=300, paper=205, ink=40, noise=6, rotate_attr=90, tag="rot90"),
    ]
    langs = [("ko", "malgun"), ("en", "times"), ("zh", "simsun")]
    seed = 10
    for (lang, font), layout, cond in itertools.product(langs, ("bottom_center", "bottom_outer", "top_header", "dash_center"), conds):
        seed += 1
        c = dict(cond)
        tag = c.pop("tag")
        books.append(BookSpec(f"va_{lang}_{layout}_{tag}", lang=lang, font=font, layout=layout, seed=seed,
                              offset=seed % 17, pages=random.Random(seed).choice([60, 120, 240, 400]), **c))
    for (lang, font), layout in itertools.product(langs, ("none", "spread", "years")):
        seed += 1
        books.append(BookSpec(f"va_neg_{lang}_{layout}", lang=lang, font=font, layout=layout, seed=seed, dpi=200))
    return books


# ---------------------------------------------------------------- 실행

def collect(which: str) -> None:
    books = train_set() if which == "train" else validation_set()
    out_json = WORK / f"candidates_{which}.json"
    done = json.loads(out_json.read_text(encoding="utf-8")) if out_json.exists() else {}
    ocr = od.WindowsOcr()
    for spec in books:
        if spec.name in done:
            continue
        pdf = make_book(spec)
        t0 = time.perf_counter()
        cand = od.collect_candidates(PdfReader(str(pdf)), ocr=ocr, early_stop=False)  # 후보를 전부 저장
        dt = time.perf_counter() - t0
        done[spec.name] = {"spec": asdict(spec), "by_page": {str(k): v for k, v in cand.by_page.items()},
                           "num_pages": cand.num_pages, "seconds": round(dt, 2)}
        out_json.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
        r = od.vote(cand.by_page, cand.num_pages)
        print(f"{spec.name:40s} expect={spec.expect!s:>4} got={r.offset!s:>4} votes={r.votes}/{r.pages_with_numbers} {dt:5.1f}s", flush=True)


def evaluate(which: str, min_votes: int, min_share: float, min_margin: int, verbose: bool = False,
             early: bool = False, tag: str = "") -> dict:
    data = json.loads((WORK / f"candidates_{which}{tag}.json").read_text(encoding="utf-8"))
    stats = {"correct": 0, "wrong": 0, "none_pos": 0, "none_neg": 0, "fp_neg": 0, "pos": 0, "neg": 0}
    for name, rec in data.items():
        expect = rec["spec"]["expect"]
        by_page = {int(k): v for k, v in rec["by_page"].items()}
        if early:  # 실제 감지와 같은 순서로 보다가 확실해지면 멈춘 것처럼 흉내 낸다
            seen = {}
            for p in od.spread_order(sorted(by_page)):
                if od._confident(seen):
                    break
                seen[p] = by_page[p]
            stats["pages_seen"] = stats.get("pages_seen", 0) + len(seen)
            by_page = seen
        r = od.vote(by_page, rec["num_pages"], min_votes=min_votes, min_share=min_share, min_margin=min_margin)
        if expect is None:
            stats["neg"] += 1
            stats["none_neg" if r.offset is None else "fp_neg"] += 1
        else:
            stats["pos"] += 1
            if r.offset is None:
                stats["none_pos"] += 1
            elif r.offset == expect:
                stats["correct"] += 1
            else:
                stats["wrong"] += 1
        if verbose and (r.offset != expect):
            print(f"   miss {name}: expect {expect} got {r.offset} votes {r.votes}/{r.pages_with_numbers} runner {r.runner_up}")
    return stats


def tune() -> None:
    grid = list(itertools.product((2, 3, 4, 5), (0.3, 0.4, 0.5, 0.6), (1, 2, 3)))
    rows = []
    for mv, ms, mm in grid:
        s = evaluate("train", mv, ms, mm)
        bad = s["wrong"] + s["fp_neg"]
        rows.append((bad, -s["correct"], (mv, ms, mm), s))
    rows.sort(key=lambda r: (r[0], r[1]))
    print("학습 세트 상위 조합 (오답+거짓양성, 정답):")
    for bad, negc, params, s in rows[:8]:
        print(f"  {params}  bad={bad} correct={-negc}/{s['pos']} none={s['none_pos']}")
    cur = (od.MIN_VOTES, od.MIN_SHARE, od.MIN_MARGIN)
    for label, params in (("현재 기준값", cur), ("학습 1위", rows[0][2])):
        for which in ("train", "validation"):
            if (WORK / f"candidates_{which}.json").exists():
                s = evaluate(which, *params, verbose=(which == "validation"))
                print(f"{label} {params} {which}: 정답 {s['correct']}/{s['pos']}, 오답 {s['wrong']}, 답없음 {s['none_pos']}, "
                      f"음성 대조군 거짓양성 {s['fp_neg']}/{s['neg']}")


def compare() -> None:
    """이전 수집(_v1)과 지금 수집을 책마다 비교하고, 조기 종료를 흉내 낸 결과도 낸다."""
    params = (od.MIN_VOTES, od.MIN_SHARE, od.MIN_MARGIN)
    for which in ("train", "validation"):
        old = json.loads((WORK / f"candidates_{which}_v1.json").read_text(encoding="utf-8"))
        new = json.loads((WORK / f"candidates_{which}.json").read_text(encoding="utf-8"))
        better = worse = fewer_votes = 0
        for name, rec in new.items():
            exp = rec["spec"]["expect"]
            ro = od.vote({int(k): v for k, v in old[name]["by_page"].items()}, rec["num_pages"])
            rn = od.vote({int(k): v for k, v in rec["by_page"].items()}, rec["num_pages"])
            ok_o, ok_n = ro.offset == exp, rn.offset == exp
            better += ok_n and not ok_o
            worse += ok_o and not ok_n
            if exp is not None and ok_o and ok_n and rn.votes < ro.votes - 2:
                fewer_votes += 1
                print(f"   표가 줄어든 책 {name}: {ro.votes} → {rn.votes}")
        print(f"{which}: 이전 대비 좋아진 책 {better}, 나빠진 책 {worse}, 표가 3표 넘게 준 책 {fewer_votes}")
        for early in (False, True):
            s = evaluate(which, *params, early=early)
            extra = f", 평균 {s['pages_seen'] / len(new):.1f}쪽만 봄" if early else ""
            print(f"   {'조기 종료' if early else '전체 표본'}: 정답 {s['correct']}/{s['pos']}, 오답 {s['wrong']}, "
                  f"답없음 {s['none_pos']}, 음성 거짓양성 {s['fp_neg']}/{s['neg']}{extra}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tune"
    if cmd == "compare":
        compare()
    elif cmd == "collect":
        collect(sys.argv[2] if len(sys.argv) > 2 else "train")
    else:
        tune()

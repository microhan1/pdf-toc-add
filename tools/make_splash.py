"""시작 그림(assets/splash.png)을 만든다 (2026-11-10, 허브 공통 지시서 「시작 그림」).

네 언어 화면의 프로그램 이름이 서로 달라서 글자는 공통인 「PDF」만 넣고, 나머지는 그림으로
(목차 줄이 있는 쪽 + 책갈피 띠). 크게 그린 뒤 줄여서 가장자리를 매끈하게 한다.

    python tools/make_splash.py assets/splash.png
"""
import sys

from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding="utf-8")
SCALE = 4
W, H = 300, 104
INK, ACCENT, RULE, PAGE, RIBBON = "#1f2328", "#2563eb", "#d9dee5", "#eaf1fe", "#dc2626"


def main(path: str) -> None:
    s = SCALE
    img = Image.new("RGB", (W * s, H * s), "white")
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W * s - 1, H * s - 1), outline=RULE, width=s)

    # 쪽 그림: 접힌 귀퉁이가 있는 종이
    x0, y0, x1, y1 = 34 * s, 18 * s, 80 * s, 86 * s
    fold = 10 * s
    d.polygon([(x0, y0), (x1 - fold, y0), (x1, y0 + fold), (x1, y1), (x0, y1)], fill=PAGE, outline=INK, width=s)
    d.polygon([(x1 - fold, y0), (x1 - fold, y0 + fold), (x1, y0 + fold)], fill="white", outline=INK, width=s)
    # 목차 줄: 번호 점 + 제목 줄 + 쪽 번호 토막
    for k in range(4):
        yy = y0 + (16 + k * 13) * s
        d.ellipse((x0 + 7 * s, yy, x0 + 10 * s, yy + 3 * s), fill=ACCENT)
        d.rectangle((x0 + 14 * s, yy, x0 + (14 + 16 - k * 2) * s, yy + 3 * s), fill=ACCENT)
        d.rectangle((x1 - 11 * s, yy, x1 - 6 * s, yy + 3 * s), fill=INK)
    # 책갈피 띠: 위쪽 가장자리에서 늘어진 붉은 리본
    rx = x0 + 32 * s
    d.polygon([(rx, y0 - 4 * s), (rx + 7 * s, y0 - 4 * s), (rx + 7 * s, y0 + 20 * s),
               (rx + 3.5 * s, y0 + 15 * s), (rx, y0 + 20 * s)], fill=RIBBON)

    font = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 40 * s)
    d.text((104 * s, 52 * s), "PDF", font=font, fill=INK, anchor="lm")
    # 「켜는 중」을 글자 없이: 점 세 개
    for k in range(3):
        cx = (214 + k * 14) * s
        d.ellipse((cx, 50 * s, cx + 6 * s, 56 * s), fill=ACCENT if k == 0 else RULE)

    img.resize((W, H), Image.LANCZOS).save(path, optimize=True)
    print(path)


if __name__ == "__main__":
    main(sys.argv[1])

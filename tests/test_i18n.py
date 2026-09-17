"""언어별 메시지 / 외국어 목차 표기 테스트."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import i18n  # noqa: E402
import pdf_toc_add as core  # noqa: E402


def test_all_languages_have_same_keys():
    ko, en, zh = (set(i18n.STRINGS[c]) for c in ("ko", "en", "zh"))
    assert ko == en == zh, {"ko-en": ko ^ en, "ko-zh": ko ^ zh}


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_every_string_formats_without_error(lang):
    """자리표시자 이름이 세 언어에서 같고, format 이 깨지지 않는지."""
    import string
    fmt = string.Formatter()
    for key, text in i18n.STRINGS[lang].items():
        fields = {f for _, f, _, _ in fmt.parse(text) if f}
        ref = {f for _, f, _, _ in fmt.parse(i18n.STRINGS["en"][key]) if f}
        assert fields == ref, f"{lang}:{key} placeholders {fields} != en {ref}"
        # 모든 자리표시자에 값을 넣어 format 이 되는지
        kw = {f.split(":")[0].split("!")[0]: 1 for f in fields}
        text.format(**kw)


@pytest.mark.parametrize("lang,needle", [("ko", "행"), ("en", "Line 1"), ("zh", "第 1 行")])
def test_parse_error_language(lang, needle):
    i18n.set_lang(lang)
    with pytest.raises(core.TocParseError) as ei:
        core.parse_toc("no page here\n")
    assert needle in str(ei.value)
    assert ei.value.lines == [1]


@pytest.mark.parametrize("lang", i18n.LANGS)
def test_validate_error_carries_line_numbers(lang):
    i18n.set_lang(lang)
    parsed = core.parse_toc("a, 1\nb, 50\nc, 60\n")
    with pytest.raises(core.TocParseError) as ei:
        core.validate(parsed.entries, 0, 12)
    assert ei.value.lines == [2, 3]


def test_warnings_carry_line_numbers():
    p = core.parse_toc("offset=1\na, 1-2\noffset=2\n")
    assert [w.lineno for w in p.warnings] == [2, 3]
    w = core.validate(core.parse_toc("a, 5\nb, 3\n").entries, 0, 12)
    assert w[0].lineno == 2


class TestForeignPageFormats:
    def test_english(self):
        p = core.parse_toc("Chapter 1 Introduction, 12\nChapter 2 p.25\nAppendix page 40\nIndex pp. 50\n")
        assert [(e.title, e.page) for e in core.flatten(p.entries)] == [
            ("Chapter 1 Introduction", 12), ("Chapter 2", 25), ("Appendix", 40), ("Index", 50),
        ]

    def test_chinese(self):
        p = core.parse_toc("第1章 绪论, 12\n第2章 背景 第25页\n    2.1 历史…… 26頁\n结论：40页\n")
        assert [(e.level, e.title, e.page) for e in core.flatten(p.entries)] == [
            (0, "第1章 绪论", 12), (0, "第2章 背景", 25), (1, "2.1 历史", 26), (0, "结论", 40),
        ]

    def test_chinese_fullwidth_offset_colon(self):
        assert core.parse_toc("offset：8\n第1章, 1\n").offset == 8

    @pytest.mark.parametrize("lang", i18n.LANGS)
    def test_gb18030_vs_cp949_autodetect(self, tmp_path, lang):
        """언어 설정과 무관하게 내용으로 인코딩을 판별해야 한다."""
        i18n.set_lang(lang)
        zh = "第1章 绪论, 12\n第2章 背景, 25\n"
        ko = "1장 서론, 12\n2장 배경, 25\n"
        (tmp_path / "gb.txt").write_bytes(zh.encode("gb18030"))
        (tmp_path / "kr.txt").write_bytes(ko.encode("cp949"))
        assert core.read_text(tmp_path / "gb.txt", None) == zh
        assert core.read_text(tmp_path / "kr.txt", None) == ko


def test_cli_lang_flag_changes_help_and_errors(tmp_path, capsys):
    toc = tmp_path / "t.txt"
    toc.write_text("bad line\n", encoding="utf-8")
    fake = tmp_path / "x.pdf"
    fake.write_text("nope", encoding="utf-8")
    assert core.main(["--lang", "en", str(fake), str(toc)]) == 1
    assert "Error: " in capsys.readouterr().err
    assert core.main(["--lang=zh", str(fake), str(toc)]) == 1
    assert "错误：" in capsys.readouterr().err

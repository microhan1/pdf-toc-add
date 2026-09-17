"""pdf_toc_gui.py - PDF 목차 넣기 GUI (한국어 / English / 中文).

- PDF: 창에 끌어다 놓거나 [찾아보기]
- 목차: 텍스트 파일을 끌어다 놓거나 [파일 열기], 또는 입력칸에 직접 타이핑
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import pdf_toc_add as core
from i18n import LANG_NAMES, LANGS, get_lang, save_lang, set_lang, tr

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _DND = True
except ImportError:  # pragma: no cover
    _DND = False

FONT_FAMILY = "Malgun Gothic"
FONT = (FONT_FAMILY, 10)
FONT_SMALL = (FONT_FAMILY, 9)
FONT_HEAD = (FONT_FAMILY, 11, "bold")
FONT_TITLE = (FONT_FAMILY, 15, "bold")

BG = "#ffffff"
BG_SOFT = "#f5f7fa"
BORDER = "#d9dee5"
FG = "#1f2328"
FG_MUTED = "#6b7280"
ACCENT = "#2563eb"
ACCENT_DARK = "#1d4ed8"
ACCENT_SOFT = "#eaf1fe"
OK_SOFT = "#e8f5ec"
OK_BORDER = "#bfe3c8"
OK_FG = "#166534"
ERR_SOFT = "#fdecec"
ERR_FG = "#b91c1c"
WARN_SOFT = "#fff4e0"
PAD = 20

TEXT_EXTS = {".txt", ".md", ".csv", ".text", ".toc", ".log"}


class App:
    def __init__(self, root: tk.Tk, pdf: str | None = None) -> None:
        self.root = root
        self.pdf_path: Path | None = None
        self.num_pages = 0
        self._log_lines: list[tuple[str, str | None]] = []  # 언어 바꿀 때 결과 칸을 다시 그리기 위해 보관

        root.geometry("720x800")
        root.minsize(640, 660)
        root.configure(bg=BG)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=3)  # 목차 입력칸
        root.rowconfigure(4, weight=2)  # 결과

        self._style()
        self._build_all()

        if _DND:
            root.drop_target_register(DND_FILES)
            root.dnd_bind("<<Drop>>", self._on_drop)

        if pdf:
            self.set_pdf(Path(pdf))

    # ------------------------------------------------------------ 스타일 / 공통 위젯

    def _style(self) -> None:
        st = ttk.Style()
        try:
            st.theme_use("vista")
        except tk.TclError:
            pass
        st.configure(".", font=FONT, background=BG, foreground=FG)
        st.configure("TFrame", background=BG)
        st.configure("TLabel", background=BG, foreground=FG)
        st.configure("Muted.TLabel", foreground=FG_MUTED, font=FONT_SMALL)
        st.configure("Head.TLabel", font=FONT_HEAD)
        st.configure("Title.TLabel", font=FONT_TITLE)
        st.configure("TButton", padding=(12, 5))
        st.configure("TSpinbox", padding=3)
        st.configure("TEntry", padding=4)
        st.configure("TCombobox", padding=3)
        st.configure("Sep.TFrame", background=BORDER)

    def _section(self, row: int, number: str, title: str, hint: str = "", grow: bool = False) -> ttk.Frame:
        """번호 배지 + 제목 헤더가 붙은 섹션을 만들고 본문 프레임을 돌려준다."""
        outer = ttk.Frame(self.root, padding=(PAD, 12, PAD, 4))
        outer.grid(row=row, column=0, sticky="nsew" if grow else "ew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        head = ttk.Frame(outer)
        head.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        tk.Label(
            head, text=number, width=2, font=(FONT_FAMILY, 9, "bold"),
            bg=ACCENT, fg="white", padx=2, pady=1,
        ).pack(side="left", padx=(0, 8))
        ttk.Label(head, text=title, style="Head.TLabel").pack(side="left")
        if hint:
            ttk.Label(head, text=hint, style="Muted.TLabel").pack(side="left", padx=(10, 0), pady=(3, 0))

        body = ttk.Frame(outer)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        return body

    def _boxed_text(self, parent: tk.Widget, **text_opts) -> tk.Text:
        """1px 테두리 안에 스크롤바 달린 Text 를 만든다."""
        box = tk.Frame(parent, bg=BORDER, padx=1, pady=1)
        box.grid(row=text_opts.pop("_row", 0), column=0, columnspan=2, sticky="nsew", pady=text_opts.pop("_pady", 0))
        box.columnconfigure(0, weight=1)
        box.rowconfigure(0, weight=1)
        txt = tk.Text(box, bd=0, padx=10, pady=8, highlightthickness=0, **text_opts)
        txt.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(box, orient="vertical", command=txt.yview)
        sb.grid(row=0, column=1, sticky="ns")
        txt.configure(yscrollcommand=sb.set)
        return txt

    # ------------------------------------------------------------ 화면 구성

    def _build_all(self) -> None:
        self.root.title(tr("app_title"))
        self._build_header()
        self._build_pdf_zone()
        self._build_toc_zone()
        self._build_options()
        self._build_log()

    def _build_header(self) -> None:
        f = ttk.Frame(self.root, padding=(PAD, 18, PAD, 10))
        f.grid(row=0, column=0, sticky="ew")
        f.columnconfigure(0, weight=1)
        ttk.Label(f, text=tr("app_title"), style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(f, text=tr("app_subtitle"), style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))

        lang_box = ttk.Frame(f)
        lang_box.grid(row=0, column=1, rowspan=2, sticky="ne")
        ttk.Label(lang_box, text=tr("lbl_language"), style="Muted.TLabel").pack(side="left", padx=(0, 6))
        self.lang_var = tk.StringVar(value=LANG_NAMES[get_lang()])
        cb = ttk.Combobox(
            lang_box, textvariable=self.lang_var, values=[LANG_NAMES[c] for c in LANGS],
            state="readonly", width=9, font=FONT_SMALL,
        )
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", self._on_lang_change)
        ttk.Frame(self.root, style="Sep.TFrame", height=1).grid(row=0, column=0, sticky="sew", padx=PAD)

    def _build_pdf_zone(self) -> None:
        body = self._section(1, "1", tr("sec_pdf"), tr("sec_pdf_hint_dnd") if _DND else tr("sec_pdf_hint_nodnd"))

        self._pdf_hint = tr("pdf_drop_hint") if _DND else tr("pdf_click_hint")
        self.pdf_label = tk.Label(
            body, text=self._pdf_hint, height=3, font=FONT, cursor="hand2",
            bg=BG_SOFT, fg=FG_MUTED, bd=0, highlightthickness=1, highlightbackground=BORDER,
        )
        self.pdf_label.grid(row=0, column=0, sticky="ew")
        self.pdf_label.bind("<Button-1>", lambda _e: self.browse_pdf())
        ttk.Button(body, text=tr("btn_browse"), command=self.browse_pdf).grid(row=0, column=1, padx=(10, 0), sticky="ns")
        if self.pdf_path:
            self._show_pdf_loaded()

    def _build_toc_zone(self) -> None:
        body = self._section(2, "2", tr("sec_toc"), tr("sec_toc_hint"), grow=True)
        body.rowconfigure(1, weight=1)

        bar = ttk.Frame(body)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Button(bar, text=tr("btn_open_txt"), command=self.browse_toc).pack(side="left")
        ttk.Button(bar, text=tr("btn_example"), command=lambda: self.set_toc_text(tr("example_toc"))).pack(side="left", padx=(6, 0))
        ttk.Button(bar, text=tr("btn_clear"), command=lambda: self.set_toc_text("")).pack(side="left", padx=(6, 0))
        if _DND:
            ttk.Label(bar, text=tr("toc_drop_hint"), style="Muted.TLabel").pack(side="right")

        self.toc_text = self._boxed_text(
            body, _row=1, font=FONT, wrap="none", undo=True, height=10,
            bg=BG, fg=FG, insertbackground=FG, selectbackground=ACCENT_SOFT, selectforeground=FG,
        )
        self.toc_text.tag_configure("badline", background=ERR_SOFT)
        self.toc_text.tag_configure("warnline", background=WARN_SOFT)
        self.toc_text.bind("<KeyRelease>", lambda _e: self._clear_marks())

    def _build_options(self) -> None:
        body = self._section(3, "3", tr("sec_settings"))
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=1)

        ttk.Label(body, text=tr("lbl_offset")).grid(row=0, column=0, sticky="w")
        row = ttk.Frame(body)
        row.grid(row=0, column=1, sticky="w", padx=(12, 0))
        if not hasattr(self, "offset_var"):
            self.offset_var = tk.StringVar(value="0")
        ttk.Spinbox(row, from_=-9999, to=99999, width=6, textvariable=self.offset_var, font=FONT).pack(side="left")
        ttk.Label(row, text=tr("offset_hint"), style="Muted.TLabel").pack(side="left", padx=(10, 0))

        ttk.Label(body, text=tr("lbl_output")).grid(row=1, column=0, sticky="w", pady=(8, 0))
        out = ttk.Frame(body)
        out.grid(row=1, column=1, sticky="ew", padx=(12, 0), pady=(8, 0))
        out.columnconfigure(0, weight=1)
        if not hasattr(self, "out_var"):
            self.out_var = tk.StringVar()
        ttk.Entry(out, textvariable=self.out_var, font=FONT).grid(row=0, column=0, sticky="ew")
        ttk.Button(out, text=tr("btn_change"), command=self.browse_out).grid(row=0, column=1, padx=(6, 0))

        btns = ttk.Frame(body)
        btns.grid(row=2, column=0, columnspan=2, sticky="e", pady=(14, 4))
        ttk.Button(btns, text=tr("btn_preview"), command=self.preview).pack(side="left", padx=(0, 8))
        self.run_btn = tk.Button(
            btns, text=tr("btn_build"), command=self.build, font=(FONT_FAMILY, 10, "bold"),
            bg=ACCENT, fg="white", activebackground=ACCENT_DARK, activeforeground="white",
            bd=0, padx=22, pady=6, cursor="hand2",
        )
        self.run_btn.pack(side="left")

    def _build_log(self) -> None:
        ttk.Frame(self.root, style="Sep.TFrame", height=1).grid(row=4, column=0, sticky="new", padx=PAD)
        body = self._section(4, "✓", tr("sec_result"), tr("sec_result_hint"), grow=True)
        body.rowconfigure(0, weight=1)
        self.log = self._boxed_text(
            body, _row=0, _pady=(0, PAD - 4), font=FONT_SMALL, height=7, state="disabled",
            bg=BG_SOFT, fg=FG, wrap="word",
        )
        self.log.tag_configure("err", foreground=ERR_FG)
        self.log.tag_configure("errhead", foreground=ERR_FG, font=(FONT_FAMILY, 9, "bold"))
        self.log.tag_configure("warn", foreground="#b45309")
        self.log.tag_configure("ok", foreground=OK_FG, font=(FONT_FAMILY, 9, "bold"))
        self.log.tag_configure("muted", foreground=FG_MUTED)

    # ------------------------------------------------------------ 언어 변경

    def _on_lang_change(self, _event=None) -> None:
        name = self.lang_var.get()
        code = next((c for c in LANGS if LANG_NAMES[c] == name), "en")
        if code == get_lang():
            return
        set_lang(code)
        save_lang(code)
        self._rebuild()

    def _rebuild(self) -> None:
        """언어가 바뀌면 입력 상태를 보존한 채 화면을 다시 그린다."""
        toc = self.toc_text.get("1.0", "end-1c")
        bad = self.toc_text.tag_ranges("badline")
        warn = self.toc_text.tag_ranges("warnline")
        log_lines = list(self._log_lines)
        for child in self.root.winfo_children():
            child.destroy()
        self._build_all()
        self.toc_text.insert("1.0", toc)
        for i in range(0, len(bad), 2):
            self.toc_text.tag_add("badline", str(bad[i]), str(bad[i + 1]))
        for i in range(0, len(warn), 2):
            self.toc_text.tag_add("warnline", str(warn[i]), str(warn[i + 1]))
        self._log_lines = []
        for text, tag in log_lines:
            self.write_log(text, tag)

    # ------------------------------------------------------------ 입력 처리

    def _on_drop(self, event) -> None:
        paths = [Path(p) for p in self.root.tk.splitlist(event.data)]
        pdfs = [p for p in paths if p.suffix.lower() == ".pdf"]
        others = [p for p in paths if p.suffix.lower() != ".pdf"]

        if pdfs:
            self.set_pdf(pdfs[0])
            if len(pdfs) > 1:
                self.write_log(tr("warn_multi_pdf", n=len(pdfs), name=pdfs[0].name), "warn")
        for p in others:
            if p.is_dir():
                self.write_log(tr("err_is_dir", name=p.name), "err")
            elif p.is_file():
                self.load_toc_file(p)
            else:
                self.write_log(tr("err_not_found", path=p), "err")

    def browse_pdf(self) -> None:
        f = filedialog.askopenfilename(title=tr("dlg_pdf"), filetypes=[("PDF", "*.pdf"), (tr("ft_all"), "*.*")])
        if f:
            self.set_pdf(Path(f))

    def _show_pdf_loaded(self) -> None:
        self.pdf_label.configure(
            text=tr("pdf_pages", name=self.pdf_path.name, n=self.num_pages),
            fg=OK_FG, bg=OK_SOFT, highlightbackground=OK_BORDER,
        )

    def set_pdf(self, path: Path) -> None:
        try:
            self.num_pages = len(core.open_pdf(path).pages)
        except core.ToolError as exc:
            self.pdf_path = None
            self.num_pages = 0
            self.pdf_label.configure(text=self._pdf_hint, fg=FG_MUTED, bg=BG_SOFT, highlightbackground=BORDER)
            self.out_var.set("")
            self.show_error(tr("err_pdf_open"), str(exc))
            return
        self.pdf_path = path
        self._show_pdf_loaded()
        self.out_var.set(str(path.with_name(f"{path.stem}_toc.pdf")))
        self.write_log(tr("log_pdf", path=path, n=self.num_pages), clear=True)
        if 0 < self.num_pages < 5:
            self.write_log(tr("warn_few_pages", n=self.num_pages), "warn")

    def browse_toc(self) -> None:
        f = filedialog.askopenfilename(
            title=tr("dlg_toc"),
            initialdir=str(self.pdf_path.parent) if self.pdf_path else None,
            filetypes=[(tr("ft_text"), "*.txt"), (tr("ft_all"), "*.*")],
        )
        if f:
            self.load_toc_file(Path(f))

    def load_toc_file(self, path: Path) -> None:
        try:
            text = core.read_text(path, None)
        except core.ToolError as exc:
            self.show_error(tr("err_toc_read"), str(exc))
            return
        self.set_toc_text(text)
        self.write_log(tr("log_toc", path=path), clear=True)
        if path.suffix.lower() not in TEXT_EXTS:
            self.write_log(tr("warn_not_txt", name=path.name), "warn")
        # 파일 안의 offset= 은 즉시 반영. 형식 오류는 미리보기에서 자세히 알려준다.
        try:
            parsed = core.parse_toc(text)
        except core.ToolError:
            self.write_log(tr("warn_toc_format"), "warn")
            return
        if parsed.offset is not None:
            self.offset_var.set(str(parsed.offset))
            self.write_log(tr("log_offset_applied", n=parsed.offset), "muted")
        for w in parsed.warnings:
            self.write_log(tr("cli_warn") + w, "warn")

    def set_toc_text(self, text: str) -> None:
        self.toc_text.delete("1.0", "end")
        self.toc_text.insert("1.0", text)
        self._clear_marks()

    def _clear_marks(self) -> None:
        self.toc_text.tag_remove("badline", "1.0", "end")
        self.toc_text.tag_remove("warnline", "1.0", "end")

    def _mark_lines(self, lines, tag: str) -> None:
        """행 번호 목록의 줄에 색을 칠한다."""
        nums = sorted({n for n in lines if n})
        for n in nums:
            self.toc_text.tag_add(tag, f"{n}.0", f"{n}.0 lineend+1c")
        if nums and tag == "badline":
            self.toc_text.see(f"{nums[0]}.0")

    def browse_out(self) -> None:
        f = filedialog.asksaveasfilename(
            title=tr("dlg_out"), defaultextension=".pdf", filetypes=[("PDF", "*.pdf")],
            initialfile=Path(self.out_var.get()).name if self.out_var.get() else "output_toc.pdf",
        )
        if f:
            self.out_var.set(f)

    # ------------------------------------------------------------ 로그 / 오류 표시

    def write_log(self, text: str, tag: str | None = None, clear: bool = False) -> None:
        self.log.configure(state="normal")
        if clear:
            self.log.delete("1.0", "end")
            self._log_lines = []
        self.log.insert("end", text + "\n", tag or ())
        self._log_lines.append((text, tag))
        self.log.see("end")
        self.log.configure(state="disabled")

    def show_error(self, title: str, detail: str, clear: bool = True) -> None:
        """결과 칸에 제목(굵게) + 상세를 쓴다. 팝업 대신 결과 칸으로 시선을 모은다."""
        self.write_log(f"✖ {title}", "errhead", clear=clear)
        for line in detail.splitlines():
            self.write_log(line, "err")
        self.log.see("1.0")
        self.root.bell()

    # ------------------------------------------------------------ 실행

    def _collect(self):
        """입력을 검사해 (entries, offset) 을 돌려주거나, 문제를 결과 칸에 쓰고 None."""
        problems: list[tuple[str, str]] = []
        self._clear_marks()

        if not self.pdf_path:
            problems.append((tr("err_no_pdf"), tr("err_no_pdf_detail")))

        text = self.toc_text.get("1.0", "end")
        parsed = None
        if not text.strip():
            problems.append((tr("err_toc_empty"), tr("err_toc_empty_detail")))
        else:
            try:
                parsed = core.parse_toc(text)
            except core.ToolError as exc:
                problems.append((tr("err_toc_format"), str(exc)))
                self._mark_lines(exc.lines, "badline")

        offset = None
        raw_offset = self.offset_var.get().strip()
        try:
            offset = int(raw_offset or "0")
        except ValueError:
            problems.append((tr("err_offset"), tr("err_offset_detail", v=raw_offset)))

        if problems:
            for i, (t, d) in enumerate(problems):
                self.show_error(t, d, clear=(i == 0))
            return None

        try:
            warnings = parsed.warnings + core.validate(parsed.entries, offset, self.num_pages)
        except core.ToolError as exc:
            self.show_error(tr("err_range"), str(exc))
            self._mark_lines(exc.lines, "badline")
            return None

        flat = core.flatten(parsed.entries)
        self.write_log(tr("summary", n=len(flat), offset=offset, total=self.num_pages), clear=True)
        for e in flat:
            self.write_log("    " * e.level + tr("tree_gui", title=e.title, pdf=e.page + offset))
        for w in warnings:
            self.write_log(tr("cli_warn") + w, "warn")
        self._mark_lines([getattr(w, "lineno", None) for w in warnings], "warnline")
        self.log.see("1.0")  # 목록은 처음부터 보이도록
        return parsed.entries, offset

    def preview(self) -> None:
        self._collect()

    def build(self) -> None:
        got = self._collect()
        if not got:
            return
        entries, offset = got
        raw_out = self.out_var.get().strip()
        out = Path(raw_out) if raw_out else self.pdf_path.with_name(f"{self.pdf_path.stem}_toc.pdf")
        if out.suffix.lower() != ".pdf":
            out = out.with_suffix(".pdf")
            self.out_var.set(str(out))
        try:
            same = out.resolve() == self.pdf_path.resolve()
        except OSError:
            same = False
        if same:
            self.show_error(tr("err_same"), tr("err_same_detail"), clear=False)
            return
        if out.exists() and not messagebox.askyesno(tr("dlg_overwrite_title"), tr("dlg_overwrite", name=out.name)):
            self.write_log(tr("log_cancelled"), "muted")
            return
        try:
            core.build_pdf(self.pdf_path, out, entries, offset, keep_existing=False)
        except core.ToolError as exc:
            self.show_error(tr("err_build"), str(exc), clear=False)
            return
        except Exception as exc:  # 예상 못 한 오류도 화면에 남긴다
            self.show_error(tr("err_unexpected"), f"{type(exc).__name__}: {exc}", clear=False)
            return
        self.write_log(tr("log_done", path=out), "ok")
        messagebox.showinfo(tr("dlg_done_title"), tr("dlg_done", path=out))


def run(pdf: str | None = None) -> int:
    root = TkinterDnD.Tk() if _DND else tk.Tk()
    App(root, pdf)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else None))

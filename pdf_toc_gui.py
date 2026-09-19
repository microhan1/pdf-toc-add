"""pdf_toc_gui.py - PDF 목차 넣기 GUI (한국어 / English / 中文).

- PDF: 창에 끌어다 놓거나 [찾아보기]
- 목차: 텍스트 파일을 끌어다 놓거나 [파일 열기], 또는 입력칸에 직접 타이핑
"""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import offset_detect
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
    def __init__(self, root: tk.Tk, pdf: str | None = None, toc: str | None = None) -> None:
        self.root = root
        self.pdf_path: Path | None = None
        self.num_pages = 0
        self._log_lines: list[tuple[str, str | None]] = []  # 언어 바꿀 때 결과 칸을 다시 그리기 위해 보관
        # 목차 입력칸의 offset= 값 중 마지막으로 칸(스핀박스)에 반영한 값. 입력칸의 값이 이것과 달라지면
        # 사용자가 입력칸에서 고친 것이므로 칸에 반영한다. 칸만 고쳤으면 칸 값을 그대로 쓴다.
        self._synced_text_offset: int | None = None
        # offset 자동 감지 (백그라운드 스레드). 세대 번호로 밀려난 결과를 버린다.
        self._detect_gen = 0
        self._detect_thread: threading.Thread | None = None
        self._detect_cancel = threading.Event()
        self._closing = False
        self._detect_queue: queue.Queue = queue.Queue()
        self._polling = False

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

        root.protocol("WM_DELETE_WINDOW", self._on_close)

        if pdf:
            self.set_pdf(Path(pdf))
        if toc:
            self.load_toc_file(Path(toc))

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
        self.lang_cb = cb
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
        self.detect_btn = ttk.Button(row, text=tr("btn_detect"), command=lambda: self.start_detect(auto=False))
        self.detect_btn.pack(side="left", padx=(8, 0))
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
        self.preview_btn = ttk.Button(btns, text=tr("btn_preview"), command=self.preview)
        self.preview_btn.pack(side="left", padx=(0, 8))
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
        self.start_detect(auto=True)

    # ------------------------------------------------------------ offset 자동 감지

    def start_detect(self, auto: bool) -> None:
        """PDF 를 넣으면 자동으로(auto=True), [자동 감지] 를 누르면 직접(auto=False) 돌린다."""
        if not self.pdf_path:
            self.show_error(tr("err_no_pdf"), tr("err_no_pdf_detail"))
            return
        self._detect_cancel.set()  # 이전 감지가 돌고 있으면 멈추게 한다
        self._detect_cancel = threading.Event()
        self._detect_gen += 1
        gen, cancel, path = self._detect_gen, self._detect_cancel, self.pdf_path
        n = len(offset_detect.sample_pages(self.num_pages))
        self.write_log(tr("detect_start", n=n), "muted")
        self._set_busy(True)

        # 작업 스레드는 Tk 를 직접 건드리지 않고 큐에 넣기만 한다. 메인 스레드가 _poll_detect 로 꺼낸다.
        # (다른 스레드에서 root.after 를 부르면 메인 루프 밖에서 "main thread is not in main loop" 로 죽는다)
        q = self._detect_queue

        def work():
            try:
                res = offset_detect.detect_offset(
                    path, progress=lambda i, total: q.put(("progress", gen, i, total)), cancel=cancel)
                q.put(("done", gen, auto, res, None))
            except Exception as exc:  # 이상한 PDF 하나 때문에 창이 죽지 않게
                q.put(("done", gen, auto, None, f"{type(exc).__name__}: {exc}"))

        self._detect_thread = threading.Thread(target=work, daemon=True)
        self._detect_thread.start()
        if not self._polling:
            self._polling = True
            self.root.after(50, self._poll_detect)

    def _poll_detect(self) -> None:
        if self._closing:
            self._polling = False
            return
        while True:
            try:
                msg = self._detect_queue.get_nowait()
            except queue.Empty:
                break
            if msg[0] == "progress":
                self._detect_progress(*msg[1:])
            else:
                self._detect_done(*msg[1:])
        if self._detect_thread is not None and (self._detect_thread.is_alive() or not self._detect_queue.empty()):
            self.root.after(50, self._poll_detect)
        else:
            self._polling = False

    def _detect_progress(self, gen: int, i: int, total: int) -> None:
        if gen != self._detect_gen or self._closing:
            return
        text = tr("detect_progress", i=i, n=total)
        # 진행 줄은 마지막 줄 하나를 계속 바꿔 쓴다
        if self._log_lines and self._log_lines[-1][1] == "progress":
            self.log.configure(state="normal")
            self.log.delete("end-2l", "end-1c")
            self.log.configure(state="disabled")
            self._log_lines.pop()
        self.write_log(text, "progress")

    def _detect_done(self, gen: int, auto: bool, res, err: str | None) -> None:
        if gen != self._detect_gen or self._closing:
            return
        self._set_busy(False)
        if self._log_lines and self._log_lines[-1][1] == "progress":
            self.log.configure(state="normal")
            self.log.delete("end-2l", "end-1c")
            self.log.configure(state="disabled")
            self._log_lines.pop()
        if err is not None:
            self.show_error(tr("detect_fail_title"), tr("detect_error", err=err) + "\n" + tr("detect_fail_hint"), clear=False)
            return
        if res.offset is None:
            if res.reason == "cancelled":
                self.write_log(tr("detect_cancelled"), "muted")
                return
            detail = {
                "no_numbers": tr("detect_fail_no_numbers"),
                "inconsistent": tr("detect_fail_inconsistent", votes=res.votes, pages=res.pages_with_numbers),
                "ocr_unavailable": tr("detect_fail_ocr_unavailable"),
            }.get(res.reason, tr("detect_fail_no_pages"))
            self.write_log(tr("detect_fail_title"), "warn")
            self.write_log(detail, "warn")
            self.write_log(tr("detect_fail_hint"), "muted")
            if not auto:
                self.root.bell()
            return
        how = tr("detect_how_ocr") if res.used_ocr else tr("detect_how_text")
        self.write_log(tr("detect_ok", offset=res.offset, votes=res.votes, pages=res.pages_with_numbers, how=how), "ok")
        for pdf_page, printed in res.evidence[:3]:
            self.write_log(tr("detect_evidence", pdf=pdf_page, page=printed), "muted")
        current = self.offset_var.get().strip()
        # 자동 실행일 때, 목차의 offset= 이 이미 칸을 채웠고 감지값과 다르면 덮어쓰지 않고 알리기만 한다
        if auto and self._synced_text_offset is not None and current != str(res.offset):
            self.write_log(tr("detect_kept", current=current, found=res.offset), "warn")
            return
        if current != str(res.offset):
            self.offset_var.set(str(res.offset))
        self.write_log(tr("detect_applied", offset=res.offset), "muted")

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for w in (self.detect_btn, self.preview_btn, self.run_btn):
            try:
                w.configure(state=state)
            except tk.TclError:
                pass
        try:
            self.lang_cb.configure(state="disabled" if busy else "readonly")
        except tk.TclError:
            pass

    def _on_close(self) -> None:
        """창 닫기: 감지 스레드를 멈추게 하고, 끝날 때까지 기다렸다가 닫는다."""
        self._closing = True
        self._detect_cancel.set()
        if self._detect_thread is not None and self._detect_thread.is_alive():
            self.root.after(100, self._on_close)
            return
        self.root.destroy()

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
        self._sync_text_offset(parsed.offset)
        for w in parsed.warnings:
            self.write_log(tr("cli_warn") + w, "warn")

    def _sync_text_offset(self, text_offset: int | None) -> None:
        """입력칸의 offset= 값이 새로 생기거나 바뀌었으면 offset 칸에 반영한다."""
        if text_offset is None or text_offset == self._synced_text_offset:
            return
        self._synced_text_offset = text_offset
        if self.offset_var.get().strip() != str(text_offset):
            self.offset_var.set(str(text_offset))
            self.write_log(tr("log_offset_applied", n=text_offset), "muted")

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
            else:
                self._sync_text_offset(parsed.offset)

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
        if not out.is_absolute():
            out = self.pdf_path.parent / out  # 이름만 적었으면 작업 폴더가 아니라 원본 PDF 옆에 쓴다
        if out.suffix.lower() != ".pdf":
            out = out.with_name(out.name + ".pdf")  # with_suffix 는 "Book_v2.0" 의 ".0" 을 지워 버린다
        if str(out) != raw_out:
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


def run(pdf: str | None = None, toc: str | None = None) -> int:
    root = TkinterDnD.Tk() if _DND else tk.Tk()
    App(root, pdf, toc)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else None))

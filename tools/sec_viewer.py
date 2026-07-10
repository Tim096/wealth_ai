r"""One-click SEC 10-K viewer — verify Task 2 yourself.

Launch: double-click 驗證SEC.bat, or:  .venv\Scripts\python tools\sec_viewer.py

Type a ticker (AAPL / INTC / XOM / JPM / C …), press 抽取. It fetches the
latest 10-K, extracts Items 1-16, runs the XBRL oracle (Item 8) and the
per-item topic oracle, and lists every item with its status / confidence /
provenance / independent checks. Click any item to READ the actual extracted
source-exact text — so you can confirm it is the filing's real text, the
status is honest, and the wrapper (Intel/Citi) handling works.
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from tkinter import scrolledtext

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("SEC_EDGAR_USER_AGENT", "ai-coding-test-2026 viewer contact@example.com")

from sec_core.fetcher import EdgarFetcher            # noqa: E402
from sec_core.main_doc import pick_main_document      # noqa: E402
from sec_core.pipeline import extract_from_html       # noqa: E402
from sec_core.resolver import FilingResolver, FilingRef  # noqa: E402
from sec_core.xbrl import certify_item8               # noqa: E402

_STATUS_COLOR = {
    "pass": "#4bbd80", "partial": "#45b9c6", "incorporated_by_reference": "#d9ad55",
    "ambiguous": "#d9ad55", "missing": "#7f8b99", "reserved": "#7f8b99",
    "unsupported": "#e07a6d",
}


class SecViewer:
    def __init__(self) -> None:
        self.q: queue.Queue = queue.Queue()
        self.result = None
        self._build()
        self.root.after(80, self._pump)
        self.root.mainloop()

    def _build(self) -> None:
        self.root = tk.Tk()
        self.root.title("SEC 10-K Viewer · 自我驗證")
        self.root.geometry("1080x680")
        self.root.configure(bg="#0f141b")

        top = tk.Frame(self.root, bg="#0f141b")
        top.pack(fill=tk.X, padx=10, pady=8)
        tk.Label(top, text="Ticker / CIK", bg="#0f141b", fg="#93a0b0").pack(side=tk.LEFT)
        self.inp = tk.Entry(top, bg="#141b25", fg="#e7ecf2", insertbackground="#e7ecf2",
                            relief=tk.FLAT, width=18, font=("Segoe UI", 11))
        self.inp.insert(0, "INTC")
        self.inp.pack(side=tk.LEFT, padx=(6, 8), ipady=4)
        self.inp.bind("<Return>", lambda e: self._go())
        self.btn = tk.Button(top, text="抽取 ▶", command=self._go, bg="#45b9c6", fg="#0f141b",
                             relief=tk.FLAT, font=("Segoe UI", 10, "bold"), padx=14)
        self.btn.pack(side=tk.LEFT)
        self.filebtn = tk.Button(top, text="開啟檔案 📁", command=self._open_file, bg="#243040",
                                 fg="#e7ecf2", relief=tk.FLAT, font=("Segoe UI", 10), padx=12)
        self.filebtn.pack(side=tk.LEFT, padx=(8, 0))
        self.status = tk.Label(top, text="輸入代號(INTC/AAPL/XOM)按 Enter,或「開啟檔案」丟自己的 10-K",
                               bg="#0f141b", fg="#93a0b0")
        self.status.pack(side=tk.LEFT, padx=12)

        pan = tk.PanedWindow(self.root, bg="#0f141b", sashwidth=6)
        pan.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        left = tk.Frame(pan, bg="#0f141b")
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background="#141b25", fieldbackground="#141b25",
                        foreground="#e7ecf2", rowheight=24, font=("Consolas", 10))
        style.configure("Treeview.Heading", background="#0f141b", foreground="#93a0b0")
        cols = ("status", "conf", "xbrl", "topic")
        self.tree = ttk.Treeview(left, columns=cols, show="tree headings", height=24)
        self.tree.heading("#0", text="Item")
        self.tree.column("#0", width=70, anchor="w")
        for c, w in zip(cols, (200, 55, 90, 90)):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        pan.add(left, width=560)

        right = tk.Frame(pan, bg="#0f141b")
        self.hdr = tk.Label(right, text="", bg="#0f141b", fg="#45b9c6", justify=tk.LEFT,
                            anchor="w", font=("Consolas", 10))
        self.hdr.pack(fill=tk.X)
        self.txt = scrolledtext.ScrolledText(right, wrap=tk.WORD, bg="#0f141b", fg="#e7ecf2",
                                             font=("Consolas", 10), relief=tk.FLAT, padx=10, pady=8)
        self.txt.pack(fill=tk.BOTH, expand=True)
        pan.add(right)

    def _set_status(self, msg: str) -> None:
        self.q.put(("status", msg))

    def _pump(self) -> None:
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "status":
                    self.status.configure(text=payload)
                elif kind == "result":
                    self._populate(payload)
                    self.btn.configure(state=tk.NORMAL, text="抽取 ▶")
                    self.filebtn.configure(state=tk.NORMAL, text="開啟檔案 📁")
                elif kind == "error":
                    self.status.configure(text="✗ " + payload)
                    self.btn.configure(state=tk.NORMAL, text="抽取 ▶")
                    self.filebtn.configure(state=tk.NORMAL, text="開啟檔案 📁")
                elif kind == "filebtn":
                    self.filebtn.configure(state=tk.NORMAL, text="開啟檔案 📁")
        except queue.Empty:
            pass
        self.root.after(80, self._pump)

    def _go(self) -> None:
        q = self.inp.get().strip()
        if not q:
            return
        self.btn.configure(state=tk.DISABLED, text="抽取中…")
        self._set_status(f"抓取 {q} 最新 10-K…")
        threading.Thread(target=self._work, args=(q,), daemon=True).start()

    def _open_file(self) -> None:
        path = filedialog.askopenfilename(
            title="選一份 10-K(HTML 或 TXT)",
            filetypes=[("10-K filing", "*.htm *.html *.txt"), ("所有檔案", "*.*")])
        if not path:
            return
        self.btn.configure(state=tk.DISABLED)
        self.filebtn.configure(state=tk.DISABLED, text="讀取中…")
        self._set_status(f"抽取本機檔案 {Path(path).name}…")
        threading.Thread(target=self._work_file, args=(path,), daemon=True).start()

    def _work_file(self, path: str) -> None:
        try:
            raw = Path(path).read_text(encoding="utf-8", errors="replace")
            result = extract_from_html(raw, Path(path).stem)
            self.result = result

            class _Ref:  # minimal shim for the header
                form = "upload"; report_date = Path(path).name
            self.q.put(("result", {"ticker": Path(path).name, "ref": _Ref(),
                                    "cls": result.filing_class, "xbrl": ""}))
            npass = sum(1 for s in result.segments if s.status == "pass")
            self._set_status(f"{Path(path).name} · class={result.filing_class} · {npass} items pass"
                             " · (本機檔案無 CIK,略過 XBRL 認證)")
        except Exception as e:  # noqa: BLE001
            self.q.put(("error", f"{type(e).__name__}: {e}"))
        finally:
            self.q.put(("filebtn", ""))

    def _work(self, q: str) -> None:
        try:
            fetcher = EdgarFetcher(cache_dir=ROOT / "data" / "raw_filings")
            resolver = FilingResolver(fetcher)
            cik = int(q) if q.isdigit() else resolver.cik_for_ticker(q)
            filings = resolver.annual_filings(cik)
            ref = next((f for f in filings if not f.is_amendment), None)
            if ref is None:
                self.q.put(("error", f"{q} 找不到 10-K")); return
            resolver.load_files(ref)
            best = pick_main_document(ref)
            self._set_status(f"抽取 {q} {ref.accession}…")
            raw = fetcher.get(ref.file_url(best.name)).content.decode("utf-8", errors="replace")
            result = extract_from_html(raw, f"{q}-{ref.accession}")
            xbrl = ""
            item8 = next((s for s in result.segments if s.item_code == "8"), None)
            if item8 is not None and item8.end_offset > item8.start_offset:
                try:
                    chk = certify_item8(result, fetcher, cik, ref.accession)
                    xbrl = chk.verdict
                except Exception:  # noqa: BLE001
                    xbrl = ""
            self.result = result
            self.q.put(("result", {"ticker": q, "ref": ref, "cls": result.filing_class, "xbrl": xbrl}))
            self._set_status(f"{q} · {ref.form} {ref.report_date} · class={result.filing_class}"
                             + (f" · Item8 XBRL={xbrl}" if xbrl else ""))
        except Exception as e:  # noqa: BLE001
            self.q.put(("error", f"{type(e).__name__}: {e}"))

    def _populate(self, meta: dict) -> None:
        for i in self.tree.get_children():
            self.tree.delete(i)
        self.hdr.configure(text=f"{meta['ticker']}  {meta['ref'].form}  report {meta['ref'].report_date}"
                                f"  ·  filing_class = {meta['cls']}")
        for s in self.result.segments:
            color = _STATUS_COLOR.get(s.status, "#e7ecf2")
            tag = f"c_{s.status}"
            self.tree.tag_configure(tag, foreground=color)
            xb = (s.xbrl_check.split(":")[0] if s.xbrl_check else "")
            tp = (s.topic_check.split(":")[0] if s.topic_check else "")
            nr = " ⚠" if s.needs_review else ""
            self.tree.insert("", tk.END, iid=s.item_code, text=f"Item {s.item_code}",
                             values=(s.status + nr, f"{s.confidence:.2f}", xb, tp), tags=(tag,))

    def _on_select(self, _e) -> None:
        sel = self.tree.selection()
        if not sel or self.result is None:
            return
        code = sel[0]
        seg = next((s for s in self.result.segments if s.item_code == code), None)
        if seg is None:
            return
        body = self.result.text_of(code) if seg.end_offset > seg.start_offset else "(無正文 span)"
        head = (f"Item {seg.item_code}. {seg.canonical_title}\n"
                f"status={seg.status}  confidence={seg.confidence:.2f}  provenance={seg.provenance}\n"
                f"needs_review={seg.needs_review}  chars={seg.end_offset - seg.start_offset}\n"
                f"offset=[{seg.start_offset},{seg.end_offset}]  sha256={seg.text_sha256[:16]}\n"
                f"xbrl_check: {seg.xbrl_check or '-'}\n"
                f"topic_check: {seg.topic_check or '-'}\n"
                + (("warnings: " + " | ".join(seg.warnings)) if seg.warnings else "") + "\n"
                + "─" * 60 + "\n")
        self.txt.delete("1.0", tk.END)
        self.txt.insert(tk.END, head + body[:20000])


if __name__ == "__main__":
    SecViewer()

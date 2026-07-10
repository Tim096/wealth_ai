r"""One-click chat window to dispatch the browser agent — you type a task in
natural language, it drives a VISIBLE browser and streams each step.

Launch: double-click 啟動Agent.bat, or:  .venv\Scripts\python tools\agent_chat.py

It auto-starts the local Codex gateway (uses your `codex login` session) if
it isn't already running; if codex isn't installed it falls back to a
deterministic mock planner so the window still works on the bundled demo site.
"""

from __future__ import annotations

import os
import queue
import re
import shutil
import subprocess
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import scrolledtext

import httpx
from playwright.sync_api import sync_playwright

from browser_core import BrowserTaskContract, SuccessCondition
from browser_agent.agent import BrowserAgent
from browser_agent.memory_store import MemoryStore
from browser_agent.planner import LLMPlanner, MockPlanner
from llm_core.config import load_llm_config
from llm_core.openai_client import OpenAIClient
from observability_core import EvidenceStore

from browser_agent.nl import derive_success  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs" / "agent_chat"


class AgentChat:
    def __init__(self) -> None:
        self.ui_q: queue.Queue = queue.Queue()
        self.task_q: queue.Queue = queue.Queue()
        self._build_gui()
        threading.Thread(target=self._worker, daemon=True).start()
        self.root.after(80, self._pump)
        self.root.mainloop()

    # ---- GUI ----
    def _build_gui(self) -> None:
        self.root = tk.Tk()
        self.root.title("AI Browser Agent · 派工對話窗")
        self.root.geometry("720x560")
        self.root.configure(bg="#0f141b")
        self.out = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, bg="#0f141b", fg="#e7ecf2",
                                             insertbackground="#e7ecf2", font=("Consolas", 11),
                                             relief=tk.FLAT, padx=12, pady=10)
        self.out.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))
        self.out.configure(state=tk.DISABLED)

        bar = tk.Frame(self.root, bg="#0f141b")
        bar.pack(fill=tk.X, padx=8, pady=(0, 4))
        tk.Label(bar, text="網址", bg="#0f141b", fg="#93a0b0").pack(side=tk.LEFT)
        self.url = tk.Entry(bar, bg="#141b25", fg="#e7ecf2", insertbackground="#e7ecf2",
                            relief=tk.FLAT, width=34)
        self.url.insert(0, "https://www.youtube.com")
        self.url.pack(side=tk.LEFT, padx=(4, 10), ipady=3)

        row = tk.Frame(self.root, bg="#0f141b")
        row.pack(fill=tk.X, padx=8, pady=(0, 10))
        tk.Label(row, text="任務", bg="#0f141b", fg="#93a0b0").pack(side=tk.LEFT)
        self.task = tk.Entry(row, bg="#141b25", fg="#e7ecf2", insertbackground="#e7ecf2",
                             relief=tk.FLAT, font=("Segoe UI", 11))
        self.task.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 8), ipady=5)
        self.task.bind("<Return>", lambda e: self._send())
        self.send_btn = tk.Button(row, text="派工 ▶", command=self._send, bg="#45b9c6",
                                  fg="#0f141b", relief=tk.FLAT, font=("Segoe UI", 10, "bold"),
                                  activebackground="#3aa6b2", padx=14)
        self.send_btn.pack(side=tk.LEFT)
        self.task.focus_set()

        self._log("sys", "啟動中…正在準備 Codex gateway 與瀏覽器。")
        self._log("sys", "用法:網址欄填起點,任務欄用自然語言描述要做什麼,按 Enter 或「派工」。")

    def _log(self, kind: str, text: str) -> None:
        self.ui_q.put((kind, text))

    def _pump(self) -> None:
        colors = {"sys": "#93a0b0", "you": "#45b9c6", "agent": "#e7ecf2",
                  "ok": "#4bbd80", "bad": "#e07a6d"}
        try:
            while True:
                kind, text = self.ui_q.get_nowait()
                self.out.configure(state=tk.NORMAL)
                tag = f"t_{kind}"
                self.out.tag_configure(tag, foreground=colors.get(kind, "#e7ecf2"))
                prefix = {"you": "你 › ", "agent": "", "sys": "· ", "ok": "", "bad": ""}.get(kind, "")
                self.out.insert(tk.END, prefix + text + "\n", tag)
                self.out.see(tk.END)
                self.out.configure(state=tk.DISABLED)
        except queue.Empty:
            pass
        self.root.after(80, self._pump)

    def _send(self) -> None:
        task = self.task.get().strip()
        if not task:
            return
        url = self.url.get().strip() or None
        self._log("you", task)
        self.task.delete(0, tk.END)
        self.send_btn.configure(state=tk.DISABLED, text="執行中…")
        self.task_q.put((url, task))

    def _done(self) -> None:
        self.send_btn.configure(state=tk.NORMAL, text="派工 ▶")

    # ---- gateway ----
    def _ensure_gateway(self, base_url: str) -> bool:
        def up() -> bool:
            try:
                return httpx.get(f"{base_url.rstrip('/')}/models", timeout=3).status_code == 200
            except Exception:  # noqa: BLE001
                return False
        if up():
            return shutil.which("codex") is not None
        backend = "codex" if shutil.which("codex") else "mock"
        if backend == "mock":
            self._log("sys", "找不到 codex（未安裝或未 login）→ 用 mock planner(僅適用內建 demo 站)。")
            self._log("sys", "要用真 Codex:先 `npm i -g @openai/codex` 然後 `codex login`。")
        port = base_url.rstrip("/").split(":")[-1].split("/")[0]
        try:
            subprocess.Popen(
                [os.path.join(str(ROOT), ".venv", "Scripts", "python.exe"),
                 str(ROOT / "tools" / "codex_gateway.py"),
                 "--backend", backend, "--model", "default", "--port", port],
                creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        except Exception as e:  # noqa: BLE001
            self._log("bad", f"無法啟動 gateway: {e}")
            return False
        for _ in range(20):
            if up():
                return backend == "codex"
            time.sleep(0.5)
        self._log("bad", "gateway 起不來,改用 mock。")
        return False

    # ---- browser worker (owns Playwright) ----
    def _worker(self) -> None:
        cfg = load_llm_config()
        real_codex = self._ensure_gateway(cfg.base_url)
        client = OpenAIClient(api_key=cfg.api_key, base_url=cfg.base_url, model=cfg.model)
        OUT.mkdir(parents=True, exist_ok=True)
        try:
            dl_dir = OUT / "downloads"
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=False)
                context = browser.new_context(viewport={"width": 1200, "height": 820},
                                              accept_downloads=True)
                page = context.new_page()
                self._log("sys", f"就緒 ✔  planner={'Codex(' + cfg.base_url + ')' if real_codex else 'mock'}"
                                  f"。下載會存到 {dl_dir}。瀏覽器視窗已開,派工吧。")
                while True:
                    url, task = self.task_q.get()
                    if task is None:
                        break
                    self._run(page, client, real_codex, url, task)
                    self.root.after(0, self._done)
                browser.close()
        except Exception as e:  # noqa: BLE001
            self._log("bad", f"瀏覽器 worker 發生錯誤: {type(e).__name__}: {e}")

    def _run(self, page, client, real_codex, url, task) -> None:
        planner = LLMPlanner(client) if real_codex else MockPlanner(
            (re.findall(r"['\"“]([^'\"”]+)['\"”]", task) or ["widget"])[0])
        if url:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:  # noqa: BLE001
                self._log("bad", f"打不開 {url}: {e}")
                return
        conds = derive_success(task)
        if not conds:
            self._log("bad", "推斷不出可驗證的成功條件(中文長句無法自動切詞)。"
                             "請在任務裡用引號標出關鍵詞,例:搜尋 \"訂閱價格\"。")
            return
        self._log("sys", f"成功條件(自動推斷):{conds[0]}")
        contract = BrowserTaskContract(
            task_id="chat", natural_language_task=task,
            expected_outcome="success conditions visibly satisfied",
            success_conditions=[SuccessCondition(type=c.split(":", 1)[0], value=c.split(":", 1)[1])
                                for c in conds])
        agent = BrowserAgent(page, MemoryStore(OUT / "mem.json"), site="chat", task_type="agentic",
                             artifact_dir=OUT / "shots", evidence_store=EvidenceStore(OUT / "evidence"),
                             downloads_dir=OUT / "downloads")
        run = agent.run_agentic("chat", contract, planner, max_steps=8,
                                on_step=lambda t: self._log("agent", t))
        kind = "ok" if run.status == "pass" else "bad"
        self._log(kind, f"結果:{run.status.upper()}(confidence {run.confidence:.2f}) — {run.verifier.reason}")
        if agent.executor.last_download_path:
            self._log("ok", f"📁 已下載到:{agent.executor.last_download_path}")


if __name__ == "__main__":
    AgentChat()

# 裁判悖論 — 專案哲學起點

- **Session**: `3ae1f24f-695e-448f-94aa-7efb6c9d79ab`
- **日期**: 2026-07-10（原始輪次 row 3–20;文末回顧引自同 session row 1051）
- **Record type**: Verbatim transcript excerpt with editorial context
- **Verbatim boundary**: Only the dated `row ...` sections below `---` are verbatim. The title, metadata, summary, and cross-references are editorial scaffolding.
- **Redaction**: Secrets are replaced with explicit `[REDACTED-...]` markers; omitted tool material is marked `[...elided...]` where applicable.
- **對應重建紀錄**: `prompts/eval_design/`（不變量 / 錯誤注入 / 多引擎投票的設計決策)、記憶 `capture-first-then-classify`

> 這是整個第二題(SEC 抽取)驗證體系的哲學源頭。使用者提出一個悖論,AI 拆解成「裁判驗不變量而非答案」「裁判可棄權」「錯誤注入量裁判自己」,這條回歸鏈後來貫穿了所有 eval 設計。

---

### row 3 — user

@Whaleforce-AI-Coding-Test-EN.md 第二題我想再想一個悖論 首先我一定要完美的解析出來我才能當一個正確的裁判不是嗎 ? 那這樣我就已經有完整的產品了 可是不就是因為我產品不完善我才要裁判嗎 ? 如何解決這個悖論

### row 11 — assistant

這個悖論是假的。它把「裁判」偷換成「重新生成正確答案的人」。裁判不需要會解析,只需要會**檢查**——而檢查是嚴格更容易的問題(P vs NP 的直覺:驗證一個解 ≠ 找出一個解)。

具體拆解成四個出口:

**1. 裁判驗的是不變量,不是答案**

你不需要知道 Item 7 的正確邊界在哪,也能檢查:

- 各 item 串接起來 ≈ 原文(coverage,呼應你的「先全抓再分類」原則)
- Items 順序單調遞增、無重疊、無重複
- 每段開頭匹配 item heading 模式
- 長度分佈合理(Item 7 通常是最長段之一;Item 4 幾乎總是很短)

這些是**必要條件**。產品必須對每個難例做出決定;裁判只需偵測違規。偵測不到違規 ≠ 保證正確,但偵測到違規 = 確定有錯——這個不對稱就是裁判的價值。

**2. 裁判可以棄權,產品不行**

產品被迫對每份 filing 輸出一個答案;裁判可以輸出「不確定,信心 0.4」。允許棄權讓裁判的任務嚴格變簡單。題目要求前端顯示 extraction confidence,就是在暗示這條路。

**3. 交叉驗證:兩個不完美的方法,分歧處就是錯誤所在**

跑兩條獨立路線(例如 regex heading 切分 vs TOC 錨點定位 vs LLM 抽查邊界)。兩者一致 → 高信心;分歧 → 標記為難例。任何一條都不完美,但分歧訊號不需要任何一條完美。

**4. 局部完美取代全域完美**

「完美解析所有 filing」不可能,但「人工完美標註 30 份抽樣」只是勞力。你在有限 golden set 上當一次性的完美裁判,用它校準前三層的自動裁判,再讓自動裁判泛化到全體。

所以架構是:

```
Layer 1  機械不變量檢查(免 ground truth,全量跑)
Layer 2  交叉方法分歧偵測(免 ground truth,全量跑)
Layer 3  人工 golden set(有 ground truth,小樣本,校準 Layer 1/2)
```

悖論消解的一句話版本:**裁判的職責是把「不知道錯在哪」變成「知道哪些地方可疑」,這不需要完整產品,只需要比沉默失敗多一點的訊號。**而題目評分項裡的 "how you verify yourself without public ground truth" 和 "silent-failure prevention",問的正是這件事——出題者預設你會遇到這個悖論,想看你用分層驗證解掉它。

### row 18 — user

可是裁判既然沒有得到答案 自己也不確定如何確定他給自己打分公正

### row 20 — assistant

這是「誰來裁判裁判」的無窮回歸問題。它的終止條件是:**裁判的準確率本身是可測量的**,而測量裁判比測量產品便宜得多。兩個手段:

**1. 錯誤注入(mutation testing)——你造不出完美答案,但造得出已知的錯誤**

拿一份抽取結果,故意破壞它:邊界偏移 200 字、整個 Item 丟掉、Item 7 和 7A 互換、塞進另一份 filing 的段落。這些是**已知為錯**的樣本,不需要任何 ground truth 就能無限生成。餵給裁判,量它的 recall:

- 抓到 95% 的注入錯誤 → 裁判的漏檢率有了上界
- 某類注入(比如小幅邊界偏移)全漏 → 你知道裁判的確切盲區,寫進 README 的 limitation

這又是同一個不對稱:生成正確答案難,生成確定錯誤的答案便宜。

**2. Golden set 反向校準——量裁判,不是量產品**

30 份人工標註不只用來評產品,同時評裁判:裁判說 pass 的,人工看實際多少真的對(precision);裁判信心 0.9 的那群,實際正確率是不是接近 0.9(calibration curve)。如果裁判說 0.9 但實際只有 0.6,你就修裁判或降權它的輸出。

然後是關鍵的觀念修正:**裁判不需要「逐例公正」,只需要「統計上已知偏差」。**

一個 recall 90%、且偏差方向已知的裁判,完全夠用——因為它的用途是排序版本、抓 regression、把 filings 分成「可信/可疑」兩堆,這些都是統計任務,不是逐例判決。真正致命的不是裁判會錯,而是裁判**錯得不知道、且錯的方向偏向漏報**。

所以設計上讓裁判的錯誤單邊化:寧可誤報(成本 = 你多看一眼),不可漏報(成本 = silent failure 交到面試官手上)。誤報率高一點沒關係,那只是雜訊;漏報率有了注入測試給的上界,回歸就終止了。

回歸鏈的完整形狀:

```
產品     ← 裁判驗(不變量 + 交叉分歧)
裁判     ← 錯誤注入量 recall + golden set 量 precision/calibration
注入器   ← 不需要驗:錯誤是自己 construct 的,正確性 by construction
人工標註 ← 有限勞力,一次付清
```

終點站是「by construction 的已知錯誤」和「有限的人工勞力」,兩者都不再需要更上層的裁判。

---

### 後續落地(同 session row 1051 回顧,節錄)

> **起點**:你問了一個悖論——「裁判要完美才能驗產品,但產品不完美才需要裁判」。答案:裁判驗的是不變量、可以棄權、用多方分歧抓錯、用錯誤注入驗裁判自己。這個哲學貫穿了後面所有工作。

這條回歸鏈實際變成了:mutation harness(六類注入 recall 全 1.0)、5 引擎 2-of-N 投票、校準曲線 AUROC、capture-first 抽取原則。對應的重建決策紀錄見 `prompts/eval_design/2026-07-10-verifier-mutation-harness.md` 與 `2026-07-10-five-engine-2of-n-voting.md`。

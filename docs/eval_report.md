# Eval Report

> 數據可重跑:`tools/eval_one.py`(每份 filing 的 JSON record)、`tools/sweep_metrics.py`(彙整)。原始 records 在 `data/sec_eval/records/`。

## 方法論:為什麼這份 eval 特別

一般作業的 eval 會止步於「pass rate 高不高」。本專案的核心主張是:**pass rate 不是正確性,silent failure rate 才是。** 一個 C 級系統會把「抓到一句 cross-reference 指標」報成 pass;A+ 系統會標成 incorporated_by_reference 並說清楚內容在哪裡。

所以本 eval 用**對抗式稽核**驗證 pass 的真偽,而不是相信 pipeline 自報的 pass。

## SEC Extractor

### Eval set(分層,SPEC 7.14)

| Layer | Tickers | 目的 |
|---|---|---|
| 大型科技 | AAPL\*, MSFT, NVDA | baseline |
| 金融 | JPM\*, GS | 長 Item 7/8、wrapper 10-K |
| 零售/製造 | WMT, CAT | 一般格式 |
| 能源/礦業 | XOM\*, NEM | Item 4 特殊、appended financial section |
| 生技 | MRNA | 格式變異 |
| 消費 | KO | 一般格式 |

`*` = dev set(開發期見過);其餘 **8 家為 held-out**,pipeline 首次接觸。合成 fixtures(alpha/beta)另有 manual golden labels(`data/golden_labels/`),ground truth by construction。

### 對抗式稽核(這是本專案的驗證核心)

用一個 multi-agent workflow(56 個 agent)稽核 sweep1 的 253 個 item:每個 ticker 一個 audit agent 檢查可疑 span(短 pass、低信心 pass、Item 7/8 內容真偽、TOC 洩漏),每個回報的 anomaly 再交給獨立的**對抗式驗證 agent**(prompt 設定為「盡力反駁這個 anomaly」),多數決才算成立。

結果:**31 個 anomaly 確認、12 個被反駁**(反駁的多是「這其實是誠實的 incorporated_by_reference / None. 行為,不是 bug」——驗證層自己擋掉了誤報)。

這直接命中你們主管在意的痛點:**很多作業 SEC 跑出來不完整,但 AI 自報完成度很高。** 我的 sweep1 metrics 自報 75.9% pass,對抗式稽核卻證明其中 15 個是 silent failure。稽核抓到了我自己的 pipeline 在說謊。

### 三大 silent-failure class(稽核發現 → 已修復)

| Class | 範例 | 根因 | 修復 |
|---|---|---|---|
| Reference-stub 誤標 pass | JPM/GS/XOM Item 7/8/1C、MSFT/NVDA/CAT Item 3 | 舊 regex 只認「refer to Item N」,漏掉「refer to Note 14」「reference is made to the Financial Section」「appear on pages 162-314」「incorporated in this Form 10-K by reference」 | `classify_reference_stub` 廣義偵測短指標 body → incorporated_by_reference + 標明指向 |
| Trailing furniture 洩漏 | 幾乎每家 Item 4/9C/16 | span end = 下一個 item start,中間夾著「PART II」「頁碼」「running header」 | `trim_trailing_furniture` 可解釋地裁掉 |
| Terminal runaway | **XOM Item 16 = 311,785 字**、**JPM Item 15 = 985,564 字** | wrapper 10-K 把整本財報接在最後一個 item heading 後;末項 span 吃到 end-of-doc | `detect_appended_section_cut` 在 section break 切斷 + 警告排除了多少字 |

### Metrics:修復前 → 修復後(11 家、253 items)

| Metric | sweep1(修復前) | sweep2(修復後) | 解讀 |
|---|---|---|---|
| pass | 75.9% (192) | **70.0% (177)** | 下降是進步:15 個 silent failure 被誠實重分類 |
| incorporated_by_reference | 19.0% (48) | **24.9% (63)** | stub 現在誠實標示指向何處 |
| reserved | 4.3% (11) | 4.3% (11) | Item 6 |
| missing | 0.8% (2) | 0.8% (2) | GS/JPM Item 16 誠實省略 |
| 稽核確認 silent failure | **31** | 目標 0(見殘留) | — |
| 最大 terminal span | 985,564 字 | **15,529 字** | runaway 已封鎖 |
| confidence 鑑別度 | 全部 ~0.958 | **substantive 0.962 / stub 0.666** | confidence 現在能分辨 stub |

### Confidence calibration

修復前 confidence 對 stub 與實質內容都給 ~0.958,毫無鑑別力(稽核明確點名)。新增 `content_substantiveness` 分量、並對 stub 不計 verifier 分數後:

- 實質 pass:mean **0.962**(min 0.799)
- reference stub:mean **0.666**(0.566–0.700)

兩群完全分離,confidence 首次能作為「這是不是真內容」的信號。

### 已知殘留(誠實邊界)

1. **Wrapper 10-K 的真實內容尚未還原。** JPM/XOM 的 Item 7/8 現在誠實標成 incorporated_by_reference 指向 appended section,但 pipeline 還沒把那段 MD&A/財報「接回」對應 item。這需要 cross-reference resolution(第二遍)——見 `docs/insights_and_directions.md` §2,列為明確優化方向。
2. **Held-out 未擴及 Intel/Citi。** 稽核用的 11 家已涵蓋 wrapper 模式(JPM/XOM),但主管點名的 Intel/Citi 尚未實測;下一輪 held-out 應納入。
3. **golden boundary IoU 尚未量化。** 目前用 status-level golden labels(合成 fixtures)+ 真實 filing 的對抗式稽核。真實 filing 的 token-level IoU 需要 manual span 標註,列為 backlog。

## Browser Agent

Phase 2,尚未實作。實作後補 task success rate、verifier false positive rate、repair success rate、silent failure rate。

# Real-filing eval sweep 設計(11 家公司)

> **Record type:** Derived decision record

## Trigger

Synthetic fixtures 與 AAPL/JPM/XOM smoke test 通過後，SEC pipeline 進入分層 real-filing sweep。

## Scoring Criteria

- 評估紀律:分層 eval set + held-out + metrics
- 可觀測性:每份 filing 有 JSON eval record
- 工程權衡:SEC rate limit 下的並行策略

## Prompt summary

分層(SPEC 7.14):

| Layer | Tickers | 角色 |
|---|---|---|
| 大型科技 | AAPL*, MSFT, NVDA | baseline |
| 金融 | JPM*, GS | 長 Item 7/8 |
| 零售/製造 | WMT, CAT | 一般格式 |
| 能源/礦業 | XOM*, NEM | Item 4 特殊案例 |
| 生技 | MRNA | 格式變異 |
| 消費 | KO | held-out 補充 |

`*` = dev set(開發期間見過);其餘 8 家 = **held-out**(pipeline 從未跑過)。

執行策略:**serial prefetch → parallel analysis**。SEC fair-access 上限 10 req/s;若 8 個 agent 各自開 fetcher(每 process 2 req/s)會超限。改為 inline 串行預抓進 shared cache,workflow agents 純讀 cache 分析,零 rate-limit 風險。

## 嘗試紀錄(含失敗)

1. **失敗**:`python -c "exec(open('tools/eval_one.py').read())"` — exec 環境無 `__file__`,`ROOT = Path(__file__)` 炸掉,8 家全 exit 255。
2. **修正**:直接 `python tools\eval_one.py TICKER > runs\sweep1\TICKER.json`,成功。

## Decision

先 serial prefetch 到 shared cache，再對分層 ticker set 做平行、cache-only analysis。

## Resulting Change

- tools/eval_one.py(JSON eval record 工具)
- runs/sweep1/*.json(eval records,gitignored;metrics 進 docs/eval_report.md)
- Workflow:每 ticker 一個 agent 分析 record + 檢查可疑 span,anomaly 進 verify 階段

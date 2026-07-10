# Cost / Latency Report

> 數據來源:2026-07-10 sweep1(11 家真實 10-K)。所有數字來自 `data/raw_filings/fetch_log.jsonl` 與 `data/sec_eval/records/sweep1/*.json`,可重跑驗證(`tools/eval_one.py`、`tools/sweep_metrics.py`)。

## SEC Extractor

### Fetch 成本

| 指標 | 值 |
|---|---|
| 總存取次數 | 503 |
| 實際 live 請求 | 34 |
| Cache 命中 | 469(**93.2%**)|
| Live fetch 延遲 | mean 453 ms,max 1,321 ms |
| Raw cache 大小 | 34 blobs,73.2 MB |

Cache 策略:content-addressed(URL hash),讀取時驗 sha256,corruption 直接 raise。同一 filing 重跑 = 零網路成本、位元組級可重現。

### Parse 延遲

| 指標 | 值 |
|---|---|
| Parse 延遲 | mean 1,131 ms,max 2,556 ms(JPM,12.9M chars)|
| 延遲 vs 文件大小 | 近線性(~0.2 ms / KB)|

單執行緒純 Python;瓶頸是 normalizer 的逐字元 offset mapping。這是刻意的權衡:**offset 精確性 > 速度**——它讓每個 span 可以 sha256 驗證。若需擴充,pipeline 是 per-filing 可平行(process pool)。

### LLM 成本

**本次 sweep LLM 成本:$0。** 253 items 全部由確定性 pipeline 判定,LLM fallback rate = 0%(deterministic path 尚未遇到需要 adjudicator 的 ambiguous boundary)。這驗證了 SPEC 7.2 的設計:LLM 只在 ambiguous 時升級,絕大多數 filing 不需要。

Adjudicator 啟用後的預估:每次裁決 ~2K input tokens(兩個 candidate context),以 Haiku 級模型計 <$0.005 / 裁決;以目前 0% fallback rate,均攤成本趨近零。

### 擴充性估算

- 每 filing 均攤:~3 live requests(submissions + index + main doc)× 0.5s rate limit + ~1.1s parse ≈ **3–5 秒/filing**(冷 cache)
- S&P 500 全量單機:< 45 分鐘;cache 熱時 < 10 分鐘
- Rate limit 是硬上限(SEC fair-access ~10 req/s),因此多機平行抓取無意義;平行化只該用在 parse 層

### 成本控制決策紀錄

1. Serial prefetch → parallel analysis:避免多 process fetcher 疊加超過 SEC rate limit(見 prompts/eval_design/2026-07-10-real-filing-sweep.md)
2. LLM 不在主路徑:hallucination 風險與成本同時歸零,只留 ambiguous fallback
3. Raw cache 永久保存:重跑 eval 免費,eval 迭代成本趨近零

## Browser Agent

尚未實作(Phase 2)。實作後補:LLM cost / step、browser runtime latency、repair latency。

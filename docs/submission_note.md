# 提交材料(草稿,push 後補 repo URL)

## 提交欄位

| 欄位 | 值 |
|---|---|
| Repo URL | https://github.com/Tim096/wealth (66 commits 待 push;若 repo 為 private 需改公開或給面試官權限) |
| Task 2(SEC 10-K Extractor)線上 demo | https://wealth-sec-ncku.zeabur.app (完整可用,免 auth) |
| Task 1(Browser Agent)線上 demo | https://wealth-agent-ncku.zeabur.app (示範任務一鍵可跑;自然語言任務需在 Zeabur 補 OpenRouter key,見 docs/deploy.md) |

## 補充說明(可直接貼)

兩題皆完成,共用同一個「自我審計」可靠性層:verifier 是唯一 runtime 裁判、可誠實棄權(unknown / needs_review / abstain),所有 LLM 評分證據接地。每個對外數字都附 artifact 路徑可反查,輸的數字照寫(例:NTU 30-slice macro-F1 我們 0.6245 vs edgar_crawler 0.6332)。

- **Task 1**:Online-Mind2Web 20 題 live 子集 33.3% → 44.4% → 合成 ~61.1%(每一步有軌跡歸因;naive baseline 20%;與官方 leaderboard 不可比,README 有明寫)。prompt-injection 對抗套件設防後 ASR 0/5。
- **Task 2**:六類錯誤注入 mutation recall 全 1.0;多引擎 2-of-N 投票;XBRL 獨立 oracle Item 8 certified 10/1;verifier false-pass 自量自揭(100→79)。
- **AI 協作**:`prompts/` 全程決策紀錄(含 rejected 取捨與事後驗證),`docs/ai_collaboration_report.md` 總結。
- 建議閱讀順序:`README.md` → `docs/eval_report.md` → `docs/research/giants_task{1,2}.md` → `prompts/README.md`。

## 提交狀態(2026-07-11)

1. ~~push + tag~~ **已完成**:`main` 已推上 `github.com/Tim096/wealth`,release tag `v1.0-submission`;GitHub Actions CI 首輪修復後綠(ruff + 763 non-integration tests,run 29134525031)。
2. wealth-agent **已 redeploy**(帶最新 browser_agent 修復;health `ready:true`、4 個免 key 示範任務)。仍為 mock 模式——(可選)Zeabur 補 OpenRouter key 轉真實 LLM,見 `docs/deploy.md`。wealth-sec 如需帶上最新 dashboard 數字(XBRL 10/1)可再 redeploy。

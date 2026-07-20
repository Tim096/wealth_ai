"""Capability router / guard (SPEC 6.3, 6.4).

The "responsibility boundary" is enforced in code, not just documented: before
a task runs, classify it; before any action runs, screen it. Irreversible or
credentialed operations (login, purchase, checkout, payment, submitting a
formal form) are refused with an explicit reason — the agent returns
TaskRun.status == "refused", it does not attempt them. This is what makes
"not supported" a real limit rather than an unenforced policy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# task-level: natural-language intents we refuse outright
_FORBIDDEN_INTENT = {
    "login": re.compile(
        r"\b(log\s?in|sign\s?in|authenticate|enter\s+(?:my\s+)?password|use\s+credentials?)\b"
        r"|(?:登入|登錄|登录|簽入|签入)(?!\s*(?:文件|文檔|文档|說明|说明|教學|教程|指南|UX|設計|设计|流程|文章))"
        r"|(?:輸入|输入)(?:我的)?(?:密碼|密码)", re.I),
    "purchase": re.compile(
        r"\b(buy|purchase|checkout|add\s+to\s+cart|place\s+(?:an\s+)?order|pay(?:ment)?)\b"
        r"|(?:購買|购买|買下|买下|結帳|结账|加入購物車|加入购物车|下單|下单|付款|支付)", re.I),
    "post_submit": re.compile(
        r"\b(publish|upload|leave\s+(?:a\s+)?(?:comment|review)|submit\s+(?:the\s+)?(?:form|application|order|comment|review)|post\s+(?:a\s+)?(?:comment|review|message|article))\b"
        r"|(?:發文|发文|發布|发布|上傳|上传|留言|評論|评论|提交|送出)(?:表單|表单|申請|申请|訂單|订单|留言|評論|评论|檔案|文件)?",
        re.I),
    "captcha": re.compile(r"\bcaptcha\b|驗證碼|验证码", re.I),
    "paid_data": re.compile(r"\b(paywall|subscription required|premium data)\b|付費牆|付费墙|訂閱限定|订阅限定", re.I),
}

_READ_ONLY_MENTION = re.compile(
    r"\b(?:read|find|search|look\s+up|research|analy[sz]e|compare|summari[sz]e|browse|inspect|learn)\b"
    r"[^,;.!?]{0,80}\b(?:log\s?in|sign\s?in|checkout|payment|purchase|captcha|paywall|subscription|upload|posting?)\b"
    r"[^,;.!?]{0,40}\b(?:article|documentation|docs?|guide|tutorial|ux|design|pattern|policy|page|security)\b"
    r"|\b(?:read|find|search|look\s+up|research|analy[sz]e|compare|summari[sz]e|browse|inspect|learn)\b"
    r"[^,;.!?]{0,80}\b(?:article|documentation|docs?|guide|tutorial|ux|design|pattern|policy|page)\b"
    r"[^,;.!?]{0,40}\b(?:about|on)\s+(?:log\s?in|sign\s?in|checkout|payment|purchase|captcha|paywall|subscription|upload|posting?)\b"
    r"|(?:閱讀|阅读|找|查找|搜尋|搜索|研究|分析|比較|比较|總結|总结|瀏覽|浏览|查看)"
    r"[^，；。！？]{0,80}(?:登入|登錄|登录|簽入|签入|結帳|结账|付款|支付|購買|购买|驗證碼|验证码|付費牆|付费墙|上傳|上传|發文|发文)"
    r"[^，；。！？]{0,40}(?:文章|文件|文檔|文档|說明|说明|教學|教程|指南|UX|設計|设计|政策|頁面|页面|安全)"
    r"|(?:閱讀|阅读|找|查找|搜尋|搜索|研究|分析|比較|比较|總結|总结|瀏覽|浏览|查看)"
    r"[^，；。！？]{0,80}\b(?:log\s?in|sign\s?in|checkout|payment|purchase|captcha|paywall|subscription|upload|posting?)\b"
    r"[^，；。！？]{0,40}(?:文章|文件|文檔|文档|說明|说明|教學|教程|指南|UX|設計|设计|政策|頁面|页面|安全)",
    re.I)

# action-level: value/target hints that indicate a forbidden interaction
_FORBIDDEN_VALUE = re.compile(
    r"password|credit\s?card|cvv|card number|\bssn\b|routing number|place order|checkout|pay now",
    re.I,
)
_FORBIDDEN_TARGET_WORDS = re.compile(
    r"password|checkout|place[-_ ]?order|buy[-_ ]?now|add[-_ ]?to[-_ ]?cart|pay[-_ ]?now|submit[-_ ]?payment",
    re.I,
)


@dataclass
class CapabilityDecision:
    allowed: bool
    category: str  # 'ok' or the forbidden category
    reason: str


def screen_task(natural_language_task: str) -> CapabilityDecision:
    screened = _READ_ONLY_MENTION.sub("", natural_language_task)
    for category, pat in _FORBIDDEN_INTENT.items():
        if pat.search(screened):
            return CapabilityDecision(
                allowed=False, category=category,
                reason=f"task requires a {category} operation, which is out of the supported "
                       f"capability set (SPEC 6.4: no login/CAPTCHA/purchase/formal submit/paid data)")
    return CapabilityDecision(allowed=True, category="ok", reason="task is within supported capabilities")


def screen_action(action) -> CapabilityDecision:
    at = getattr(action, "type", "")
    value = getattr(action, "value", "") or ""
    target = getattr(action, "target", None)
    target_blob = ""
    if target is not None:
        target_blob = f"{getattr(target, 'selector', '')} {getattr(target, 'description', '')}"
    if at in ("fill", "press") and (
            _FORBIDDEN_VALUE.search(value) or _FORBIDDEN_VALUE.search(target_blob)):
        return CapabilityDecision(False, "sensitive_input",
                                  f"action would enter sensitive/credential data ('{value[:20]}...') — refused")
    # the raw keyboard channel must not become a hole in the credential boundary
    if at == "keyboard":
        typed = f"{getattr(action, 'text', '') or ''} {getattr(action, 'keys', '') or ''}"
        if _FORBIDDEN_VALUE.search(typed):
            return CapabilityDecision(False, "sensitive_input",
                                      f"keyboard would enter sensitive/credential data ('{typed.strip()[:20]}...') — refused")
    # press is as irreversible as click on a checkout/place-order control (Enter
    # on a pay button submits the order), so the grounded target must go through
    # the same forbidden-word gate — not only the value check above.
    if at in ("click", "download", "press") and _FORBIDDEN_TARGET_WORDS.search(target_blob):
        return CapabilityDecision(False, "irreversible_action",
                                  f"action targets an irreversible control ('{target_blob.strip()[:40]}') — refused")
    return CapabilityDecision(True, "ok", "action is reversible and within capabilities")

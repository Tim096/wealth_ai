"""derive_success: turn a natural-language task into a verifier condition,
confidently or not at all (honest > guessy)."""

from browser_agent.nl import derive_success


def test_download_task_keeps_the_section_to_verify():
    # "download the 10-K and find Risk Factors" must verify the FILE contains
    # the section — not rubber-stamp any downloaded file.
    assert derive_success("下載 INTC 10-K 並找到 Risk Factors 章節") == ["download_exists:Risk Factors"]


def test_bare_download_task_uses_empty_condition():
    assert derive_success("下載這個檔案") == ["download_exists:"]


def test_quoted_phrase_becomes_text_visible():
    assert derive_success('打開維基百科找到『量子計算』') == ["text_visible:量子計算"]


def test_titlecase_phrase_preferred_over_bare_token():
    assert derive_success("open the page and read Risk Factors") == ["text_visible:Risk Factors"]


def test_unsegmented_chinese_prose_returns_nothing():
    # no boundaries, no confident phrase -> [] (the caller runs anyway and the
    # verifier reports unknown; we never invent a garbage condition)
    assert derive_success("幫我找最熱門的財經節目") == []

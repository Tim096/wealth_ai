"""Regression tests for independent Online-Mind2Web judge prompts."""

from tools import webjudge


def test_final_judge_prompt_requires_one_binary_status():
    assert '"status": "success"}' in webjudge.FINAL_JUDGE_SYSTEM
    assert '"status": "failure"}' in webjudge.FINAL_JUDGE_SYSTEM
    assert '"status": "success" or "failure"' not in webjudge.FINAL_JUDGE_SYSTEM


def test_gateway_envelope_never_demonstrates_placeholder_status():
    note = webjudge._envelope_note(
        '{\\"thoughts\\": \\"evidence\\", \\"status\\": \\"success\\"}')
    assert '\\"status\\": \\"success\\"' in note
    assert '\\"status\\": \\"success|failure\\"' not in note
    assert "choose one" in note

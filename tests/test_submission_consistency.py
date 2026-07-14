"""Guard mutable submission prose against known stale snapshots."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_readme_does_not_duplicate_mutable_test_or_demo_counts():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    stale = (
        "843 tests",
        "793 quick passed",
        "50 Playwright/integration passed",
        "The four **示範任務**",
        "4 個免 key 示範任務",
        "evidence store(兩題共用)",
    )
    assert not [text for text in stale if text in readme]
    assert "GET /api/demo" in readme
    assert "實際數量由 pytest collection 回報" in readme


def test_ci_file_does_not_claim_a_historical_snapshot_is_current():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "has NOT run yet" not in workflow
    assert "743 passed" not in workflow
    assert "50 deselected" not in workflow


def test_deploy_docs_use_the_demo_discovery_endpoint_as_source_of_truth():
    deploy = (ROOT / "docs" / "deploy.md").read_text(encoding="utf-8")
    assert "4 個一鍵 preset" not in deploy
    assert "免 key 示範任務(4 preset)" not in deploy
    assert "GET /api/demo" in deploy


def test_ai_collaboration_docs_point_to_reproducible_provenance():
    texts = [(ROOT / "README.md").read_text(encoding="utf-8")]
    texts.extend(path.read_text(encoding="utf-8") for path in (ROOT / "docs").glob("*.md"))
    combined = "\n".join(texts)
    assert "tools/verify_prompt_provenance.py" in combined
    assert "verbatim body hash" in combined


def test_current_tree_does_not_publish_a_personal_school_email():
    pattern = re.compile(r"\b[a-z]\d{8}@gs\.ncku\.edu\.tw\b", re.IGNORECASE)
    hits: list[str] = []
    for folder in ("apps", "data", "docs", "packages", "prompts", "tools"):
        for path in (ROOT / folder).rglob("*"):
            if path.is_file() and path.suffix in {".json", ".md", ".py", ".toml", ".txt", ".yml"}:
                if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
                    hits.append(str(path.relative_to(ROOT)))
    assert not hits, f"personal contact leaked in current tree: {hits}"

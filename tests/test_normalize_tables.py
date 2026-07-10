"""Table-cell separation + short-answer confidence — fixes from real NVDA use:
table labels were gluing to values ("Cost of revenue$261") and correct short
"None." answers were penalised by a length check."""

from sec_core.normalize import normalize_html
from sec_core.pipeline import extract_from_html


def test_table_cells_are_separated():
    html = ("<table><tr><td>Cost of revenue</td><td>$261</td><td>$178</td></tr>"
            "<tr><td>Research and development</td><td>4,676</td><td>3,423</td></tr></table>")
    text = normalize_html(html).text
    assert "Cost of revenue$261" not in text            # no gluing
    assert "Cost of revenue $261" in text                # separated
    assert "Research and development 4,676" in text
    # rows are on their own lines
    assert "\n" in text.strip()


def test_short_none_answer_not_penalised_for_length():
    # a legitimate short "None." item must score like a clean pass, not be
    # docked for being under the old 50-char minimum
    html = ("<p><b>Item 1B. Unresolved Staff Comments</b></p><p>None.</p>"
            "<p><b>Item 1C. Cybersecurity</b></p><p>" + ("We manage cybersecurity risk. " * 40)
            + "</p>")
    result = extract_from_html(html, "short")
    seg = result.segment("1B")
    assert seg.status == "pass"
    assert seg.confidence >= 0.9  # was ~0.87 before the length-sanity fix

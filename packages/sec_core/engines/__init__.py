"""Additional arbitration engines for triangulation (P0-7).

Each engine is a function raw_html -> dict[item_code, text] | None (None =
engine unavailable, never evidence against our span) with an INDEPENDENT
implementation lineage, so a shared blind spot cannot outvote our extractor:

  edgartools     — sec_core.third_engine (pip, MIT, pinned 5.42.0)
  edgar_crawler  — engines.edgar_crawler_vote: nlpaueb/edgar-crawler run as an
                   UNMODIFIED subprocess on a local checkout (GPLv3 — never
                   vendored or imported; see module doc). Lineage note:
                   EDGAR-CORPUS was built by this same code, so an
                   edgar-crawler vote and a corpus teacher vote are ONE
                   lineage and must never be counted as two.
  datamule       — engines.datamule_vote: pip dependency (MIT), style-driven
                   doc2dict backend — independent of every regex-driven route.

Engines only VOTE on agreement (third_engine.apply_triangulation 2-of-N);
they never manufacture our filing text.
"""

from sec_core.engines.datamule_vote import extract_items_datamule
from sec_core.engines.edgar_crawler_vote import (
    ensure_checkout,
    extract_items_edgar_crawler,
)

__all__ = [
    "ensure_checkout",
    "extract_items_datamule",
    "extract_items_edgar_crawler",
]

"""Deterministic generator for synthetic 10-K eval fixtures.

Body sections are padded to realistic lengths (real 10-K items run thousands
of characters); TOC-defence heuristics are tuned for that scale, and testing
them on toy-sized sections would misrepresent their behaviour.

Run: .venv/Scripts/python tools/gen_fixtures.py
"""

from __future__ import annotations

from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "sec_eval" / "fixtures"

FILLER = (
    "The Company continues to evaluate developments in its markets and adjusts "
    "its operating plans accordingly, and management believes that the factors "
    "described above are the material considerations relevant to this item. "
)


def pad(text: str, target: int = 2200) -> str:
    while len(text) < target:
        text += " " + FILLER
    return text


def p(anchor: str | None, heading: str, body: str, target: int = 2200) -> str:
    aid = f' id="{anchor}"' if anchor else ""
    return f"<p{aid}><b>{heading}</b></p>\n<p>{pad(body, target)}</p>\n"


def alpha() -> str:
    toc_rows = [
        ("item1", "Item 1. Business", 3),
        ("item1a", "Item 1A. Risk Factors", 12),
        ("item1b", "Item 1B. Unresolved Staff Comments", 25),
        ("item2", "Item 2. Properties", 26),
        ("item3", "Item 3. Legal Proceedings", 27),
        ("item5", "Item 5. Market for Registrant&#8217;s Common Equity", 28),
        ("item7", "Item 7. Management&#8217;s Discussion and Analysis of Financial Condition and Results of Operations", 31),
        ("item7a", "Item 7A. Quantitative and Qualitative Disclosures About Market Risk", 45),
        ("item8", "Item 8. Financial Statements and Supplementary Data", 47),
        ("item9a", "Item 9A. Controls and Procedures", 80),
        ("item10", "Item 10. Directors, Executive Officers and Corporate Governance", 82),
        ("item15", "Item 15. Exhibits, Financial Statement Schedules", 83),
    ]
    toc = "\n".join(
        f'<div><a href="#{a}">{t}</a> .......... {page}</div>' for a, t, page in toc_rows
    )
    return f"""<html>
<head><title>ALPHA TECH CORP - FORM 10-K</title><style>body {{ font: 10pt serif; }}</style>
<script>console.log("Item 7. this must never be extracted");</script>
</head>
<body>
<div>UNITED STATES SECURITIES AND EXCHANGE COMMISSION</div>
<div>FORM 10-K</div>
<div>ALPHA TECH CORP</div>

<h2>TABLE OF CONTENTS</h2>
{toc}

<div>PART I</div>

{p("item1", "Item 1. Business",
   "Alpha Tech Corp designs, manufactures and sells advanced widget systems worldwide. "
   "Our business is organized into three reportable segments: Widgets, Services, and Cloud. "
   "We were incorporated in Delaware in 1987 and our principal executive offices are located "
   "in Austin, Texas. We employ approximately 14,000 people worldwide as of fiscal year end.")}
{p("item1a", "Item 1A. Risk Factors",
   "Investing in our common stock involves a high degree of risk. Supply chain disruption "
   "could materially harm our operating results. Cybersecurity incidents could compromise "
   "our systems and result in loss of customer data. Our international operations expose us "
   "to currency fluctuations and regulatory changes.")}
{p("item1b", "Item 1B. Unresolved Staff Comments",
   "None. We have no unresolved comments from the staff of the Securities and Exchange "
   "Commission regarding our periodic or current reports under the Exchange Act.")}
{p("item2", "Item 2. Properties",
   "Our corporate headquarters occupies approximately 450,000 square feet in Austin, Texas "
   "under a lease expiring in 2031. We also own manufacturing facilities in Ohio and Malaysia "
   "totaling 1.2 million square feet.")}
{p("item3", "Item 3. Legal Proceedings",
   "From time to time we are involved in legal proceedings arising in the ordinary course "
   "of business. In March 2025 a patent infringement suit was filed against us in the Western "
   "District of Texas. We believe the claims are without merit and intend to defend vigorously.")}
{p(None, "Item 4. Mine Safety Disclosures",
   "Not applicable. Our operations do not involve mines subject to the Federal Mine Safety "
   "and Health Act of 1977, and accordingly no disclosures are required under this item.")}

<div>PART II</div>

{p("item5", "Item 5. Market for Registrant&#8217;s Common Equity, Related Stockholder Matters and Issuer Purchases of Equity Securities",
   "Our common stock trades on the Nasdaq Global Select Market under the symbol ALPH. "
   "As of February 1, 2026 there were 412 holders of record of our common stock. We have "
   "never declared or paid cash dividends and do not anticipate paying any in the near future.")}
<p><b>Item 6. [Reserved]</b></p>
<p>Reserved.</p>

{p("item7", "Item 7. Management&#8217;s Discussion and Analysis of Financial Condition and Results of Operations",
   "The following discussion should be read together with our consolidated financial "
   "statements and the related notes included in Item 8 of this Annual Report on Form 10-K. "
   "Net revenue for fiscal 2025 was $4.2 billion, an increase of 11% compared with fiscal "
   "2024, driven primarily by growth in the Cloud segment. Gross margin improved to 58.3%.", 3200)}
{p("item7a", "Item 7A. Quantitative and Qualitative Disclosures About Market Risk",
   "We are exposed to market risk from changes in foreign currency exchange rates and "
   "interest rates. A hypothetical 10% adverse movement in exchange rates would have "
   "decreased fiscal 2025 revenue by approximately $120 million.")}
{p("item8", "Item 8. Financial Statements and Supplementary Data",
   "The consolidated financial statements required by this item are included herein. "
   "Report of Independent Registered Public Accounting Firm. Consolidated Balance Sheets "
   "as of December 31, 2025 and 2024. Total assets were $8.4 billion at December 31, 2025.", 3200)}
{p(None, "Item 9. Changes in and Disagreements with Accountants on Accounting and Financial Disclosure",
   "None. There were no changes in or disagreements with our independent registered public "
   "accounting firm on accounting or financial disclosure matters during the periods presented.")}
{p("item9a", "Item 9A. Controls and Procedures",
   "Our management, with the participation of our Chief Executive Officer and Chief "
   "Financial Officer, evaluated the effectiveness of our disclosure controls and procedures "
   "as of December 31, 2025 and concluded they were effective at the reasonable assurance level.")}
{p(None, "Item 9B. Other Information",
   "During the three months ended December 31, 2025, no director or officer adopted or "
   "terminated a Rule 10b5-1 trading arrangement or non-Rule 10b5-1 trading arrangement.")}

<div>PART III</div>

<p id="item10"><b>Item 10. Directors, Executive Officers and Corporate Governance</b></p>
<p>The information required by this Item 10 is incorporated by reference to our definitive
proxy statement for the 2026 Annual Meeting of Stockholders to be filed within 120 days.</p>

<p><b>Item 11. Executive Compensation</b></p>
<p>The information required by this Item 11 is incorporated by reference to our definitive
proxy statement for the 2026 Annual Meeting of Stockholders.</p>

<div>PART IV</div>

{p("item15", "Item 15. Exhibits, Financial Statement Schedules",
   "The following documents are filed as part of this report: (1) consolidated financial "
   "statements listed in Item 8; (2) financial statement schedules, omitted because not "
   "applicable; and (3) the exhibits listed in the Exhibit Index below.")}
<h3>SIGNATURES</h3>
<p>Pursuant to the requirements of Section 13 or 15(d) of the Securities Exchange Act of
1934, the registrant has duly caused this report to be signed on its behalf by the
undersigned, thereunto duly authorized, on February 20, 2026.</p>
</body>
</html>
"""


def beta() -> str:
    def c(heading: str, body: str) -> str:
        return f"<center><b>{heading}</b></center>\n<p>{pad(body)}</p>\n"

    return f"""<html>
<body>
<div>BETA ENERGY PARTNERS LP&nbsp;&#8212;&nbsp;ANNUAL REPORT ON FORM 10-K</div>

<div>INDEX</div>
<div>ITEMS 1 AND 2. BUSINESS AND PROPERTIES&nbsp;.....&nbsp;2</div>
<div>ITEM 1A. RISK FACTORS&nbsp;.....&nbsp;15</div>
<div>ITEM 3. LEGAL PROCEEDINGS&nbsp;.....&nbsp;30</div>
<div>ITEM 4. MINE SAFETY DISCLOSURES&nbsp;.....&nbsp;31</div>
<div>ITEM 7. MANAGEMENT&#8217;S DISCUSSION AND ANALYSIS&nbsp;.....&nbsp;33</div>

<div>PART I</div>

{c("ITEMS 1 AND 2. BUSINESS AND PROPERTIES",
   "Beta Energy Partners LP is a master limited partnership engaged in the gathering, "
   "processing and transportation of natural gas across the Permian Basin. We own and "
   "operate approximately 6,400 miles of pipeline and four processing plants. Our "
   "properties consist of the pipeline systems described above together with related "
   "compression facilities, rights of way and easements.")}
{c("ITEM 1A. RISK FACTORS",
   "Limited partner interests are inherently different from shares of capital stock. "
   "Commodity price volatility may reduce throughput on our systems and adversely affect "
   "our cash available for distribution. Environmental regulation of methane emissions is "
   "expected to become more stringent and may require significant capital expenditures.")}
{c("ITEM 3. LEGAL PROCEEDINGS",
   "We are a party to various legal proceedings incidental to our business. Management "
   "believes the resolution of open matters will not materially affect our consolidated "
   "financial position, results of operations or cash flows.")}
{c("ITEM 4. MINE SAFETY DISCLOSURES",
   "The operation of our sand mine in West Texas is subject to regulation by the federal "
   "Mine Safety and Health Administration under the Federal Mine Safety and Health Act of "
   "1977. Information concerning mine safety violations is included in Exhibit 95.1.")}

<div>PART II</div>

{c("ITEM 7. MANAGEMENT&#8217;S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION AND RESULTS OF OPERATIONS",
   "Adjusted EBITDA for 2025 was $612 million compared with $548 million for 2024. "
   "Throughput volumes averaged 940 MMcf/d, an increase of 7% over the prior year, "
   "primarily attributable to increased drilling activity by producers on acreage "
   "dedicated to our systems. Distributable cash flow provided coverage of 1.4x.")}
<div>SIGNATURES</div>
<p>Pursuant to the requirements of Section 13 or 15(d) of the Securities Exchange Act of
1934, the registrant has duly caused this report to be signed on its behalf.</p>
</body>
</html>
"""


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "alpha_10k.html").write_text(alpha(), encoding="utf-8")
    (OUT_DIR / "beta_10k.html").write_text(beta(), encoding="utf-8")
    print(f"wrote fixtures to {OUT_DIR}")


if __name__ == "__main__":
    main()

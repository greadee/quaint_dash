# Fund eligibility regression coverage

Verified 2026-09-11. This is a 65-instrument regression basket of widely distributed Canadian and US instruments, not an exhaustive or ranked popularity list. Canadian exchange suffixes distinguish fund symbols from operating companies (for example CASH.TO versus CASH).

## Root cause and rules

Corporate scheduling previously accepted broker-imported `stock` labels without checking fund identity. XSH.TO and TCSH.TO consequently reached company earnings providers. Both are ETFs: XSH holds short-term corporate bonds; TCSH is a cash-management fund. Neither has company earnings dates.

The shared identity rule recognizes explicit fund metadata, ETF/money-market names and subtypes, and a curated symbol fallback for incomplete or incorrect metadata. Corporate scheduling and execution both apply the rule. Startup repairs stored labels, disables fundamental subscriptions, and marks inappropriate pending/failed corporate jobs unsupported. Historical prices, transactions and completed records remain stored. Price and distribution ingestion remains eligible. Data readiness uses the same fund identity check.

Tests deliberately seed every covered fund with `asset_type=stock` and no descriptive metadata. They verify exclusion from company scheduling, continued general ingestion eligibility, and zero provider calls for earnings and financial-statement jobs. Additional cases cover new names outside the symbol set, ordinary companies, and the CASH/CASH.TO collision.

Broker creation and FMP profile mapping now apply the shared classification before writing metadata, addressing the hardcoded broker `stock` default. Tests also verify these import boundaries. Live verification through the Quaint Dash desktop shortcut confirmed XSH.TO and TCSH.TO have `asset_type=etf`, with no pending/running/failed corporate jobs for either and zero critical Operations incidents.

## Issuer references and explicit fixture basket

| Issuer / source | Symbols in regression coverage |
| --- | --- |
| [TD cash management](https://www.td.com/ca/en/asset-management/funds/solutions/etfs/fundcard?fundId=7114&fundname=TD-Cash-Management-ETF) | TCSH.TO |
| [iShares Canada](https://www.blackrock.com/ca/investors/en/products/product-list), [XSH](https://www.blackrock.com/ca/investors/en/products/239492/ishares-canadian-short-term-corporate-maple-bond-index-etf) | XSH.TO, XBB.TO, XSB.TO, XCB.TO, XGB.TO, XLB.TO, XRB.TO, CMR.TO |
| [Global X cash](https://www.globalx.ca/product/cash), [Treasury bills](https://www.globalx.ca/insights/what-are-t-bill-etfs), [HSAV report](https://www.globalx.ca/wp-content/uploads/2026/03/HSAV-EN-AR2025.pdf) | CASH.TO, HSAV.TO, CBIL.TO, UBIL.U.TO |
| [Purpose cash management](https://www.purposeinvest.com/cash-management) | PSA.TO, PSU.U.TO |
| [CI savings](https://funds.cifinancial.com/en/funds/ETFS/CIHighInterestSavingsETF.html), [Evolve savings](https://evolveetfs.com/product/HISA/) | CSAV.TO, HISA.NE |
| [BMO cash](https://www.bmoetfs.ca/articles/earn-more-on-your-cash), [bond suite](https://www.bmoetfs.ca/articles/fixed-income-heat-map-a-mid-year-temperature-check-for-canadian-bonds), [ZDB](https://www.bmoetfs.ca/etfs/zdb-bmo-discount-bond-index-etf) | ZMMK.TO, ZUCM.TO, ZST.TO, ZAG.TO, ZDB.TO, ZFL.TO, ZPL.TO |
| [Vanguard Canada](https://www.vanguard.ca/en/tools-and-resources/tax-centre) | VAB.TO, VSB.TO, VCB.TO, VLB.TO |
| [Vanguard US bond ETFs](https://investor.vanguard.com/investment-products/list/etfs?assetclass=bond) | BND, BNDX, BSV, BIV, BLV, VGSH, VGIT, VGLT, VCSH, VCIT, VCLT, VTIP, VBIL |
| [iShares US](https://www.blackrock.com/us/individual/products/investment-funds) | AGG, SGOV, SHV, SHY, IEF, TLT, TIP, LQD, HYG, TFLO, GOVT |
| [State Street BIL](https://www.ssga.com/us/en/intermediary/etfs/state-street-spdr-bloomberg-1-3-month-t-bill-etf-bil), [WisdomTree USFR](https://www.wisdomtree.com/us/products/fixed-income/usfr), [PIMCO MINT](https://www.pimco.com/us/en/investment-strategies/short-term-strategies), [JPMorgan JPST](https://am.jpmorgan.com/content/dam/jpm-am-aem/americas/us/en/literature/fact-sheet/etfs/FS-JPST.PDF) | BIL, USFR, MINT, JPST |
| [Fidelity money markets](https://www.fidelity.com/trading/faqs-about-account), [FDRXX](https://www.fidelity.com/bin-public/060_www_fidelity_com/documents/mutual-funds/us-government-debt-ceiling-and-fidelity-money-market-funds.pdf) | SPAXX, FDRXX, FZFXX |
| [Vanguard money markets](https://investor.vanguard.com/investment-products/money-markets) | VMFXX, VUSXX, VMRXX |
| [Schwab money markets](https://www.schwab.com/money-market-funds) | SWVXX, SNSXX, SNOXX |

Unlisted instruments with missing or wrong metadata still require identity enrichment; a finite symbol list cannot guarantee recognition of every future launch. Extend the independent test fixture and curated identities together when another case is verified.

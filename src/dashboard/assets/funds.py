"""Fund identity for ingestion eligibility; independent of valuation calculations.

The curated symbols protect common funds when broker metadata says ``stock``.
Canadian symbols retain their exchange suffix to avoid collisions (e.g. CASH).
Issuer references and regression coverage are documented in docs/audits/fund-ingestion.md.
"""

import re

KNOWN_ETFS = frozenset("""
XSH.TO TCSH.TO CASH.TO HSAV.TO CBIL.TO UBIL.U.TO PSA.TO PSU.U.TO
CSAV.TO HISA.NE
CMR.TO ZMMK.TO ZUCM.TO ZST.TO XBB.TO XSB.TO XCB.TO XGB.TO XLB.TO XRB.TO
ZAG.TO ZDB.TO ZFL.TO ZPL.TO VAB.TO VSB.TO VCB.TO VLB.TO
BND BNDX BSV BIV BLV VGSH VGIT VGLT VCSH VCIT VCLT VTIP VBIL
AGG BIL SGOV SHV SHY IEF TLT TIP LQD HYG USFR TFLO GOVT MINT JPST
""".split())
KNOWN_MONEY_MARKET_FUNDS = frozenset(
    "SPAXX FDRXX FZFXX VMFXX VUSXX VMRXX SWVXX SNSXX SNOXX".split()
)


def fund_type(*, asset_id=None, symbol=None, asset_type=None, asset_subtype=None,
              name=None, description=None) -> str | None:
    """Return a conservative fund type, including contradictory broker metadata."""
    identifiers = {str(value or "").strip().upper() for value in (asset_id, symbol)}
    if identifiers & KNOWN_ETFS:
        return "etf"
    if identifiers & KNOWN_MONEY_MARKET_FUNDS:
        return "mutual_fund"
    kind = str(asset_type or "").strip().lower()
    if kind in {"etf", "fund", "mutual_fund", "money_market", "index", "cash", "bond"}:
        return kind
    identity = " ".join(str(value or "") for value in (asset_subtype, name)).lower()
    if re.search(r"\betf\b|exchange[ -]traded fund", identity):
        return "etf"
    if re.search(r"money[ _-]market|mutual[ _-]fund|closed[ -]end fund|physical uranium trust", identity):
        return "fund"
    return None


def reconcile_fund_assets(conn) -> int:
    """Correct labels and retire inappropriate corporate work, retaining history."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info('asset')").fetchall()}
    if not {"asset_type", "name"} <= columns:
        return 0
    rows = conn.execute(
        "SELECT asset_id, symbol, asset_type, asset_subtype, name FROM asset"
    ).fetchall()
    corrected = 0
    for asset_id, symbol, old_type, subtype, name in rows:
        kind = fund_type(asset_id=asset_id, symbol=symbol, asset_type=old_type,
                         asset_subtype=subtype, name=name)
        if kind is None:
            continue
        if kind != old_type:
            conn.execute("UPDATE asset SET asset_type = ?, updated_at = now() WHERE asset_id = ?",
                         [kind, asset_id])
            corrected += 1
        conn.execute("""
            UPDATE ingestion_job SET status = 'unsupported',
                terminal_reason = 'company earnings and statements do not apply to funds',
                completed_at = now(), updated_at = now()
            WHERE asset_id = ? AND domain = 'corporate'
              AND status IN ('pending', 'failed', 'dead_letter')
        """, [asset_id])
        conn.execute("""
            UPDATE fundamental_subscription SET is_active = FALSE, updated_at = now()
            WHERE asset_id = ? AND is_active = TRUE
        """, [asset_id])
    return corrected

# S4 broker presentation boundary verification

## Outcome

S4 is implemented and verified on 2026-09-08. Ordinary broker import-preview and
reconciliation responses now expose a typed, allowlisted instrument identity rather
than forwarding provider-shaped symbol objects into table cells.

The change is presentation-only. Broker payload retention, database tables, account
and asset mapping, transaction normalization, import idempotency, local ledger
projection, quantity/value reconciliation calculations, and every broker write
contract are unchanged.

## Audit coverage

| Audit ID | S4 result |
| --- | --- |
| BR-01 | Reconciliation no longer renders raw nested instrument objects. Symbol, name, exchange, currency, local asset ID, resolution state, and a deterministic label are the only instrument fields in the normal response. |
| INF-05 | Persisted raw payloads are deliberately omitted from ordinary broker read models. S4 adds no diagnostic endpoint and does not alter the existing retention toggle or stored payload contract. |
| UX-06 support | Reconciliation uses a bounded desktop table and a separate narrow card layout. Long names wrap, and absent symbols receive a readable unsupported or cash-activity label. The broader broker workflow remains assigned to S5. |

## API boundary

`BrokerInstrumentDisplay` is the public instrument presentation model. Its contract is
limited to:

- `symbol`;
- `name`;
- `exchange`;
- `currency`;
- stable `local_asset_id`;
- `resolution_status` (`resolved`, `unresolved`, or `unsupported`);
- deterministic `display_label`.

`present_broker_instrument` parses only instrument-shaped symbol values and copies an
explicit scalar allowlist. It never copies the stored raw JSON, provider position or
transaction identifier, FIGI, logo URL, or unknown nested key. Pydantic response
models reject nested values for scalar display fields.

Both reconciliation and import preview use the same boundary. Compatibility scalar
fields (`ticker`, `symbol`, `asset_id`, and `currency`) remain present but are populated
from the normalized display object, not the raw provider-shaped value.

## UI behavior

- Instrument cells render the deterministic label plus available exchange, currency,
  and local asset mapping.
- Unresolved securities say `Needs local asset resolution`.
- Positions with no usable identity say `Unsupported broker instrument`.
- Cash-only contributions, withdrawals, interest, fees, and similar activity say
  `Cash activity`; absence of a symbol is not falsely presented as an instrument
  error.
- Reconciliation retains the desktop comparison table at wide widths and switches to
  a readable card view below 900px.
- Grid and scroll containers are width-bounded so wide transaction tables scroll
  internally rather than expanding the page.

## Live application passes

The running local application was inspected against the production-shaped broker data
at `http://127.0.0.1:5173/brokers?tab=import`.

1. **Raw boundary pass:** 474 rendered instrument identities were inspected. No label
   began with an object/array representation, and no visible FIGI, logo URL, nested
   currency object, or raw symbol mapping remained.
2. **Identity quality pass:** resolved examples rendered readable labels such as
   `NVDA.TO - Nvidia Corporation`; unresolved symbols remained concise and carried a
   local-resolution message. Long ETF/CDR names wrapped rather than determining the
   page width.
3. **Absent-symbol pass:** cash activities rendered `Cash activity`. Unsupported
   securities retain the explicit deterministic fallback.
4. **Narrow-layout pass:** at the available 624px viewport, reconciliation cards were
   active, the desktop reconciliation table was hidden, wide activity tables remained
   inside their scroll containers, and document-level horizontal overflow was absent.

The computer-use workflow influenced S4 in two material ways: it found a narrow grid
min-content overflow that component tests did not expose, and it distinguished valid
cash rows from genuinely unsupported instruments. Both were corrected before sign-off.

## Automated verification

- Broker presentation and Operations API files: `49 passed`.
- Frontend: `23` files, `112 passed`.
- Python lint: Ruff passed.
- Architecture boundary check: passed.
- Frontend lint: ESLint passed.
- Production frontend build: TypeScript and Vite passed.
- Full backend suite: `669 passed` with the local API stopped so DuckDB was not held
  by a separate process.

## Acceptance conclusion

The ordinary broker UI no longer receives or stringifies arbitrary instrument
objects. Every row has a readable primary identity or deterministic fallback, while
the existing broker persistence and import contracts remain intact.

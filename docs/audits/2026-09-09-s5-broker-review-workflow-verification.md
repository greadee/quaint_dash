# S5 broker review workflow verification

## Outcome

S5 is implemented and verified on 2026-09-09. The broker Import & Reconciliation
workspace now includes a read-only, paginated review queue that turns each blocked
transaction state into a scoped next step.

The slice does not change financial calculations, import idempotency, account or
asset mapping writes, broker payload retention, ledger projection, reconciliation
math, database tables, or any existing persistence contract.

## Audit coverage

| Audit ID | S5 result |
| --- | --- |
| BR-02 | The review backlog is grouped into account assignment, unresolved asset, unsupported/invalid activity, and ready-to-import queues. Each summary and row exposes a visible scoped action. |
| UX-06 | Account previews start closed, render no transaction rows until opened, reveal ten rows at a time, and state the global import scope by account before the import action. |
| UX-10 support | Queue actions, pagination, disabled controls, and prerequisite descriptions use native accessible controls and explicit labels. Broader cross-product accessibility polish remains assigned to S8. |

## Read-only review contract

`GET /api/v1/brokers/review-queue` accepts an allowlisted blocker, optional account
scope, limit, and offset. Its response contains full queue counts but at most the
requested page of normalized rows. The default and frontend page size is ten; the
API maximum is fifty.

The endpoint reuses the existing broker import-status rules. It does not run an
import, refresh a provider, create an asset, or save a mapping. Raw payloads and
account numbers remain excluded. Closed or inactive provider accounts are routed to
retained unsupported activity instead of producing dead account-assignment links.

## Workflow behavior

- **Assign accounts** opens the Accounts tab scoped to one active provider account.
  The existing assignment control remains the only mapping action and retains its
  existing confirmation behavior.
- **Resolve assets** opens a scoped, read-only candidate view carrying blocker,
  account, transaction, and normalized symbol context. Candidate asset links retain
  a return path to the same queue.
- **Unsupported or invalid** explains why the retained transaction cannot import;
  it offers no misleading mutation.
- **Ready to import** returns the user to the explicit per-account import scope.
- Previous/next paging preserves the selected blocker and account scope.

Disabled assignment controls now reference visible prerequisite text through
`aria-describedby`. When no local portfolio exists, the user can create one inline
or follow the direct New Portfolio route.

## Scale and rendered checks

The live application was inspected at the available narrow viewport against the
production-shaped broker dataset:

- the review summaries represented the complete multi-thousand-row backlog;
- only ten review rows were present in the document at once;
- sixteen account preview groups started closed with zero preview transaction rows
  rendered;
- the import action stated that 59 eligible transactions across six assigned
  accounts were in scope;
- unresolved-asset navigation retained broker account and transaction context and
  returned one normalized local candidate;
- active account navigation rendered exactly one scoped account and two responsive
  representations of the same described assignment control;
- closed/inactive account rows no longer linked to an empty resolver;
- no document-level horizontal overflow was present.

The computer-use pass materially influenced the result by finding the inactive
account dead-link condition, which component fixtures did not initially expose.

## Automated verification

- Broker and Operations API module: `47 passed`.
- Frontend suite: `23` files, `114 passed`.
- Python lint: Ruff passed.
- Architecture boundary check: passed.
- Frontend lint: ESLint passed.
- Production frontend build: TypeScript and Vite passed.
- Full backend suite: `670 passed` with the local API stopped so DuckDB was not held
  by a separate process.

## Acceptance conclusion

The broker review backlog is now safe to browse, bounded at scale, and connected to
the correct existing account or read-only asset-resolution pathway without changing
the persistence boundary. Import scope and blocked-control prerequisites are stated
before users reach the corresponding actions.

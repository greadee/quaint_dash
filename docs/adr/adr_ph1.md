
# Phase 0 - Project Setup and CLI skeleton

## ADR-000: Focus on app function over form

**Deicision:**
Ensure the dashboard is robust and useful before it is pretty.

**Rationale:** 
- I want to put it into use for myself once it is good.
- I do not want to plan the UI before I know all I want the dashboard to do.

**Status:** Implemented

---

## ADR-001: Test CLI Using monkeypatch and capsys

**Decision:**  
Use pytest with:
- `monkeypatch` for input()
- `capsys` for printed output

**Context:**  
Need full CLI/TUI coverage.

**Rationale:**
- Simulates user interaction
- Ensures output stability
- Validates interactive prompts

**Status:** Implemented

---


# Phase 1 - Data Model and TUI upgrade

Established the data model, core architecture, layering, separation of concerns, and testing strategy.

---

## ADR-003: Use DuckDB as the Primary Database

**Decision:**  
Use DuckDB for embedded SQL database management.

**Context:**  
The app is a CLI/TUI portfolio manager that needs:
- SQL queries
- Lightweight embedded storage
- No external DB server
- Strong analytics more important than rapid real-time data processing

**Rationale:**
- Zero configuration
- Embedded 
- Concurrency is not a concern

**Status:** Implemented

---

## ADR-004: Introduce a DB Wrapper Class

**Decision:**  
Encapsulate the DuckDB connection in a `DB` class with an `init_db()` function.

**Context:**  
Calling `duckdb.connect()` everywhere tightly couples the database to all layers.

**Rationale:**
- Centralized DB connection
- Easier test isolation
- Cleaner injection into managers

**Status:** Implemented

---

## ADR-005: Separate Domain Models from Storage Logic

**Decision:**  
Create domain model classes (`Txn`, `Position`, `Portfolio`, etc.) separate from SQL queries.

**Context:**  
We need structured objects to represent data returned from SQL.

**Rationale:**
- Prevents raw tuples from leaking through layers
- Enables formatting and validation
- Clean separation of concerns
- Easier to test and validate

**Status:** Implemented

---

## ADR-064: PortfolioManager belongs to, but is not a DashboardManager

**Decision:**  
Keep `DashboardManager` and `PortfolioManager` as separate classes.

**Context:**  
- Dashboard operations apply globally
- Portfolio operations apply to one portfolio
- Each one is associated with it's respective View

**Rationale:**
- They represent different responsibilities
- The domain of the DashboardManager is strictly the union of all PortfolioManagers
    - (+) the waitlist to be implemented later
- Simpler for a foundation 

**Status:** Accepted

---


## ADR-007: Normalize Date Inputs Before SQL Queries

**Decision:**  
Normalize user date input into Python `date` before querying.

**Context:**  
Mismatch between display format and SQL timestamp.

**Rationale:**
- Prevents format mismatch bugs
- Keeps CLI consistent
- Avoids SQL casting complexity
- Cleaner error handling

**Status:** Implemented

---

## ADR-008 Keep Database as Source of Truth for Positions

**Decision:**  
Positions are updated via SQL and recalculated based on transactions.

**Context:**  
In-memory recalculation was considered.

**Rationale:**
- DB guarantees consistency
- Prevents divergence
- Easier to test
- Avoids caching bugs

**Status:** Implemented

---

## ADR-009: CLI View Layer Separate from CLI 

**Decision:**  
Construct argument parsers inside `DashboardView` and `PortfolioView`, rather than in `cli.py`.

**Context:**  
Each view has its own command set and behavior.

**Rationale:**
- Views handle user input + display
- Keeps commands close to the view that executes them
- Seperate business and cmd parsing logic
- CLI loop runs cleaner 

**Status:** Implemented

---

## ADR-010: Introduce a Formatter class over pandas 

**Decision:**  
Create formatter classes such as:
- `TxnTableFormatter`
- `PositionTableFormatter`
- `PortfolioTableFormatter`
- etc.

**Context:**  
CLI displays need to be more than just object instances.
- Table headers
- Entry printing
- Predictable CLI formatting
- Test-stable output

**Rationale:**
- Keeps domain models pure
- Consistent and central formatting logic
- Lighter than dataframes
- Makes capsys testing predictable
- I do not think pandas dataframes fit the TUI style

**Status:** Implmented

---

## ADR-011 Seperate Formatter UML diagram

**Decision:**
Make the UML diagram for the Formatter class seperate from the main UMl diagram.

**Context:**
With the Formatters included, the core components were hard to decipher.

**Rationale:** 
- Keeps lighter weight interface-type classes from dominating the component diagram
- Better readability
- Can implement other domain-model tied classes into the same diagram 
    - as what all is associated with all domain classes

**Status:** Implemented








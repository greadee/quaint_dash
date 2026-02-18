
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

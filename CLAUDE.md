# CLAUDE.md — Project context for Claude Code

## Project overview

NSF-style grant budget calculator. Terminal-based interactive Python script that computes year-by-year budgets with inflation, fringe, indirect costs, and subaward handling.

## Key files

- `budget.py` — Main script. Contains importable functions (`load_parameters`, `dollar`, `calculate_budget`) and an interactive `main()` entry point.
- `budget.par` — Parameter file with institutional rates and default values. Parsed as `key = value` with `#` comments.
- `budget.log` — Append-only run log (auto-generated, do not commit).
- `budget_110724.py` — Legacy version kept for reference. Do not modify.
- `tests/test_budget.py` — Test suite.

## Architecture

- `load_parameters(path)` — Reads `budget.par` into a dict.
- `dollar(amount)` — Formats floats as `$1,234.56`.
- `calculate_budget(...)` — Pure function: takes all inputs, returns `{tdc, mtdc, indirect, yearly, details}` dict. No I/O. This is the testable core.
- `main()` — Interactive wrapper: reads params, prompts user, calls `calculate_budget`, logs output.

## Budget math

- **MTDC** = TDC - grad_fees - grad_insurance - subaward
- **Indirect** = indirect_rate * MTDC + indirect_rate * min(subaward, $25k)
- **Fringe** = (0.25 * grad_salary + undergrad_salary + faculty_salary) * fringe_rate + fulltime_fringe * postdoc_salary
- The 0.25 factor is the grad summer fraction (3 months / 12) — only summer wages are subject to FICA.
- "Total Fringe" is payroll-tax fringe only; postdoc health insurance is a separate line item.
- Inflation is applied at the end of each year to salaries, stipends, and fees.

## Testing

```bash
pytest                   # run all tests
pytest -v                # verbose
pytest tests/test_budget.py::TestCalculateBudget  # specific test class
```

Tests mock `input()` for integration tests. Unit tests call `calculate_budget()` directly.

## Conventions

- Python 3.6+ (f-strings required).
- No third-party dependencies in the main script.
- Rates are always expressed as decimals (0.59 = 59%), never percentages.
- All monetary values displayed with `dollar()` formatting.

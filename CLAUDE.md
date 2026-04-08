# CLAUDE.md — Project context for Claude Code

## Project overview

NSF-style grant budget calculator. The curses-based TUI (`budget_tui.py`) is the primary interface. A CLI (`budget_partial_years.py`) is also available. Both share a common calculation engine with partial-year support. Previous versions are preserved in git history.

## Key files

- `budget_tui.py` — Curses-based TUI (Pine/Alpine style). Primary interface. Imports the calculation engine from `budget_partial_years.py`. Menu-driven interface with arrow-key navigation, field editing, live total estimate, and scrollable results.
- `budget_partial_years.py` — Calculation engine and CLI. Contains `calculate_budget`, `compute_period_fractions`, `summer_months_in_period`, `load_parameters`, `dollar`. Supports partial/fractional budget periods with exact day counts (`days / 365.25`).
- `budget.par` — Parameter file with institutional rates and zeroed default values. Parsed as `key = value` with `#` comments.
- `budget.log` — Append-only run log (auto-generated, do not commit).
- `tests/test_budget_partial_years.py` — Test suite for `budget_partial_years.py`.
- `tests/test_budget_tui.py` — Test suite for `budget_tui.py` (state, validation, summaries).

## Architecture

### Core calculation (budget_partial_years.py)

- `load_parameters(path)` — Reads `budget.par` into a dict.
- `dollar(amount)` — Formats floats as `$1,234.56`.
- `calculate_budget(...)` — Pure function: takes all inputs, returns `{tdc, mtdc, indirect, yearly, details}` dict. No I/O. This is the testable core.
- `main()` — CLI wrapper: reads params, prompts user, calls `calculate_budget`, logs output.

### Partial-year functions (budget_partial_years.py)

- `summer_months_in_period(start_date, end_date)` — Counts how many of {June, July, August} are fully contained within the half-open interval `[start_date, end_date)`.
- `compute_period_fractions(start_date, end_date)` — Splits a project date range into anniversary-aligned budget periods. Accepts any valid dates. Returns a list of period dicts with keys: `start`, `end`, `duration_days`, `frac`, `summer_months`.
- `_anniversary(d)` — Returns the same month/day one year later; Feb 29 falls back to Feb 28 in non-leap years.

### TUI (budget_tui.py)

- `BudgetState` — Central state class holding all budget inputs. Initialized from `budget.par`. Methods: `from_par_file()`, `to_calc_args()`, `recompute_estimate()`, `finalize()`, `resize_subaward()`, `validate_field()`.
- `PIInfo` — Holds per-PI base salary and summer months.
- `MENU_ITEMS` — List of (label, summary_fn) tuples defining the main menu.
- Summary functions — `summary_dates()`, `summary_pis()`, `summary_grads()`, etc.
- `FieldEditor` — Character-by-character text field editing within curses.
- `format_results()` — Formats budget results as lines matching CLI output format.
- `write_log()` — Appends formatted results to `budget.log`.

## Budget math

- **MTDC** = TDC - grad_fees - subaward - equipment
- **Indirect** = indirect_rate * MTDC + indirect_rate * min(subaward, $25k)
- **Fringe** = (0.25 * grad_salary + undergrad_salary + faculty_salary) * fringe_rate + fulltime_fringe * postdoc_salary
- grad_salary, grad_fees, and grad_ins passed to `calculate_budget` are totals across all graduate students (number_grads x per-student value). All graduate students are assumed to have the same stipend, fees, and insurance.
- The 0.25 factor is the grad summer fraction (3 months / 12) -- only summer wages are subject to FICA.
- "Total Fringe" is payroll-tax fringe only; postdoc health insurance is a separate line item.
- "Grad Fringe + Health Ins" combines graduate payroll-tax fringe with graduate health insurance into a single display line. Health insurance is included in the MTDC base (not excluded like tuition).
- Equipment is a fixed yearly cost excluded from MTDC (no inflation applied).
- Inflation is applied at the end of each year to salaries, stipends, and fees.
- Output includes both an NSF-style detailed table and a NASA R&R budget format summary.

### Partial-period scaling (budget_partial_years.py)

When `period_fractions` is provided to `calculate_budget`:
- All annual costs (salaries, stipends, fees, travel, pub_costs, health insurance) are scaled by `frac = days / 365.25`.
- Equipment and subawards are NOT scaled (already per-period values).
- Grad summer fraction = `summer_months / 12.0` per period (replaces hardcoded 0.25).
- Inflation compounds as `(1 + r) ^ frac` for fractional periods; uses exact `(1 + r)` for full years to avoid float divergence.
- Subaward indirect cap prorated to `$25k x frac`.
- When no dates are provided, all periods default to full 12-month years.

## Testing

```bash
pytest                   # run all tests (139 total)
pytest -v                # verbose
pytest tests/test_budget_partial_years.py  # calculation engine (43 tests)
pytest tests/test_budget_tui.py            # TUI state & validation (50 tests)
```

CI runs `pytest tests/ -v` on Python 3.9 and 3.12 via GitHub Actions.

## Conventions

- Python 3.6+ (f-strings required).
- No third-party dependencies in the main scripts (`curses` is stdlib).
- Rates are always expressed as decimals (0.59 = 59%), never percentages.
- All monetary values displayed with `dollar()` formatting.

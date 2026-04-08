[![Tests](https://github.com/rtfisher/grant-budget-calculator/actions/workflows/tests.yml/badge.svg)](https://github.com/rtfisher/grant-budget-calculator/actions/workflows/tests.yml)

# Grant Budget Calculator

A Python tool for calculating research grant budgets with year-by-year inflation, fringe benefits, indirect costs, and subaward handling. Features a curses-based TUI with partial budget period support.

## Files

| File | Purpose |
|------|---------|
| `budget_tui.py` | Curses-based TUI -- menu-driven interface with live totals |
| `budget_partial_years.py` | Calculation engine and CLI alternative |
| `budget.par` | Editable parameter file with institutional rates and default values |
| `budget.log` | Append-only log of all runs (auto-generated) |

## Quick Start

```bash
python budget_tui.py               # TUI (primary interface)
python budget_partial_years.py     # CLI alternative
```

The TUI reads default rates from `budget.par` and presents a menu where you navigate budget categories with arrow keys, edit values, and finalize the budget. The CLI prompts interactively; press Enter to accept the default shown in brackets.

## TUI Interface

`budget_tui.py` provides a Pine/Alpine-style menu interface:

- **Arrow keys** navigate budget categories (Project Dates, Senior Investigators, Graduate Students, Postdocs, etc.)
- **Enter** opens a sub-screen to edit values for that category
- **F** finalizes the budget and displays results in a scrollable view
- **S** saves results to `budget.log` (on the results screen)
- **Q** quits (with confirmation if unsaved)

The TUI supports partial budget periods via the Project Dates menu item (Tab toggles between date mode and year mode).

## Parameter File (`budget.par`)

Institutional rates live in `budget.par`, a plain text file with `key = value` format. Lines starting with `#` are comments. Edit this file to update rates for a new fiscal year without modifying the script.

Key parameters:

| Parameter | Description | Example |
|-----------|-------------|---------|
| `indirect_rate` | F&A (indirect) cost rate | `0.59` |
| `fringe_rate` | Payroll tax rate (FICA) for part-time/summer wages | `0.0221` |
| `fulltime_fringe` | Full-time employee fringe benefit rate | `0.3781` |
| `inflation` | Annual salary/fee inflation rate | `0.03` |

Consult with your institutional office of research administration for current rates.

## Budget Calculation Details

- **Faculty salary**: Computed from 9-month base salary and number of summer months requested. Supports multiple PIs.
- **Fringe**: Payroll tax (`fringe_rate`) applies to faculty summer salary, graduate student summer stipend (25% of annual), and undergraduate salary. Postdocs use the full-time fringe rate.
- **Graduate students**: Annual stipend + tuition/fees + health insurance. Tuition/fees are excluded from MTDC; health insurance is part of fringe and remains in the MTDC base.
- **Equipment**: Fixed yearly cost, excluded from MTDC (no inflation).
- **Subawards**: Per-year amounts, excluded from MTDC. Indirect is charged on the first $25,000 of each year's subaward per NSF policy.
- **Inflation**: Applied at the end of each year to salaries, stipends, and fees for the following year.
- **Indirect (F&A)**: Applied to MTDC plus the capped subaward amount.

## Partial Budget Periods

`budget_partial_years.py` and `budget_tui.py` support fractional budget periods for grants whose duration is not a whole number of years (e.g., a 33-month award).

- Specify a **project start date** and **end date** (any dates -- no restriction to 1st of month).
- Budget periods are split at anniversary boundaries of the start date. The last period may be shorter.
- All annual costs are prorated by `days / 365.25` for each period. Equipment and subaward values are per-period and not scaled.
- **Summer months** (June, July, August) for graduate FICA are computed from the actual calendar overlap of each period, rather than using a hardcoded 3/12 fraction.
- Inflation compounds as `(1 + r) ^ frac` for fractional periods.
- The subaward indirect cap ($25k) is prorated for fractional periods.
- Skipping the date prompt (or using year mode in the TUI) gives full calendar years.

## Output Formats

The calculator produces two budget tables:

1. **NSF-style detailed table** -- Line-by-line breakdown of all salary, fringe, and cost components.
2. **NASA R&R budget format** -- Standard federal R&R categories (A-K): Senior/Key Person, Other Personnel, Equipment, Travel, Participant/Trainee Support, Other Direct Costs, Direct/Indirect totals, Fee, and Budget Total.

## Logging

Each run appends a timestamped record to `budget.log` containing:
- All input parameters as entered
- Per-PI base salary and summer months (for full reproducibility)
- Year-by-year budget breakdown
- Final summary totals

## Requirements

- Python 3.6+
- No third-party dependencies (`curses` is in the Python standard library)
- Windows users need `pip install windows-curses` for the TUI

## Running Tests

```bash
pip install pytest
pytest                                    # run all tests
pytest tests/test_budget_partial_years.py  # calculation engine tests
pytest tests/test_budget_tui.py            # TUI tests
```

CI runs on Python 3.9 and 3.12 via GitHub Actions on every push and PR to main.

## Acknowledgments

Robert Fisher + Claude Opus (Anthropic).

## License

[MIT License](LICENSE)

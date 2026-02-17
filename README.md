[![Tests](https://github.com/rtfisher/grant-budget-calculator/actions/workflows/tests.yml/badge.svg)](https://github.com/rtfisher/grant-budget-calculator/actions/workflows/tests.yml)

# Grant Budget Calculator

A terminal-based Python script for calculating research grant budgets with year-by-year inflation, fringe benefits, indirect costs, and subaward handling.

## Files

| File | Purpose |
|------|---------|
| `budget.py` | Main budget calculator script |
| `budget.par` | Editable parameter file with institutional rates and default values |
| `budget.log` | Append-only log of all runs (auto-generated) |

## Quick Start

```bash
python budget.py
```

The script reads default values from `budget.par` and prompts interactively for all inputs. Press Enter at any prompt to accept the default shown in brackets.

## Parameter File (`budget.par`)

Institutional rates and default salary values live in `budget.par`, a plain text file with `key = value` format. Lines starting with `#` are comments. Edit this file to update rates for a new fiscal year without modifying the script.

Key parameters:

| Parameter | Description | Example |
|-----------|-------------|---------|
| `indirect_rate` | F&A (indirect) cost rate | `0.59` |
| `fringe_rate` | Payroll tax rate (FICA) for part-time/summer wages | `0.0211` |
| `fulltime_fringe` | Full-time employee fringe benefit rate | `0.4531` |
| `inflation` | Annual salary/fee inflation rate | `0.03` |

Consult with your institutional office of research administration for current rates.

## Budget Calculation Details

- **Faculty salary**: Computed from 9-month base salary and number of summer months requested. Supports multiple PIs.
- **Fringe**: Payroll tax (`fringe_rate`) applies to faculty summer salary, graduate student summer stipend (25% of annual), and undergraduate salary. Postdocs use the full-time fringe rate.
- **Graduate students**: Annual stipend + tuition/fees + health insurance. Tuition/fees and health insurance are excluded from MTDC.
- **Subawards**: Per-year amounts, excluded from MTDC. Indirect is charged on the first $25,000 of each year's subaward per NSF policy.
- **Inflation**: Applied at the end of each year to salaries, stipends, and fees for the following year.
- **Indirect (F&A)**: Applied to MTDC plus the capped subaward amount.

## Logging

Each run appends a timestamped record to `budget.log` containing:
- All input parameters as entered
- Year-by-year budget breakdown
- Final summary totals

## Requirements

- Python 3.6+
- No third-party dependencies

## Running Tests

```bash
pip install pytest
pytest
```

## Acknowledgments

Claude (Anthropic) collaborated with rtfisher on refactoring and CI/CD integration.

## License

[MIT License](LICENSE)

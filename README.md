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

## Sample Output

```
Input Parameters
---------------------------------
  Number of years              = 3
  Number of faculty            = 1
  Faculty salary (year 1)      = $2,777.78
  Graduate stipend             = $35,000.00
  Graduate tuition + fees      = $12,415.00
  Graduate health insurance    = $1,395.00
  Undergraduate salary         = $5,000.00
  Postdoc salary               = $75,000.00
  Postdoc health               = $2,000.00
  Travel                       = $5,000.00
  Publication costs            = $1,000.00
  Subawards                    = [0, 0, 0]
  Indirect rate                = 0.59
  Fringe (payroll tax) rate    = 0.0211
  Full-time fringe rate        = 0.4531
  Inflation rate               = 0.03


                                          Year 1          Year 2          Year 3           Total
------------------------------------------------------------------------------------------------
                  Faculty Salary       $2,777.78       $2,861.11       $2,946.94       $8,585.83
                  Faculty Fringe          $58.61          $60.37          $62.18         $181.16
                 Graduate Salary      $35,000.00      $36,050.00      $37,131.50     $108,181.50
                 Graduate Fringe         $184.62         $190.16         $195.87         $570.66
                  Postdoc Salary      $75,000.00      $77,250.00      $79,567.50     $231,817.50
                  Postdoc Fringe      $33,982.50      $35,001.97      $36,052.03     $105,036.51
                   Total Postdoc     $110,982.50     $114,251.98     $117,619.53     $342,854.01
            Undergraduate Salary       $5,000.00       $5,150.00       $5,304.50      $15,454.50
                    Total Fringe      $34,331.24      $35,361.17      $36,422.01     $106,114.42
   Graduate Tuition + Health Ins      $13,810.00      $14,224.30      $14,651.03      $42,685.33
                          Travel       $5,000.00       $5,000.00       $5,000.00      $15,000.00
               Publication Costs       $1,000.00       $1,000.00       $1,000.00       $3,000.00
                        Subaward           $0.00           $0.00           $0.00           $0.00
------------------------------------------------------------------------------------------------
     Modified Total Direct Costs     $160,109.01     $164,672.28     $169,372.45     $494,153.75
                        Indirect      $94,464.32      $97,156.65      $99,929.75     $291,550.71
------------------------------------------------------------------------------------------------
                    Total Direct     $173,919.01     $178,896.58     $184,023.48     $536,839.08
                    Total Budget     $268,383.33     $276,053.23     $283,953.23     $828,389.79
```

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

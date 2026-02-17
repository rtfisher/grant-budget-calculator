# A short python script to calculate NSF-style budget
# RTF, 10/31/15
# See budget_110724.py for full revision history.
# 2/16/26 : Refactored to read defaults from budget.par parameter file,
#           removed numpy dependency, added currency formatting,
#           fixed Python 2 print remnants, extracted testable functions.
# 2/16/26 : Restructured output to tabular format.

import os
import sys
from datetime import datetime

PAR_FILE = "budget.par"
LOG_FILE = "budget.log"


def load_parameters(path):
    """Read key=value pairs from a parameter file, ignoring comments and blanks."""
    params = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, value = line.partition("=")
            if not sep:
                continue
            params[key.strip()] = value.strip()
    return params


def dollar(amount):
    """Format a number as a dollar amount."""
    return f"${amount:,.2f}"


# Grad students are on fellowship during the academic year (exempt from payroll tax).
# Only the summer fraction (3 months / 12 = 0.25) is wages subject to FICA.
GRAD_SUMMER_FRACTION = 0.25

# NSF caps indirect on subawards at $25k per year
SUBAWARD_INDIRECT_CAP = 25000


def calculate_budget(number_years, faculty_salary, grad_salary, grad_fees, grad_ins,
                     undergrad_salary, postdoc_salary, postdoc_health, travel, pub_costs,
                     subaward, indirect_rate, fringe_rate, fulltime_fringe, inflation):
    """Calculate the year-by-year budget and return results as a dict.

    All salary/fee arguments are year-1 values; inflation is applied for
    subsequent years inside this function.  The subaward argument is a list
    of length number_years.

    Returns a dict with keys:
        tdc, mtdc, indirect, yearly  — lists of length number_years
        details — list of per-year detail dicts (for display / logging)
    """
    tdc = [0.0] * number_years
    mtdc = [0.0] * number_years
    indirect = [0.0] * number_years
    details = []

    for year in range(number_years):
        fringe = ((GRAD_SUMMER_FRACTION * grad_salary + undergrad_salary + faculty_salary) * fringe_rate
                  + fulltime_fringe * postdoc_salary)

        tdc[year] = (faculty_salary + grad_salary + grad_fees + grad_ins
                     + postdoc_salary + undergrad_salary + travel + pub_costs
                     + fringe + postdoc_health + subaward[year])

        mtdc[year] = tdc[year] - grad_fees - grad_ins - subaward[year]

        indirect[year] = indirect_rate * mtdc[year]

        # NSF: indirect on subawards applies to the first $25k of each year's subaward
        subaward_mtdc = min(subaward[year], SUBAWARD_INDIRECT_CAP)
        indirect[year] += indirect_rate * subaward_mtdc

        details.append({
            "year": year + 1,
            "faculty_salary": faculty_salary,
            "faculty_fringe": faculty_salary * fringe_rate,
            "grad_salary": grad_salary,
            "grad_fringe": GRAD_SUMMER_FRACTION * grad_salary * fringe_rate,
            "postdoc_salary": postdoc_salary,
            "postdoc_fringe": postdoc_salary * fulltime_fringe,
            "total_postdoc": (1 + fulltime_fringe) * postdoc_salary + postdoc_health,
            "undergrad_salary": undergrad_salary,
            "total_fringe": fringe,
            "grad_tuition_health": grad_fees + grad_ins,
            "travel": travel,
            "pub_costs": pub_costs,
            "subaward": subaward[year],
            "subaward_mtdc": subaward_mtdc,
            "mtdc": mtdc[year],
            "indirect": indirect[year],
        })

        # Inflate for next year
        faculty_salary *= (1.0 + inflation)
        grad_salary *= (1.0 + inflation)
        postdoc_salary *= (1.0 + inflation)
        grad_fees *= (1.0 + inflation)
        grad_ins *= (1.0 + inflation)
        undergrad_salary *= (1.0 + inflation)

    yearly = [tdc[y] + indirect[y] for y in range(number_years)]

    return {"tdc": tdc, "mtdc": mtdc, "indirect": indirect, "yearly": yearly, "details": details}


# ── Interactive entry point ──────────────────────────────────────────

def main():
    # Load parameter file
    if not os.path.exists(PAR_FILE):
        print(f"Error: parameter file '{PAR_FILE}' not found.")
        print("Place budget.par in the current directory and re-run.")
        sys.exit(1)

    params = load_parameters(PAR_FILE)

    logfile = open(LOG_FILE, "a")

    def log(msg=""):
        """Print to both stdout and the log file."""
        print(msg)
        logfile.write(msg + "\n")

    log("Basic Grant Budget Calculator")
    log("Robert Fisher, 11/2/2016")
    log("Refactored 2/16/2026 — defaults read from budget.par")
    log(f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log()

    # Convenience: look up a default from the parameter file
    def default(key):
        return params.get(key, "0")

    # ── Number of years and PIs ──────────────────────────────────────

    number_years = int(input("Enter number of years [3]: ") or "3")
    if number_years < 1:
        print("Error: number of years must be at least 1.")
        sys.exit(1)

    number_pis = int(input("Enter number of supported faculty [1]: ") or "1")
    if number_pis < 0:
        print("Error: number of faculty cannot be negative.")
        sys.exit(1)

    # ── Salaries & Fees ──────────────────────────────────────────────

    faculty_salary = 0.0

    d_base = default("faculty_base_salary")
    d_months = default("faculty_months")

    for pi in range(number_pis):
        print(f"Entering 9-month salary for faculty investigator {pi + 1}")
        base_salary = int(input(f"  Enter base 9-month faculty salary [{d_base}]: ") or d_base)
        monthly_salary = base_salary / 9.0
        months_salary = float(input(f"  Enter number of summer months faculty salary [{d_months}]: ") or d_months)
        faculty_salary += months_salary * monthly_salary

    d_grad = default("grad_stipend")
    d_fees = default("grad_fees")
    d_ins = default("grad_insurance")
    d_ugrad = default("undergrad_salary")
    d_postdoc = default("postdoc_salary")
    d_phealth = default("postdoc_health")

    grad_salary = int(input(f"Enter graduate student annual stipend [{d_grad}]: ") or d_grad)
    grad_fees = float(input(f"Enter graduate student tuition + fees [{d_fees}]: ") or d_fees)
    grad_ins = float(input(f"Enter graduate student health insurance [{d_ins}]: ") or d_ins)
    undergrad_salary = int(input(f"Enter undergraduate student salary [{d_ugrad}]: ") or d_ugrad)
    postdoc_salary = int(input(f"Enter postdoc salary [{d_postdoc}]: ") or d_postdoc)
    postdoc_health = int(input(f"Enter postdoc health [{d_phealth}]: ") or d_phealth)

    # ── Travel and publication costs ─────────────────────────────────

    d_travel = default("travel")
    d_pub = default("pub_costs")

    travel = int(input(f"Enter yearly travel costs [{d_travel}]: ") or d_travel)
    pub_costs = int(input(f"Enter yearly publication costs [{d_pub}]: ") or d_pub)

    # ── Subawards ────────────────────────────────────────────────────

    while True:
        try:
            print(f"Enter subaward as {number_years} integers, e.g., 1000 2000 ..., or press Enter for all zero:")
            user_input = input().strip()

            if not user_input:
                subaward = [0] * number_years
            else:
                subaward = [int(x) for x in user_input.split()]
                if len(subaward) != number_years:
                    raise ValueError(f"Please enter exactly {number_years} integers.")
            break
        except ValueError as e:
            print(f"Error: {e}. Try again.")

    total_subaward = sum(subaward)

    log(f"Subaward values: {subaward}")
    log(f"Total Subaward: {dollar(total_subaward)}")

    # ── Rates ────────────────────────────────────────────────────────

    d_indirect = default("indirect_rate")
    d_fringe = default("fringe_rate")
    d_ft = default("fulltime_fringe")
    d_infl = default("inflation")

    indirect_rate = float(input(f"Enter indirect rate [{d_indirect}]: ") or d_indirect)
    fringe_rate = float(input(f"Enter fringe rate [{d_fringe}]: ") or d_fringe)
    fulltime_fringe = float(input(f"Enter full time employee fringe rate [{d_ft}]: ") or d_ft)
    inflation = float(input(f"Enter annual rate of inflation for salaries, stipends, and fees [{d_infl}]: ") or d_infl)

    for name, val in [("indirect_rate", indirect_rate), ("fringe_rate", fringe_rate),
                      ("fulltime_fringe", fulltime_fringe), ("inflation", inflation)]:
        if not 0.0 <= val <= 1.0:
            print(f"Warning: {name} = {val} is outside [0, 1]. Did you mean {val/100:.4f}?")

    # ── Log input parameters ─────────────────────────────────────────

    logfile.write("=" * 60 + "\n")
    log("Input Parameters")
    log("---------------------------------")
    log(f"  Number of years              = {number_years}")
    log(f"  Number of faculty            = {number_pis}")
    log(f"  Faculty salary (year 1)      = {dollar(faculty_salary)}")
    log(f"  Graduate stipend             = {dollar(grad_salary)}")
    log(f"  Graduate tuition + fees      = {dollar(grad_fees)}")
    log(f"  Graduate health insurance    = {dollar(grad_ins)}")
    log(f"  Undergraduate salary         = {dollar(undergrad_salary)}")
    log(f"  Postdoc salary               = {dollar(postdoc_salary)}")
    log(f"  Postdoc health               = {dollar(postdoc_health)}")
    log(f"  Travel                       = {dollar(travel)}")
    log(f"  Publication costs            = {dollar(pub_costs)}")
    log(f"  Subawards                    = {subaward}")
    log(f"  Indirect rate                = {indirect_rate}")
    log(f"  Fringe (payroll tax) rate    = {fringe_rate}")
    log(f"  Full-time fringe rate        = {fulltime_fringe}")
    log(f"  Inflation rate               = {inflation}")
    log()

    # ── Calculate budget ─────────────────────────────────────────────

    results = calculate_budget(
        number_years, faculty_salary, grad_salary, grad_fees, grad_ins,
        undergrad_salary, postdoc_salary, postdoc_health, travel, pub_costs,
        subaward, indirect_rate, fringe_rate, fulltime_fringe, inflation)

    tdc = results["tdc"]
    indirect = results["indirect"]
    yearly = results["yearly"]

    # ── Budget table ──────────────────────────────────────────────────

    details = results["details"]

    line_items = [
        ("Faculty Salary",                "faculty_salary"),
        ("Faculty Fringe",                "faculty_fringe"),
        ("Graduate Salary",               "grad_salary"),
        ("Graduate Fringe",               "grad_fringe"),
        ("Postdoc Salary",                "postdoc_salary"),
        ("Postdoc Fringe",                "postdoc_fringe"),
        ("Total Postdoc",                 "total_postdoc"),
        ("Undergraduate Salary",          "undergrad_salary"),
        ("Total Fringe",                  "total_fringe"),
        ("Graduate Tuition + Health Ins", "grad_tuition_health"),
        ("Travel",                        "travel"),
        ("Publication Costs",             "pub_costs"),
        ("Subaward",                      "subaward"),
    ]

    label_w = 32
    col_w = 16

    def table_row(label, values, total):
        cols = "".join(f"{dollar(v):>{col_w}}" for v in values)
        return f"{label:>{label_w}}{cols}{dollar(total):>{col_w}}"

    header = (f"{'':>{label_w}}"
              + "".join(f"{'Year ' + str(y+1):>{col_w}}" for y in range(number_years))
              + f"{'Total':>{col_w}}")
    sep = "-" * len(header)

    log()
    log(header)
    log(sep)

    for label, key in line_items:
        vals = [d[key] for d in details]
        log(table_row(label, vals, sum(vals)))

    log(sep)

    mtdc_vals = [d["mtdc"] for d in details]
    log(table_row("Modified Total Direct Costs", mtdc_vals, sum(mtdc_vals)))

    ind_vals = list(indirect)
    log(table_row("Indirect", ind_vals, sum(ind_vals)))

    log(sep)

    log(table_row("Total Direct", tdc, sum(tdc)))
    log(table_row("Total Budget", yearly, sum(yearly)))

    # Subaward indirect notes
    if any(d["subaward_mtdc"] > 0 for d in details):
        log()
        for d in details:
            if d["subaward_mtdc"] > 0:
                log(f"  Note: Year {d['year']} subaward indirect (on first $25k) = {dollar(indirect_rate * d['subaward_mtdc'])}")

    logfile.write("\n")
    logfile.close()
    print(f"Results saved to {LOG_FILE}")


if __name__ == "__main__":
    main()

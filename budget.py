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
                     subaward, indirect_rate, fringe_rate, fulltime_fringe, inflation,
                     equipment=0):
    """Calculate the year-by-year budget and return results as a dict.

    All salary/fee arguments are year-1 values; inflation is applied for
    subsequent years inside this function.  The subaward argument is a list
    of length number_years.  Equipment is a fixed yearly cost (no inflation).

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
                     + fringe + postdoc_health + subaward[year] + equipment)

        mtdc[year] = tdc[year] - grad_fees - subaward[year] - equipment

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
            "undergrad_fringe": undergrad_salary * fringe_rate,
            "total_fringe": fringe,
            "fringe_health": fringe + grad_ins,
            "grad_fees": grad_fees,
            "grad_ins": grad_ins,
            "grad_tuition_health": grad_fees + grad_ins,
            "postdoc_health": postdoc_health,
            "travel": travel,
            "pub_costs": pub_costs,
            "equipment": equipment,
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
    pi_details = []

    d_base = default("faculty_base_salary")
    d_months = default("faculty_months")

    for pi in range(number_pis):
        print(f"Entering 9-month salary for faculty investigator {pi + 1}")
        base_salary = int(input(f"  Enter base 9-month faculty salary [{d_base}]: ") or d_base)
        monthly_salary = base_salary / 9.0
        months_salary = float(input(f"  Enter number of summer months faculty salary [{d_months}]: ") or d_months)
        pi_contrib = months_salary * monthly_salary
        faculty_salary += pi_contrib
        pi_details.append({
            "base_salary": base_salary,
            "months": months_salary,
            "contribution": pi_contrib,
        })

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

    # ── Equipment, travel, and publication costs ─────────────────────

    d_equip = default("equipment")
    d_travel = default("travel")
    d_pub = default("pub_costs")

    equipment = int(input(f"Enter yearly equipment costs [{d_equip}]: ") or d_equip)
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
    for i, pid in enumerate(pi_details):
        log(f"    PI {i + 1}: base 9-month salary = {dollar(pid['base_salary'])}, "
            f"summer months = {pid['months']}, contribution = {dollar(pid['contribution'])}")
    log(f"  Faculty salary (year 1)      = {dollar(faculty_salary)}")
    log(f"  Graduate stipend             = {dollar(grad_salary)}")
    log(f"  Graduate tuition + fees      = {dollar(grad_fees)}")
    log(f"  Graduate health insurance    = {dollar(grad_ins)}")
    log(f"  Undergraduate salary         = {dollar(undergrad_salary)}")
    log(f"  Postdoc salary               = {dollar(postdoc_salary)}")
    log(f"  Postdoc health               = {dollar(postdoc_health)}")
    log(f"  Equipment                    = {dollar(equipment)}")
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
        subaward, indirect_rate, fringe_rate, fulltime_fringe, inflation,
        equipment)

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
        ("Fringe + Health Insurance",     "fringe_health"),
        ("Graduate Tuition",              "grad_fees"),
        ("Equipment",                     "equipment"),
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

    # ── NASA R&R Budget Format ─────────────────────────────────────

    log()
    log("=" * len(header))
    log("NASA R&R Budget Format")
    log("=" * len(header))

    nasa_items = []
    for y in range(number_years):
        d = details[y]
        senior_key = d["faculty_salary"] + d["faculty_fringe"]
        other_personnel = (d["grad_salary"] + d["grad_fringe"]
                           + d["postdoc_salary"] + d["postdoc_fringe"]
                           + d["postdoc_health"]
                           + d["undergrad_salary"] + d["undergrad_fringe"])
        total_salary = senior_key + other_personnel
        equip = d["equipment"]
        trav = d["travel"]
        participant = 0.0
        other_direct = d["pub_costs"] + d["subaward"] + d["grad_fees"] + d["grad_ins"]
        direct = total_salary + equip + trav + participant + other_direct
        ind = d["indirect"]
        total_di = direct + ind
        fee = 0.0
        budget_total = total_di + fee
        nasa_items.append({
            "senior_key": senior_key,
            "other_personnel": other_personnel,
            "total_salary": total_salary,
            "equipment": equip,
            "travel": trav,
            "participant": participant,
            "other_direct": other_direct,
            "direct": direct,
            "indirect": ind,
            "total_di": total_di,
            "fee": fee,
            "budget_total": budget_total,
        })

    nasa_lines = [
        ("A. Senior/Key Person",                "senior_key"),
        ("B. Other Personnel",                  "other_personnel"),
        ("Total Salary and Wages (A+B)",        "total_salary"),
        ("C. Equipment Description",            "equipment"),
        ("D. Travel",                           "travel"),
        ("E. Participant/Trainee Support Costs", "participant"),
        ("F. Other Direct Costs",               "other_direct"),
        ("G. Direct Costs (A through F)",       "direct"),
        ("H. Indirect Costs",                   "indirect"),
        ("I. Total Direct and Indirect (G + H)", "total_di"),
        ("J. Fee",                              "fee"),
        ("K. Budget Total (I + J)",             "budget_total"),
    ]

    nasa_label_w = 40
    nasa_header = (f"{'':>{nasa_label_w}}"
                   + "".join(f"{'Year ' + str(y+1):>{col_w}}" for y in range(number_years))
                   + f"{'Total':>{col_w}}")
    nasa_sep = "-" * len(nasa_header)

    def nasa_row(label, key):
        vals = [n[key] for n in nasa_items]
        cols = "".join(f"{dollar(v):>{col_w}}" for v in vals)
        return f"{label:>{nasa_label_w}}{cols}{dollar(sum(vals)):>{col_w}}"

    log()
    log(nasa_header)
    log(nasa_sep)
    for label, key in nasa_lines:
        log(nasa_row(label, key))
    log(nasa_sep)

    logfile.write("\n")
    logfile.close()
    print(f"Results saved to {LOG_FILE}")


if __name__ == "__main__":
    main()

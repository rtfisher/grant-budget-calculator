#!/usr/bin/env python3
# Curses-based TUI for the NSF grant budget calculator.
# Robert Fisher + Claude Opus, 4/2026
"""Provides a Pine/Alpine-style menu interface for editing budget parameters
and computing year-by-year budgets.  Imports the calculation engine from
budget_partial_years.py.
"""

import os
import sys
import curses
from datetime import datetime, date

from budget_partial_years import (
    load_parameters, dollar, calculate_budget, compute_period_fractions,
    GRAD_SUMMER_FRACTION, SUBAWARD_INDIRECT_CAP,
)

PAR_FILE = "budget.par"
LOG_FILE = "budget.log"

MIN_WIDTH = 80
MIN_HEIGHT = 24


# ── Data model ──────────────────────────────────────────────────────


class PIInfo:
    def __init__(self, base_salary=100000, summer_months=0.25):
        self.base_salary = base_salary
        self.summer_months = summer_months


class BudgetState:
    def __init__(self):
        self.use_dates = False
        self.start_date = None
        self.end_date = None
        self.number_years = 3
        self.pis = [PIInfo(base_salary=0, summer_months=0)]
        self.number_grads = 1
        self.grad_stipend_per = 0
        self.grad_fees_per = 0.0
        self.grad_ins_per = 0.0
        self.undergrad_salary = 0
        self.postdoc_salary = 0
        self.postdoc_health = 0
        self.travel = 0
        self.pub_costs = 0
        self.equipment = 0
        self.subaward = [0, 0, 0]
        self.indirect_rate = 0.59
        self.fringe_rate = 0.0221
        self.fulltime_fringe = 0.3781
        self.inflation = 0.03
        self._estimated_total = None
        self._dirty = False

    @classmethod
    def from_par_file(cls, path):
        params = load_parameters(path)
        state = cls()
        state.pis = [PIInfo(
            base_salary=int(params.get("faculty_base_salary", "100000")),
            summer_months=float(params.get("faculty_months", "0.25")),
        )]
        state.grad_stipend_per = int(params.get("grad_stipend", "26000"))
        state.grad_fees_per = float(params.get("grad_fees", "14500"))
        state.grad_ins_per = float(params.get("grad_insurance", "1232"))
        state.undergrad_salary = int(params.get("undergrad_salary", "0"))
        state.postdoc_salary = int(params.get("postdoc_salary", "0"))
        state.postdoc_health = int(params.get("postdoc_health", "0"))
        state.travel = int(params.get("travel", "2500"))
        state.pub_costs = int(params.get("pub_costs", "0"))
        state.equipment = int(params.get("equipment", "0"))
        state.indirect_rate = float(params.get("indirect_rate", "0.59"))
        state.fringe_rate = float(params.get("fringe_rate", "0.0221"))
        state.fulltime_fringe = float(params.get("fulltime_fringe", "0.3781"))
        state.inflation = float(params.get("inflation", "0.03"))
        return state

    def to_calc_args(self):
        faculty_salary = sum(pi.base_salary / 9.0 * pi.summer_months for pi in self.pis)
        period_fractions = None
        if self.use_dates and self.start_date and self.end_date:
            period_fractions = compute_period_fractions(self.start_date, self.end_date)
        return dict(
            number_years=self.number_years,
            faculty_salary=faculty_salary,
            grad_salary=self.number_grads * self.grad_stipend_per,
            grad_fees=self.number_grads * self.grad_fees_per,
            grad_ins=self.number_grads * self.grad_ins_per,
            undergrad_salary=self.undergrad_salary,
            postdoc_salary=self.postdoc_salary,
            postdoc_health=self.postdoc_health,
            travel=self.travel,
            pub_costs=self.pub_costs,
            subaward=list(self.subaward),
            indirect_rate=self.indirect_rate,
            fringe_rate=self.fringe_rate,
            fulltime_fringe=self.fulltime_fringe,
            inflation=self.inflation,
            equipment=self.equipment,
            period_fractions=period_fractions,
        )

    def recompute_estimate(self):
        try:
            args = self.to_calc_args()
            if args["number_years"] < 1:
                self._estimated_total = 0.0
                return 0.0
            results = calculate_budget(**args)
            self._estimated_total = sum(results["yearly"])
            return self._estimated_total
        except Exception:
            self._estimated_total = None
            return 0.0

    def finalize(self):
        return calculate_budget(**self.to_calc_args())

    def resize_subaward(self):
        current = len(self.subaward)
        if self.number_years > current:
            self.subaward.extend([0] * (self.number_years - current))
        elif self.number_years < current:
            self.subaward = self.subaward[:self.number_years]

    def validate_field(self, category, field_name, value):
        """Validate a raw string. Returns (ok, parsed_value, error_msg)."""
        if field_name in ("start_date", "end_date"):
            try:
                d = datetime.strptime(value, "%Y-%m-%d").date()
                return True, d, ""
            except ValueError:
                return False, None, "Invalid date (use YYYY-MM-DD)"
        if field_name in ("indirect_rate", "fringe_rate", "fulltime_fringe", "inflation",
                          "summer_months", "grad_fees_per", "grad_ins_per"):
            try:
                v = float(value)
                if v < 0:
                    return False, None, "Must be >= 0"
                warn = ""
                if field_name in ("indirect_rate", "fringe_rate", "fulltime_fringe", "inflation") and v > 1.0:
                    warn = f"Warning: {v} > 1.0 — did you mean {v/100:.4f}?"
                return True, v, warn
            except ValueError:
                return False, None, "Must be a number"
        try:
            v = int(value)
            if v < 0:
                return False, None, "Must be >= 0"
            return True, v, ""
        except ValueError:
            return False, None, "Must be an integer"


# ── Summary functions ───────────────────────────────────────────────


def summary_dates(state):
    if state.use_dates and state.start_date and state.end_date:
        return f"{state.start_date} to {state.end_date} ({state.number_years} periods)"
    return f"{state.number_years} years (full calendar)"


def summary_pis(state):
    n = len(state.pis)
    if n == 0:
        return "No PIs"
    total = sum(pi.base_salary / 9.0 * pi.summer_months for pi in state.pis)
    return f"{n} PI{'s' if n > 1 else ''}, {dollar(total)}/yr"


def summary_grads(state):
    if state.number_grads == 0:
        return "None"
    return f"{state.number_grads} student{'s' if state.number_grads > 1 else ''}, {dollar(state.grad_stipend_per)} stipend"


def summary_undergrad(state):
    return dollar(state.undergrad_salary)


def summary_postdocs(state):
    return f"{dollar(state.postdoc_salary)} salary, {dollar(state.postdoc_health)} health"


def summary_travel(state):
    return f"{dollar(state.travel)} travel, {dollar(state.pub_costs)} pub"


def summary_equipment(state):
    return dollar(state.equipment)


def summary_subawards(state):
    if all(s == 0 for s in state.subaward):
        return "$0 per period"
    return ", ".join(dollar(s) for s in state.subaward)


def summary_rates(state):
    return f"IDC {state.indirect_rate}, fringe {state.fringe_rate}, infl {state.inflation}"


MENU_ITEMS = [
    ("Project Dates", summary_dates),
    ("Senior Investigators", summary_pis),
    ("Graduate Students", summary_grads),
    ("Undergraduate Students", summary_undergrad),
    ("Postdocs", summary_postdocs),
    ("Travel & Publication", summary_travel),
    ("Equipment", summary_equipment),
    ("Subawards", summary_subawards),
    ("Rates & Inflation", summary_rates),
]


# ── Field editor ────────────────────────────────────────────────────


class FieldEditor:
    """Single editable text field for curses."""

    def __init__(self, value="", max_width=16):
        self.value = str(value)
        self.cursor = len(self.value)
        self.max_width = max_width

    def handle_key(self, key):
        """Process a key. Returns the confirmed string on Enter, else None."""
        if key in (curses.KEY_ENTER, 10, 13):
            return self.value
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            if self.cursor > 0:
                self.value = self.value[:self.cursor - 1] + self.value[self.cursor:]
                self.cursor -= 1
        elif key == curses.KEY_DC:
            if self.cursor < len(self.value):
                self.value = self.value[:self.cursor] + self.value[self.cursor + 1:]
        elif key == curses.KEY_LEFT:
            self.cursor = max(0, self.cursor - 1)
        elif key == curses.KEY_RIGHT:
            self.cursor = min(len(self.value), self.cursor + 1)
        elif key == curses.KEY_HOME:
            self.cursor = 0
        elif key == curses.KEY_END:
            self.cursor = len(self.value)
        elif 32 <= key <= 126 and len(self.value) < self.max_width:
            ch = chr(key)
            self.value = self.value[:self.cursor] + ch + self.value[self.cursor:]
            self.cursor += 1
        return None

    def render(self, win, y, x, width, active=False):
        """Draw the field at (y, x)."""
        display = self.value.ljust(width)[:width]
        try:
            if active:
                win.addstr(y, x, "[", curses.A_BOLD)
                win.addstr(y, x + 1, display, curses.A_REVERSE)
                win.addstr(y, x + 1 + width, "]", curses.A_BOLD)
                # Position cursor
                win.move(y, x + 1 + self.cursor)
            else:
                win.addstr(y, x, "[")
                win.addstr(y, x + 1, display)
                win.addstr(y, x + 1 + width, "]")
        except curses.error:
            pass


# ── Format results (matches budget_partial_years.py output) ─────────


def format_results(results, state):
    """Format budget results as a list of strings for display and logging."""
    lines = []
    lines.append("Basic Grant Budget Calculator (TUI)")
    lines.append(f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Input parameters
    lines.append("Input Parameters")
    lines.append("---------------------------------")

    if state.use_dates and state.start_date and state.end_date:
        lines.append(f"  Project start              = {state.start_date}")
        lines.append(f"  Project end                = {state.end_date}")
        pf = compute_period_fractions(state.start_date, state.end_date)
        for i, p in enumerate(pf):
            lines.append(f"  Period {i+1}                   = {p['start']} to {p['end']} "
                         f"({p['duration_days']} days, {p['summer_months']} summer)")

    lines.append(f"  Number of years              = {state.number_years}")
    lines.append(f"  Number of faculty            = {len(state.pis)}")
    for i, pi in enumerate(state.pis):
        contrib = pi.base_salary / 9.0 * pi.summer_months
        lines.append(f"    PI {i+1}: base 9-month salary = {dollar(pi.base_salary)}, "
                     f"summer months = {pi.summer_months}, contribution = {dollar(contrib)}")

    faculty_salary = sum(pi.base_salary / 9.0 * pi.summer_months for pi in state.pis)
    lines.append(f"  Faculty salary (year 1)      = {dollar(faculty_salary)}")
    lines.append(f"  Graduate stipend             = {dollar(state.number_grads * state.grad_stipend_per)}")
    lines.append(f"  Graduate tuition + fees      = {dollar(state.number_grads * state.grad_fees_per)}")
    lines.append(f"  Graduate health insurance    = {dollar(state.number_grads * state.grad_ins_per)}")
    lines.append(f"  Undergraduate salary         = {dollar(state.undergrad_salary)}")
    lines.append(f"  Postdoc salary               = {dollar(state.postdoc_salary)}")
    lines.append(f"  Postdoc health               = {dollar(state.postdoc_health)}")
    lines.append(f"  Equipment                    = {dollar(state.equipment)}")
    lines.append(f"  Travel                       = {dollar(state.travel)}")
    lines.append(f"  Publication costs            = {dollar(state.pub_costs)}")
    lines.append(f"  Subawards                    = {state.subaward}")
    lines.append(f"  Indirect rate                = {state.indirect_rate}")
    lines.append(f"  Fringe (payroll tax) rate    = {state.fringe_rate}")
    lines.append(f"  Full-time fringe rate        = {state.fulltime_fringe}")
    lines.append(f"  Inflation rate               = {state.inflation}")
    lines.append("")

    # Budget table
    details = results["details"]
    tdc = results["tdc"]
    indirect = results["indirect"]
    yearly = results["yearly"]
    number_years = state.number_years

    line_items = [
        ("Faculty Salary", "faculty_salary"),
        ("Faculty Fringe", "faculty_fringe"),
        ("Graduate Salary", "grad_salary"),
        ("Grad Fringe + Health Ins", "grad_fringe_health"),
        ("Postdoc Salary", "postdoc_salary"),
        ("Postdoc Fringe", "postdoc_fringe"),
        ("Total Postdoc", "total_postdoc"),
        ("Undergraduate Salary", "undergrad_salary"),
        ("Undergraduate Fringe", "undergrad_fringe"),
        ("Total Fringe", "total_fringe"),
        ("Graduate Tuition", "grad_fees"),
        ("Equipment", "equipment"),
        ("Travel", "travel"),
        ("Publication Costs", "pub_costs"),
        ("Subaward", "subaward"),
    ]

    label_w = 32
    col_w = 16

    def table_row(label, values, total):
        cols = "".join(f"{dollar(v):>{col_w}}" for v in values)
        return f"{label:>{label_w}}{cols}{dollar(total):>{col_w}}"

    col_headers = [f"Year {y+1}" for y in range(number_years)]
    header = (f"{'':>{label_w}}"
              + "".join(f"{h:>{col_w}}" for h in col_headers)
              + f"{'Total':>{col_w}}")
    sep = "-" * len(header)

    lines.append(header)
    lines.append(sep)

    for label, key in line_items:
        vals = [d[key] for d in details]
        lines.append(table_row(label, vals, sum(vals)))

    lines.append(sep)
    mtdc_vals = [d["mtdc"] for d in details]
    lines.append(table_row("Modified Total Direct Costs", mtdc_vals, sum(mtdc_vals)))
    ind_vals = list(indirect)
    lines.append(table_row("Indirect", ind_vals, sum(ind_vals)))
    lines.append(sep)
    lines.append(table_row("Total Direct", tdc, sum(tdc)))
    lines.append(table_row("Total Budget", yearly, sum(yearly)))

    # NASA R&R format
    lines.append("")
    lines.append("=" * len(header))
    lines.append("NASA R&R Budget Format")
    lines.append("=" * len(header))

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
        nasa_items.append({
            "senior_key": senior_key, "other_personnel": other_personnel,
            "total_salary": total_salary, "equipment": equip, "travel": trav,
            "participant": participant, "other_direct": other_direct,
            "direct": direct, "indirect": ind, "total_di": total_di,
            "fee": 0.0, "budget_total": total_di,
        })

    nasa_lines_def = [
        ("A. Senior/Key Person", "senior_key"),
        ("B. Other Personnel", "other_personnel"),
        ("Total Salary and Wages (A+B)", "total_salary"),
        ("C. Equipment Description", "equipment"),
        ("D. Travel", "travel"),
        ("E. Participant/Trainee Support Costs", "participant"),
        ("F. Other Direct Costs", "other_direct"),
        ("G. Direct Costs (A through F)", "direct"),
        ("H. Indirect Costs", "indirect"),
        ("I. Total Direct and Indirect (G + H)", "total_di"),
        ("J. Fee", "fee"),
        ("K. Budget Total (I + J)", "budget_total"),
    ]

    nasa_label_w = 40
    nasa_header = (f"{'':>{nasa_label_w}}"
                   + "".join(f"{h:>{col_w}}" for h in col_headers)
                   + f"{'Total':>{col_w}}")
    nasa_sep = "-" * len(nasa_header)

    lines.append("")
    lines.append(nasa_header)
    lines.append(nasa_sep)
    for label, key in nasa_lines_def:
        vals = [n[key] for n in nasa_items]
        cols = "".join(f"{dollar(v):>{col_w}}" for v in vals)
        lines.append(f"{label:>{nasa_label_w}}{cols}{dollar(sum(vals)):>{col_w}}")
    lines.append(nasa_sep)

    return lines


def write_log(lines, path=LOG_FILE):
    with open(path, "a") as f:
        f.write("=" * 60 + "\n")
        for line in lines:
            f.write(line + "\n")
        f.write("\n")


# ── Curses helpers ──────────────────────────────────────────────────


def safe_addstr(win, y, x, text, attr=0):
    """addstr that silently ignores edge-of-screen errors."""
    try:
        win.addstr(y, x, text, attr)
    except curses.error:
        pass


def safe_addnstr(win, y, x, text, n, attr=0):
    try:
        win.addnstr(y, x, text, n, attr)
    except curses.error:
        pass


def is_escape(stdscr, key):
    """Detect plain Escape vs Alt+key sequence."""
    if key != 27:
        return False
    stdscr.nodelay(True)
    next_key = stdscr.getch()
    stdscr.nodelay(False)
    return next_key == -1


def draw_title_bar(stdscr, title, width, color_pair=0):
    bar = f" {title} ".ljust(width)
    safe_addnstr(stdscr, 0, 0, bar, width, curses.A_REVERSE | color_pair)


def draw_status_bar(stdscr, text, height, width):
    safe_addstr(stdscr, height - 2, 0, "─" * width)
    safe_addnstr(stdscr, height - 1, 0, f" {text}".ljust(width), width, curses.A_DIM)


# ── Main menu screen ────────────────────────────────────────────────


def render_main_menu(stdscr, state, selected):
    height, width = stdscr.getmaxyx()
    stdscr.clear()

    draw_title_bar(stdscr, "Grant Budget Calculator — Robert Fisher + Claude Opus", width)

    # Menu items
    label_col = 4
    value_col = 30
    row = 2

    # Project dates (always first, above separator)
    label, summary_fn = MENU_ITEMS[0]
    prefix = "> " if selected == 0 else "  "
    attr = curses.A_REVERSE if selected == 0 else 0
    safe_addnstr(stdscr, row, label_col - 2, prefix + label, value_col - label_col + 2, attr)
    safe_addnstr(stdscr, row, value_col, summary_fn(state), width - value_col - 2, attr)
    row += 1

    # Separator
    safe_addstr(stdscr, row, label_col - 2, "─" * (width - 4))
    row += 1

    # Categories 1-8
    for i in range(1, len(MENU_ITEMS)):
        label, summary_fn = MENU_ITEMS[i]
        prefix = "> " if selected == i else "  "
        attr = curses.A_REVERSE if selected == i else 0
        safe_addnstr(stdscr, row, label_col - 2, prefix + label, value_col - label_col + 2, attr)
        safe_addnstr(stdscr, row, value_col, summary_fn(state), width - value_col - 2, attr)
        row += 1

    # Separator
    safe_addstr(stdscr, row, label_col - 2, "─" * (width - 4))
    row += 1

    # Finalize button
    finalize_idx = len(MENU_ITEMS)
    attr = curses.A_REVERSE if selected == finalize_idx else curses.A_BOLD
    safe_addstr(stdscr, row, label_col - 2, "> " if selected == finalize_idx else "  ")
    safe_addstr(stdscr, row, label_col, "[ Finalize Budget ]", attr)
    row += 2

    # Estimated total
    if state._estimated_total is not None:
        safe_addstr(stdscr, row, label_col - 2, f"Est. Total: {dollar(state._estimated_total)}", curses.A_BOLD)
    else:
        safe_addstr(stdscr, row, label_col - 2, "Est. Total: ---")

    # Status bar
    draw_status_bar(stdscr, "↑↓ Navigate   Enter: Edit   F: Finalize   Q: Quit", height, width)

    stdscr.refresh()


# ── Sub-screen: generic field editor ────────────────────────────────


def edit_fields(stdscr, title, field_defs, state):
    """Edit a list of fields. field_defs = [(label, field_name, current_value), ...]
    Returns dict of {field_name: new_value} or None if cancelled."""
    height, width = stdscr.getmaxyx()
    editors = []
    for label, fname, val in field_defs:
        editors.append(FieldEditor(str(val), max_width=16))

    active = 0
    error_msg = ""

    while True:
        stdscr.clear()
        draw_title_bar(stdscr, title, width)

        label_col = 4
        field_col = 30
        field_w = 16
        row = 2

        for i, (label, fname, _) in enumerate(field_defs):
            safe_addstr(stdscr, row, label_col, f"{label}:")
            editors[i].render(stdscr, row, field_col, field_w, active=(i == active))
            row += 1

        if error_msg:
            safe_addstr(stdscr, row + 1, label_col, error_msg, curses.A_BOLD)

        draw_status_bar(stdscr, "↑↓ Fields   Enter: Confirm   Esc: Done", height, width)

        curses.curs_set(1)
        stdscr.refresh()

        key = stdscr.getch()

        if is_escape(stdscr, key):
            curses.curs_set(0)
            # Return current values
            result = {}
            for i, (_, fname, _) in enumerate(field_defs):
                result[fname] = editors[i].value
            return result

        if key == curses.KEY_UP:
            error_msg = ""
            active = (active - 1) % len(editors)
        elif key == curses.KEY_DOWN:
            error_msg = ""
            active = (active + 1) % len(editors)
        else:
            confirmed = editors[active].handle_key(key)
            if confirmed is not None:
                # Validate
                _, fname, _ = field_defs[active]
                cat = title.lower().replace(" ", "_").replace("&", "")
                ok, parsed, err = state.validate_field(cat, fname, confirmed)
                if not ok:
                    error_msg = err
                else:
                    error_msg = err  # may be a warning
                    if active < len(editors) - 1:
                        active += 1
                    else:
                        curses.curs_set(0)
                        result = {}
                        for i, (_, fn, _) in enumerate(field_defs):
                            result[fn] = editors[i].value
                        return result


# ── Category-specific editors ───────────────────────────────────────


def edit_project_dates(stdscr, state):
    """Special editor for project dates with mode toggle."""
    height, width = stdscr.getmaxyx()

    mode = "dates" if state.use_dates else "years"
    start_ed = FieldEditor(str(state.start_date or ""), max_width=16)
    end_ed = FieldEditor(str(state.end_date or ""), max_width=16)
    years_ed = FieldEditor(str(state.number_years), max_width=6)

    active = 0  # 0=start, 1=end in date mode; 0=years in year mode
    error_msg = ""

    while True:
        stdscr.clear()
        draw_title_bar(stdscr, "Project Dates", width)

        row = 2
        label_col = 4
        field_col = 30
        field_w = 16

        # Mode indicator
        mode_str = f"Mode: {'[Dates]' if mode == 'dates' else ' Dates '} / {'[Years]' if mode == 'years' else ' Years '}"
        safe_addstr(stdscr, row, label_col, mode_str + "   (Tab to toggle)")
        row += 2

        if mode == "dates":
            safe_addstr(stdscr, row, label_col, "Start date (YYYY-MM-DD):")
            start_ed.render(stdscr, row, field_col, field_w, active=(active == 0))
            row += 1
            safe_addstr(stdscr, row, label_col, "End date (YYYY-MM-DD):")
            end_ed.render(stdscr, row, field_col, field_w, active=(active == 1))
            row += 2

            # Show computed periods
            if state.use_dates and state.start_date and state.end_date:
                try:
                    pf = compute_period_fractions(state.start_date, state.end_date)
                    safe_addstr(stdscr, row, label_col, f"Periods: {len(pf)}")
                    row += 1
                    for i, p in enumerate(pf):
                        safe_addnstr(stdscr, row, label_col + 2,
                                     f"Period {i+1}: {p['start']} to {p['end']} "
                                     f"({p['duration_days']} days, {p['summer_months']} summer)",
                                     width - label_col - 4)
                        row += 1
                except ValueError:
                    pass
        else:
            safe_addstr(stdscr, row, label_col, "Number of years:")
            years_ed.render(stdscr, row, field_col, 6, active=(active == 0))

        if error_msg:
            safe_addstr(stdscr, height - 4, label_col, error_msg, curses.A_BOLD)

        draw_status_bar(stdscr, "↑↓ Fields   Enter: Confirm   Tab: Toggle mode   Esc: Done", height, width)
        curses.curs_set(1)
        stdscr.refresh()

        key = stdscr.getch()

        if is_escape(stdscr, key):
            curses.curs_set(0)
            return

        if key == 9:  # Tab
            mode = "years" if mode == "dates" else "dates"
            active = 0
            error_msg = ""
            continue

        if key == curses.KEY_UP:
            if mode == "dates":
                active = (active - 1) % 2
            error_msg = ""
        elif key == curses.KEY_DOWN:
            if mode == "dates":
                active = (active + 1) % 2
            error_msg = ""
        else:
            if mode == "dates":
                ed = start_ed if active == 0 else end_ed
                fname = "start_date" if active == 0 else "end_date"
            else:
                ed = years_ed
                fname = "number_years"

            confirmed = ed.handle_key(key)
            if confirmed is not None:
                ok, parsed, err = state.validate_field("project_dates", fname, confirmed)
                if not ok:
                    error_msg = err
                else:
                    error_msg = ""
                    if mode == "dates":
                        if fname == "start_date":
                            state.start_date = parsed
                            active = 1
                        else:
                            state.end_date = parsed
                            # Compute periods
                            if state.start_date and state.end_date and state.end_date > state.start_date:
                                state.use_dates = True
                                pf = compute_period_fractions(state.start_date, state.end_date)
                                state.number_years = len(pf)
                                state.resize_subaward()
                    else:
                        state.use_dates = False
                        state.start_date = None
                        state.end_date = None
                        state.number_years = parsed
                        state.resize_subaward()


def edit_senior_investigators(stdscr, state):
    """Editor for PIs with +/- support."""
    height, width = stdscr.getmaxyx()
    error_msg = ""

    # Build field list from current PIs
    def build_editors():
        eds = []
        for i, pi in enumerate(state.pis):
            eds.append((f"PI {i+1} base 9-month salary", "base_salary", FieldEditor(str(pi.base_salary), 12)))
            eds.append((f"PI {i+1} summer months", "summer_months", FieldEditor(str(pi.summer_months), 6)))
        return eds

    editors = build_editors()
    active = 0

    while True:
        stdscr.clear()
        draw_title_bar(stdscr, f"Senior Investigators ({len(state.pis)} PIs)", width)

        row = 2
        label_col = 4
        field_col = 34
        field_w = 12

        for i, (label, fname, ed) in enumerate(editors):
            safe_addstr(stdscr, row, label_col, f"{label}:")
            ed.render(stdscr, row, field_col, field_w, active=(i == active))
            row += 1
            if i % 2 == 1 and i < len(editors) - 1:
                row += 1  # blank line between PIs

        row += 1
        safe_addstr(stdscr, row, label_col, "(Press + to add PI, - to remove last PI)")

        if error_msg:
            safe_addstr(stdscr, row + 2, label_col, error_msg, curses.A_BOLD)

        draw_status_bar(stdscr, "↑↓ Fields   Enter: Confirm   +/-: Add/Remove PI   Esc: Done", height, width)
        curses.curs_set(1)
        stdscr.refresh()

        key = stdscr.getch()

        if is_escape(stdscr, key):
            curses.curs_set(0)
            # Apply values back to state
            for i, pi in enumerate(state.pis):
                base_ed = editors[i * 2][2]
                months_ed = editors[i * 2 + 1][2]
                try:
                    pi.base_salary = int(base_ed.value)
                except ValueError:
                    pass
                try:
                    pi.summer_months = float(months_ed.value)
                except ValueError:
                    pass
            return

        if key == ord('+'):
            state.pis.append(PIInfo())
            editors = build_editors()
            active = len(editors) - 2  # focus new PI's base salary
            error_msg = ""
        elif key == ord('-'):
            if len(state.pis) > 0:
                state.pis.pop()
                editors = build_editors()
                active = min(active, max(0, len(editors) - 1))
            error_msg = ""
        elif key == curses.KEY_UP:
            if editors:
                active = (active - 1) % len(editors)
            error_msg = ""
        elif key == curses.KEY_DOWN:
            if editors:
                active = (active + 1) % len(editors)
            error_msg = ""
        elif editors:
            _, fname, ed = editors[active]
            confirmed = ed.handle_key(key)
            if confirmed is not None:
                ok, parsed, err = state.validate_field("senior_investigators", fname, confirmed)
                if not ok:
                    error_msg = err
                else:
                    error_msg = err
                    if active < len(editors) - 1:
                        active += 1


def edit_subawards(stdscr, state):
    """Editor for per-period subaward values."""
    height, width = stdscr.getmaxyx()
    editors = [FieldEditor(str(s), max_width=12) for s in state.subaward]
    active = 0
    error_msg = ""

    while True:
        stdscr.clear()
        draw_title_bar(stdscr, "Subawards", width)

        row = 2
        label_col = 4
        field_col = 30
        field_w = 12

        for i, ed in enumerate(editors):
            safe_addstr(stdscr, row, label_col, f"Period {i+1} subaward:")
            ed.render(stdscr, row, field_col, field_w, active=(i == active))
            row += 1

        row += 1
        total = 0
        for ed in editors:
            try:
                total += int(ed.value)
            except ValueError:
                pass
        safe_addstr(stdscr, row, label_col, f"Total subawards: {dollar(total)}")

        if error_msg:
            safe_addstr(stdscr, row + 2, label_col, error_msg, curses.A_BOLD)

        draw_status_bar(stdscr, "↑↓ Fields   Enter: Confirm   Esc: Done", height, width)
        curses.curs_set(1)
        stdscr.refresh()

        key = stdscr.getch()

        if is_escape(stdscr, key):
            curses.curs_set(0)
            for i, ed in enumerate(editors):
                try:
                    state.subaward[i] = int(ed.value)
                except ValueError:
                    pass
            return

        if key == curses.KEY_UP and editors:
            active = (active - 1) % len(editors)
            error_msg = ""
        elif key == curses.KEY_DOWN and editors:
            active = (active + 1) % len(editors)
            error_msg = ""
        elif editors:
            confirmed = editors[active].handle_key(key)
            if confirmed is not None:
                ok, parsed, err = state.validate_field("subawards", "subaward", confirmed)
                if not ok:
                    error_msg = err
                else:
                    error_msg = ""
                    if active < len(editors) - 1:
                        active += 1


# ── Results screen ──────────────────────────────────────────────────


def show_results(stdscr, lines, state):
    """Scrollable results display. Returns True if saved."""
    height, width = stdscr.getmaxyx()
    scroll = 0
    visible = height - 3  # title + status bar
    saved = False

    while True:
        stdscr.clear()
        draw_title_bar(stdscr, "Budget Results", width)

        for i in range(visible):
            line_idx = scroll + i
            if line_idx < len(lines):
                safe_addnstr(stdscr, i + 1, 1, lines[line_idx], width - 2)

        status = "↑↓ Scroll   S: Save to log   Esc/Q: Return"
        if saved:
            status = f"Saved to {LOG_FILE}!   " + status
        draw_status_bar(stdscr, status, height, width)

        curses.curs_set(0)
        stdscr.refresh()

        key = stdscr.getch()

        if is_escape(stdscr, key) or key in (ord('q'), ord('Q')):
            return saved
        elif key == curses.KEY_UP:
            scroll = max(0, scroll - 1)
        elif key == curses.KEY_DOWN:
            scroll = min(max(0, len(lines) - visible), scroll + 1)
        elif key == curses.KEY_PPAGE:
            scroll = max(0, scroll - visible)
        elif key == curses.KEY_NPAGE:
            scroll = min(max(0, len(lines) - visible), scroll + visible)
        elif key in (ord('s'), ord('S')):
            write_log(lines)
            saved = True


# ── Confirmation dialog ─────────────────────────────────────────────


def confirm_quit(stdscr):
    """Show quit confirmation. Returns True if user confirms."""
    height, width = stdscr.getmaxyx()
    msg = "Unsaved changes. Quit? (Y/N)"
    y = height // 2
    x = max(0, (width - len(msg)) // 2)
    safe_addstr(stdscr, y, x, msg, curses.A_BOLD | curses.A_REVERSE)
    stdscr.refresh()

    while True:
        key = stdscr.getch()
        if key in (ord('y'), ord('Y')):
            return True
        if key in (ord('n'), ord('N'), 27):
            return False


# ── Dispatch editing to category ────────────────────────────────────


# Field definitions for simple categories
SIMPLE_CATEGORIES = {
    2: ("Graduate Students", [
        ("Number of graduate students", "number_grads"),
        ("Annual stipend (per student)", "grad_stipend_per"),
        ("Tuition + fees (per student)", "grad_fees_per"),
        ("Health insurance (per student)", "grad_ins_per"),
    ]),
    3: ("Undergraduate Students", [
        ("Undergraduate salary", "undergrad_salary"),
    ]),
    4: ("Postdocs", [
        ("Postdoc salary", "postdoc_salary"),
        ("Postdoc health insurance", "postdoc_health"),
    ]),
    5: ("Travel & Publication", [
        ("Yearly travel costs", "travel"),
        ("Yearly publication costs", "pub_costs"),
    ]),
    6: ("Equipment", [
        ("Yearly equipment costs", "equipment"),
    ]),
    8: ("Rates & Inflation", [
        ("Indirect (F&A) rate", "indirect_rate"),
        ("Fringe (payroll tax) rate", "fringe_rate"),
        ("Full-time fringe rate", "fulltime_fringe"),
        ("Inflation rate", "inflation"),
    ]),
}


def get_state_attr(state, fname):
    """Get a field value from state, handling nested PI attrs."""
    return getattr(state, fname)


def set_state_attr(state, fname, value):
    """Set a field value on state."""
    ok, parsed, _ = state.validate_field("", fname, str(value))
    if ok:
        setattr(state, fname, parsed)


def dispatch_edit(stdscr, state, idx):
    """Open the appropriate editor for menu item idx."""
    if idx == 0:
        edit_project_dates(stdscr, state)
    elif idx == 1:
        edit_senior_investigators(stdscr, state)
    elif idx == 7:
        edit_subawards(stdscr, state)
    elif idx in SIMPLE_CATEGORIES:
        title, fields = SIMPLE_CATEGORIES[idx]
        field_defs = [(label, fname, getattr(state, fname)) for label, fname in fields]
        result = edit_fields(stdscr, title, field_defs, state)
        if result:
            for fname, val_str in result.items():
                ok, parsed, _ = state.validate_field(title.lower(), fname, val_str)
                if ok:
                    setattr(state, fname, parsed)
            if idx == 2:  # grad count may have changed
                pass  # number_grads is already set via setattr


# ── Main entry point ────────────────────────────────────────────────


def main(stdscr):
    curses.curs_set(0)
    stdscr.keypad(True)

    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()

    height, width = stdscr.getmaxyx()
    if height < MIN_HEIGHT or width < MIN_WIDTH:
        stdscr.addstr(0, 0, f"Terminal too small ({width}x{height}). Need at least {MIN_WIDTH}x{MIN_HEIGHT}.")
        stdscr.getch()
        return

    state = BudgetState.from_par_file(PAR_FILE)
    state.recompute_estimate()

    total_items = len(MENU_ITEMS) + 1  # +1 for Finalize
    selected = 0

    while True:
        render_main_menu(stdscr, state, selected)
        key = stdscr.getch()

        if key == curses.KEY_UP:
            selected = (selected - 1) % total_items
        elif key == curses.KEY_DOWN:
            selected = (selected + 1) % total_items
        elif key in (curses.KEY_ENTER, 10, 13):
            if selected < len(MENU_ITEMS):
                dispatch_edit(stdscr, state, selected)
                state._dirty = True
                state.recompute_estimate()
            else:
                # Finalize
                try:
                    results = state.finalize()
                    lines = format_results(results, state)
                    saved = show_results(stdscr, lines, state)
                    if saved:
                        state._dirty = False
                except Exception as e:
                    stdscr.clear()
                    safe_addstr(stdscr, 1, 2, f"Error: {e}", curses.A_BOLD)
                    safe_addstr(stdscr, 3, 2, "Press any key to return.")
                    stdscr.getch()
        elif key in (ord('f'), ord('F')):
            try:
                results = state.finalize()
                lines = format_results(results, state)
                saved = show_results(stdscr, lines, state)
                if saved:
                    state._dirty = False
            except Exception as e:
                stdscr.clear()
                safe_addstr(stdscr, 1, 2, f"Error: {e}", curses.A_BOLD)
                safe_addstr(stdscr, 3, 2, "Press any key to return.")
                stdscr.getch()
        elif key in (ord('q'), ord('Q')):
            if state._dirty:
                if not confirm_quit(stdscr):
                    continue
            break
        elif key == curses.KEY_RESIZE:
            height, width = stdscr.getmaxyx()


if __name__ == "__main__":
    if not os.path.exists(PAR_FILE):
        print(f"Error: parameter file '{PAR_FILE}' not found.")
        print("Place budget.par in the current directory and re-run.")
        sys.exit(1)
    curses.wrapper(main)

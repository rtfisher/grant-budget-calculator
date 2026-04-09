"""Tests for the TUI budget calculator's non-curses components."""

import os
import sys
import pytest
from datetime import date

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PAR_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "budget.par")

from budget_tui import (
    BudgetState, PIInfo, MENU_ITEMS,
    summary_dates, summary_pis, summary_grads, summary_undergrad,
    summary_postdocs, summary_travel, summary_equipment,
    summary_subawards, summary_rates, summary_agency,
    generate_log_filename, parse_log_file, format_results,
    format_nsf_table, format_nasa_table, write_log,
)
from budget_partial_years import calculate_budget, dollar


# ── BudgetState initialization ──────────────────────────────────────


class TestBudgetStateInit:
    def test_from_par_file_defaults(self):
        state = BudgetState.from_par_file(PAR_FILE)
        assert state.number_years == 3
        assert len(state.pis) == 1
        assert state.pis[0].base_salary == 0
        assert state.pis[0].summer_months == 0.0
        assert state.grad_stipend_per == 0
        assert state.grad_fees_per == 14500.0
        assert state.grad_ins_per == 1232.0
        assert state.undergrad_salary == 0
        assert state.postdoc_salary == 0
        assert state.postdoc_health == 0
        assert state.travel == 0
        assert state.pub_costs == 0
        assert state.equipment == 0
        assert state.indirect_rate == 0.59
        assert state.fringe_rate == 0.0221
        assert state.fulltime_fringe == 0.3781
        assert state.inflation == 0.03
        assert state.subaward == [0, 0, 0]
        assert state.use_dates is False
        assert state._dirty is False

    def test_from_par_file_missing(self):
        with pytest.raises((FileNotFoundError, OSError)):
            BudgetState.from_par_file("/nonexistent/budget.par")

    def test_default_constructor(self):
        state = BudgetState()
        assert state.number_years == 3
        assert len(state.pis) == 1


# ── to_calc_args ────────────────────────────────────────────────────


class TestBudgetStateCalcArgs:
    def test_single_pi_faculty_salary(self):
        state = BudgetState.from_par_file(PAR_FILE)
        state.pis = [PIInfo(base_salary=100000, summer_months=0.25)]
        args = state.to_calc_args()
        expected = 100000 / 9.0 * 0.25
        assert args["faculty_salary"] == pytest.approx(expected)

    def test_multiple_pis(self):
        state = BudgetState.from_par_file(PAR_FILE)
        state.pis = [PIInfo(base_salary=100000, summer_months=0.25)]
        state.pis.append(PIInfo(base_salary=150000, summer_months=1.0))
        args = state.to_calc_args()
        expected = (100000 / 9.0 * 0.25) + (150000 / 9.0 * 1.0)
        assert args["faculty_salary"] == pytest.approx(expected)

    def test_zero_pis(self):
        state = BudgetState.from_par_file(PAR_FILE)
        state.pis = []
        args = state.to_calc_args()
        assert args["faculty_salary"] == 0.0

    def test_grad_totals_multiplied(self):
        state = BudgetState.from_par_file(PAR_FILE)
        state.number_grads = 2
        state.grad_stipend_per = 26000
        state.grad_fees_per = 14500.0
        state.grad_ins_per = 1232.0
        args = state.to_calc_args()
        assert args["grad_salary"] == 2 * 26000
        assert args["grad_fees"] == 2 * 14500.0
        assert args["grad_ins"] == 2 * 1232.0

    def test_date_mode_has_period_fractions(self):
        state = BudgetState.from_par_file(PAR_FILE)
        state.use_dates = True
        state.start_date = date(2026, 9, 15)
        state.end_date = date(2029, 6, 15)
        state.number_years = 3
        state.resize_subaward()
        args = state.to_calc_args()
        assert args["period_fractions"] is not None
        assert len(args["period_fractions"]) == 3

    def test_year_mode_no_period_fractions(self):
        state = BudgetState.from_par_file(PAR_FILE)
        args = state.to_calc_args()
        assert args["period_fractions"] is None

    def test_all_keys_present(self):
        state = BudgetState.from_par_file(PAR_FILE)
        args = state.to_calc_args()
        required = {"number_years", "faculty_salary", "grad_salary", "grad_fees",
                     "grad_ins", "undergrad_salary", "postdoc_salary", "postdoc_health",
                     "travel", "pub_costs", "subaward", "indirect_rate", "fringe_rate",
                     "fulltime_fringe", "inflation", "equipment", "period_fractions"}
        assert set(args.keys()) == required

    def test_subaward_is_copy(self):
        state = BudgetState.from_par_file(PAR_FILE)
        args = state.to_calc_args()
        args["subaward"][0] = 99999
        assert state.subaward[0] == 0


# ── resize_subaward ─────────────────────────────────────────────────


class TestResizeSubaward:
    def test_extend(self):
        state = BudgetState.from_par_file(PAR_FILE)
        state.number_years = 5
        state.resize_subaward()
        assert len(state.subaward) == 5
        assert state.subaward == [0, 0, 0, 0, 0]

    def test_truncate(self):
        state = BudgetState.from_par_file(PAR_FILE)
        state.subaward = [1000, 2000, 3000]
        state.number_years = 2
        state.resize_subaward()
        assert state.subaward == [1000, 2000]

    def test_preserves_existing(self):
        state = BudgetState.from_par_file(PAR_FILE)
        state.subaward = [1000, 2000, 3000]
        state.number_years = 5
        state.resize_subaward()
        assert state.subaward[:3] == [1000, 2000, 3000]
        assert state.subaward[3:] == [0, 0]

    def test_no_change_same_size(self):
        state = BudgetState.from_par_file(PAR_FILE)
        state.subaward = [100, 200, 300]
        state.number_years = 3
        state.resize_subaward()
        assert state.subaward == [100, 200, 300]


# ── recompute_estimate ──────────────────────────────────────────────


class TestRecomputeEstimate:
    def test_matches_calculate_budget(self):
        state = BudgetState.from_par_file(PAR_FILE)
        est = state.recompute_estimate()
        args = state.to_calc_args()
        results = calculate_budget(**args)
        assert est == pytest.approx(sum(results["yearly"]))

    def test_updates_after_change(self):
        state = BudgetState.from_par_file(PAR_FILE)
        est1 = state.recompute_estimate()
        state.travel = 10000
        est2 = state.recompute_estimate()
        assert est2 > est1

    def test_nonzero_with_par_defaults(self):
        """With budget.par defaults (grad fees/insurance set), estimate reflects those."""
        state = BudgetState.from_par_file(PAR_FILE)
        est = state.recompute_estimate()
        # grad_fees and grad_insurance are non-zero in budget.par
        assert est > 0

    def test_positive_with_values(self):
        state = BudgetState.from_par_file(PAR_FILE)
        state.pis = [PIInfo(base_salary=100000, summer_months=0.25)]
        state.travel = 2500
        est = state.recompute_estimate()
        assert est > 0

    def test_zero_years_returns_zero(self):
        state = BudgetState.from_par_file(PAR_FILE)
        state.number_years = 0
        state.subaward = []
        est = state.recompute_estimate()
        assert est == 0.0


# ── validate_field ──────────────────────────────────────────────────


class TestFieldValidation:
    def test_int_valid(self):
        state = BudgetState.from_par_file(PAR_FILE)
        ok, val, err = state.validate_field("equipment", "equipment", "15000")
        assert ok is True
        assert val == 15000
        assert err == ""

    def test_int_non_numeric(self):
        state = BudgetState.from_par_file(PAR_FILE)
        ok, val, err = state.validate_field("equipment", "equipment", "abc")
        assert ok is False

    def test_int_negative(self):
        state = BudgetState.from_par_file(PAR_FILE)
        ok, val, err = state.validate_field("equipment", "equipment", "-100")
        assert ok is False

    def test_int_zero(self):
        state = BudgetState.from_par_file(PAR_FILE)
        ok, val, err = state.validate_field("equipment", "equipment", "0")
        assert ok is True
        assert val == 0

    def test_float_valid(self):
        state = BudgetState.from_par_file(PAR_FILE)
        ok, val, err = state.validate_field("rates_inflation", "indirect_rate", "0.55")
        assert ok is True
        assert val == pytest.approx(0.55)

    def test_float_negative(self):
        state = BudgetState.from_par_file(PAR_FILE)
        ok, val, err = state.validate_field("rates_inflation", "indirect_rate", "-0.1")
        assert ok is False

    def test_float_zero(self):
        state = BudgetState.from_par_file(PAR_FILE)
        ok, val, err = state.validate_field("rates_inflation", "inflation", "0.0")
        assert ok is True
        assert val == 0.0

    def test_rate_warns_above_one(self):
        state = BudgetState.from_par_file(PAR_FILE)
        ok, val, err = state.validate_field("rates_inflation", "indirect_rate", "59")
        assert ok is True
        assert val == pytest.approx(59.0)
        assert len(err) > 0

    def test_date_valid(self):
        state = BudgetState.from_par_file(PAR_FILE)
        ok, val, err = state.validate_field("project_dates", "start_date", "2026-09-15")
        assert ok is True
        assert val == date(2026, 9, 15)

    def test_date_invalid_format(self):
        state = BudgetState.from_par_file(PAR_FILE)
        ok, val, err = state.validate_field("project_dates", "start_date", "09/15/2026")
        assert ok is False

    def test_date_invalid_date(self):
        state = BudgetState.from_par_file(PAR_FILE)
        ok, val, err = state.validate_field("project_dates", "start_date", "2026-13-01")
        assert ok is False


# ── Summary strings ─────────────────────────────────────────────────


class TestSummaryStrings:
    def test_dates_year_mode(self):
        state = BudgetState.from_par_file(PAR_FILE)
        s = summary_dates(state)
        assert "3 years" in s

    def test_dates_date_mode(self):
        state = BudgetState.from_par_file(PAR_FILE)
        state.use_dates = True
        state.start_date = date(2026, 9, 15)
        state.end_date = date(2029, 6, 15)
        state.number_years = 3
        s = summary_dates(state)
        assert "2026-09-15" in s
        assert "2029-06-15" in s

    def test_pis_single(self):
        state = BudgetState.from_par_file(PAR_FILE)
        s = summary_pis(state)
        assert "1 PI" in s
        assert "$" in s

    def test_pis_multiple(self):
        state = BudgetState.from_par_file(PAR_FILE)
        state.pis.append(PIInfo(150000, 1.0))
        s = summary_pis(state)
        assert "2 PIs" in s

    def test_pis_none(self):
        state = BudgetState.from_par_file(PAR_FILE)
        state.pis = []
        s = summary_pis(state)
        assert "No PI" in s

    def test_grads_single(self):
        state = BudgetState.from_par_file(PAR_FILE)
        state.grad_stipend_per = 26000
        s = summary_grads(state)
        assert "1 student" in s

    def test_grads_none(self):
        state = BudgetState.from_par_file(PAR_FILE)
        state.number_grads = 0
        s = summary_grads(state)
        assert "None" in s

    def test_undergrad(self):
        state = BudgetState.from_par_file(PAR_FILE)
        s = summary_undergrad(state)
        assert "$0" in s

    def test_postdocs(self):
        state = BudgetState.from_par_file(PAR_FILE)
        s = summary_postdocs(state)
        assert "salary" in s
        assert "health" in s

    def test_travel(self):
        state = BudgetState.from_par_file(PAR_FILE)
        s = summary_travel(state)
        assert "travel" in s
        assert "pub" in s

    def test_equipment(self):
        state = BudgetState.from_par_file(PAR_FILE)
        s = summary_equipment(state)
        assert "$0" in s

    def test_subawards_all_zero(self):
        state = BudgetState.from_par_file(PAR_FILE)
        s = summary_subawards(state)
        assert "$0" in s

    def test_subawards_nonzero(self):
        state = BudgetState.from_par_file(PAR_FILE)
        state.subaward = [10000, 5000, 0]
        s = summary_subawards(state)
        assert "$10,000" in s

    def test_rates(self):
        state = BudgetState.from_par_file(PAR_FILE)
        s = summary_rates(state)
        assert "0.59" in s
        assert "0.03" in s


# ── finalize ────────────────────────────────────────────────────────


class TestFinalize:
    def test_returns_valid_results(self):
        state = BudgetState.from_par_file(PAR_FILE)
        results = state.finalize()
        assert "tdc" in results
        assert "mtdc" in results
        assert "indirect" in results
        assert "yearly" in results
        assert "details" in results
        assert len(results["yearly"]) == 3

    def test_results_match_direct_call(self):
        state = BudgetState.from_par_file(PAR_FILE)
        results = state.finalize()
        args = state.to_calc_args()
        direct = calculate_budget(**args)
        for key in ["tdc", "mtdc", "indirect", "yearly"]:
            for i in range(3):
                assert results[key][i] == pytest.approx(direct[key][i])


# ── MENU_ITEMS ──────────────────────────────────────────────────────


class TestMenuItems:
    def test_ten_categories(self):
        assert len(MENU_ITEMS) == 10

    def test_all_have_label_and_function(self):
        for label, fn in MENU_ITEMS:
            assert isinstance(label, str)
            assert callable(fn)

    def test_all_summary_fns_work_with_default_state(self):
        state = BudgetState.from_par_file(PAR_FILE)
        for label, fn in MENU_ITEMS:
            result = fn(state)
            assert isinstance(result, str), f"{label} summary_fn did not return string"


# ── Agency & Program fields ─────────────────────────────────────────


class TestAgencyProgramFields:
    def test_default_empty(self):
        state = BudgetState()
        assert state.agency == ""
        assert state.program_call == ""

    def test_from_par_file_empty(self):
        state = BudgetState.from_par_file(PAR_FILE)
        assert state.agency == ""
        assert state.program_call == ""

    def test_validate_agency_any_string(self):
        state = BudgetState()
        ok, val, err = state.validate_field("agency", "agency", "NASA")
        assert ok is True
        assert val == "NASA"

    def test_validate_program_call_any_string(self):
        state = BudgetState()
        ok, val, err = state.validate_field("agency", "program_call", "COMPASS")
        assert ok is True
        assert val == "COMPASS"

    def test_validate_empty_string(self):
        state = BudgetState()
        ok, val, err = state.validate_field("agency", "agency", "")
        assert ok is True
        assert val == ""


# ── summary_agency ──────────────────────────────────────────────────


class TestSummaryAgency:
    def test_both_set(self):
        state = BudgetState()
        state.agency = "nasa"
        state.program_call = "compass"
        assert summary_agency(state) == "nasa / compass"

    def test_only_agency(self):
        state = BudgetState()
        state.agency = "nsf"
        assert summary_agency(state) == "nsf"

    def test_only_program(self):
        state = BudgetState()
        state.program_call = "aag"
        assert summary_agency(state) == "aag"

    def test_neither_set(self):
        state = BudgetState()
        assert summary_agency(state) == "(not set)"


# ── generate_log_filename ───────────────────────────────────────────


class TestGenerateLogFilename:
    def test_basic_filename(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        name = generate_log_filename("nasa", "compass")
        # Should match pattern: nasa_compass_MMDDYY.log
        assert name.startswith("nasa_compass_")
        assert name.endswith(".log")

    def test_empty_agency_and_call(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        name = generate_log_filename("", "")
        assert name.startswith("budget_")
        assert name.endswith(".log")

    def test_only_agency(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        name = generate_log_filename("nsf", "")
        assert name.startswith("nsf_")
        assert name.endswith(".log")

    def test_only_call(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        name = generate_log_filename("", "aag")
        assert name.startswith("aag_")
        assert name.endswith(".log")

    def test_versioning(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        name1 = generate_log_filename("nasa", "compass")
        # Create the first file
        (tmp_path / name1).write_text("test")
        name2 = generate_log_filename("nasa", "compass")
        assert "_v2" in name2
        # Create v2
        (tmp_path / name2).write_text("test")
        name3 = generate_log_filename("nasa", "compass")
        assert "_v3" in name3

    def test_sanitizes_special_chars(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        name = generate_log_filename("NASA", "My Program!")
        assert "nasa" in name
        assert "my_program" in name
        assert "!" not in name

    def test_sanitizes_spaces(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        name = generate_log_filename("my agency", "call name")
        assert " " not in name


# ── parse_log_file ──────────────────────────────────────────────────


class TestParseLogFile:
    SAMPLE_LOG = """============================================================
Basic Grant Budget Calculator (TUI)
Run: 2026-04-08 14:30:00
  Agency                       = nasa
  Program call                 = compass

Input Parameters
---------------------------------
  Project start              = 2026-09-01
  Project end                = 2029-06-01
  Period 1                   = 2026-09-01 to 2027-09-01 (365 days, 3 summer)
  Period 2                   = 2027-09-01 to 2028-09-01 (366 days, 3 summer)
  Period 3                   = 2028-09-01 to 2029-06-01 (273 days, 0 summer)
  Number of years              = 3
  Number of faculty            = 2
    PI 1: base 9-month salary = $100,000.00, summer months = 0.25, contribution = $2,777.78
    PI 2: base 9-month salary = $150,000.00, summer months = 1.0, contribution = $16,666.67
  Number of graduate students   = 2
  Grad stipend (per student)   = $26,000.00
  Grad fees (per student)      = $14,500.00
  Grad insurance (per student) = $1,232.00
  Faculty salary (year 1)      = $19,444.44
  Graduate stipend             = $52,000.00
  Graduate tuition + fees      = $29,000.00
  Graduate health insurance    = $2,464.00
  Undergraduate salary         = $5,000.00
  Postdoc salary               = $60,000.00
  Postdoc health               = $3,000.00
  Equipment                    = $15,000.00
  Travel                       = $2,500.00
  Publication costs            = $1,000.00
  Subawards                    = [10000, 5000, 0]
  Indirect rate                = 0.59
  Fringe (payroll tax) rate    = 0.0221
  Full-time fringe rate        = 0.3781
  Inflation rate               = 0.03

"""

    def test_parse_agency(self, tmp_path):
        log_file = tmp_path / "test.log"
        log_file.write_text(self.SAMPLE_LOG)
        state = parse_log_file(str(log_file))
        assert state.agency == "nasa"
        assert state.program_call == "compass"

    def test_parse_dates(self, tmp_path):
        log_file = tmp_path / "test.log"
        log_file.write_text(self.SAMPLE_LOG)
        state = parse_log_file(str(log_file))
        assert state.use_dates is True
        assert state.start_date == date(2026, 9, 1)
        assert state.end_date == date(2029, 6, 1)

    def test_parse_number_years(self, tmp_path):
        log_file = tmp_path / "test.log"
        log_file.write_text(self.SAMPLE_LOG)
        state = parse_log_file(str(log_file))
        assert state.number_years == 3

    def test_parse_pis(self, tmp_path):
        log_file = tmp_path / "test.log"
        log_file.write_text(self.SAMPLE_LOG)
        state = parse_log_file(str(log_file))
        assert len(state.pis) == 2
        assert state.pis[0].base_salary == 100000
        assert state.pis[0].summer_months == 0.25
        assert state.pis[1].base_salary == 150000
        assert state.pis[1].summer_months == 1.0

    def test_parse_grad_students(self, tmp_path):
        log_file = tmp_path / "test.log"
        log_file.write_text(self.SAMPLE_LOG)
        state = parse_log_file(str(log_file))
        assert state.number_grads == 2
        assert state.grad_stipend_per == 26000
        assert state.grad_fees_per == pytest.approx(14500.0)
        assert state.grad_ins_per == pytest.approx(1232.0)

    def test_parse_other_salaries(self, tmp_path):
        log_file = tmp_path / "test.log"
        log_file.write_text(self.SAMPLE_LOG)
        state = parse_log_file(str(log_file))
        assert state.undergrad_salary == 5000
        assert state.postdoc_salary == 60000
        assert state.postdoc_health == 3000

    def test_parse_costs(self, tmp_path):
        log_file = tmp_path / "test.log"
        log_file.write_text(self.SAMPLE_LOG)
        state = parse_log_file(str(log_file))
        assert state.equipment == 15000
        assert state.travel == 2500
        assert state.pub_costs == 1000

    def test_parse_subawards(self, tmp_path):
        log_file = tmp_path / "test.log"
        log_file.write_text(self.SAMPLE_LOG)
        state = parse_log_file(str(log_file))
        assert state.subaward == [10000, 5000, 0]

    def test_parse_rates(self, tmp_path):
        log_file = tmp_path / "test.log"
        log_file.write_text(self.SAMPLE_LOG)
        state = parse_log_file(str(log_file))
        assert state.indirect_rate == pytest.approx(0.59)
        assert state.fringe_rate == pytest.approx(0.0221)
        assert state.fulltime_fringe == pytest.approx(0.3781)
        assert state.inflation == pytest.approx(0.03)

    def test_roundtrip_format_then_parse(self):
        """format_results + parse_log_file should roundtrip all state."""
        import tempfile
        state = BudgetState.from_par_file(PAR_FILE)
        state.agency = "doe"
        state.program_call = "fusion"
        state.pis = [PIInfo(base_salary=120000, summer_months=0.5)]
        state.number_grads = 1
        state.grad_stipend_per = 30000
        state.grad_fees_per = 15000.0
        state.grad_ins_per = 1500.0
        state.undergrad_salary = 4000
        state.postdoc_salary = 55000
        state.postdoc_health = 2800
        state.travel = 3000
        state.pub_costs = 500
        state.equipment = 10000
        state.subaward = [5000, 10000, 0]
        state.indirect_rate = 0.55
        state.fringe_rate = 0.025
        state.fulltime_fringe = 0.35
        state.inflation = 0.04

        results = state.finalize()
        lines = format_results(results, state)

        # Write to temp file and parse back
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            for line in lines:
                f.write(line + "\n")
            tmp_file = f.name

        try:
            loaded = parse_log_file(tmp_file)
            assert loaded.agency == "doe"
            assert loaded.program_call == "fusion"
            assert len(loaded.pis) == 1
            assert loaded.pis[0].base_salary == 120000
            assert loaded.pis[0].summer_months == pytest.approx(0.5)
            assert loaded.number_grads == 1
            assert loaded.grad_stipend_per == 30000
            assert loaded.grad_fees_per == pytest.approx(15000.0)
            assert loaded.grad_ins_per == pytest.approx(1500.0)
            assert loaded.undergrad_salary == 4000
            assert loaded.postdoc_salary == 55000
            assert loaded.postdoc_health == 2800
            assert loaded.travel == 3000
            assert loaded.pub_costs == 500
            assert loaded.equipment == 10000
            assert loaded.subaward == [5000, 10000, 0]
            assert loaded.indirect_rate == pytest.approx(0.55)
            assert loaded.fringe_rate == pytest.approx(0.025)
            assert loaded.fulltime_fringe == pytest.approx(0.35)
            assert loaded.inflation == pytest.approx(0.04)
            assert loaded.number_years == 3
        finally:
            os.unlink(tmp_file)

    def test_parse_no_dates(self, tmp_path):
        """Log without date fields should leave use_dates=False."""
        log_content = """============================================================
Basic Grant Budget Calculator (TUI)
Run: 2026-04-08 14:30:00

Input Parameters
---------------------------------
  Number of years              = 3
  Number of faculty            = 1
    PI 1: base 9-month salary = $100,000.00, summer months = 0.25, contribution = $2,777.78
  Number of graduate students   = 1
  Grad stipend (per student)   = $26,000.00
  Grad fees (per student)      = $14,500.00
  Grad insurance (per student) = $1,232.00
  Faculty salary (year 1)      = $2,777.78
  Graduate stipend             = $26,000.00
  Graduate tuition + fees      = $14,500.00
  Graduate health insurance    = $1,232.00
  Undergraduate salary         = $0.00
  Postdoc salary               = $0.00
  Postdoc health               = $0.00
  Equipment                    = $0.00
  Travel                       = $2,500.00
  Publication costs            = $0.00
  Subawards                    = [0, 0, 0]
  Indirect rate                = 0.59
  Fringe (payroll tax) rate    = 0.0221
  Full-time fringe rate        = 0.3781
  Inflation rate               = 0.03

"""
        log_file = tmp_path / "test.log"
        log_file.write_text(log_content)
        state = parse_log_file(str(log_file))
        assert state.use_dates is False
        assert state.start_date is None
        assert state.end_date is None
        assert state.number_years == 3


# ── NSF / NASA table formatting ───────────────────────────────────


class TestFormatNsfTable:
    def test_returns_list_of_strings(self):
        state = BudgetState.from_par_file(PAR_FILE)
        results = state.finalize()
        lines = format_nsf_table(results, state)
        assert isinstance(lines, list)
        assert all(isinstance(l, str) for l in lines)

    def test_contains_key_line_items(self):
        state = BudgetState.from_par_file(PAR_FILE)
        state.pis = [PIInfo(base_salary=100000, summer_months=0.25)]
        state.travel = 2500
        results = state.finalize()
        lines = format_nsf_table(results, state)
        text = "\n".join(lines)
        assert "Faculty Salary" in text
        assert "Total Budget" in text
        assert "Modified Total Direct Costs" in text
        assert "Indirect" in text

    def test_contains_year_headers(self):
        state = BudgetState.from_par_file(PAR_FILE)
        results = state.finalize()
        lines = format_nsf_table(results, state)
        text = "\n".join(lines)
        assert "Year 1" in text
        assert "Year 2" in text
        assert "Year 3" in text
        assert "Total" in text

    def test_does_not_contain_nasa(self):
        state = BudgetState.from_par_file(PAR_FILE)
        results = state.finalize()
        lines = format_nsf_table(results, state)
        text = "\n".join(lines)
        assert "NASA" not in text
        assert "Senior/Key Person" not in text


class TestFormatNasaTable:
    def test_returns_list_of_strings(self):
        state = BudgetState.from_par_file(PAR_FILE)
        results = state.finalize()
        lines = format_nasa_table(results, state)
        assert isinstance(lines, list)
        assert all(isinstance(l, str) for l in lines)

    def test_contains_nasa_line_items(self):
        state = BudgetState.from_par_file(PAR_FILE)
        results = state.finalize()
        lines = format_nasa_table(results, state)
        text = "\n".join(lines)
        assert "Federal Research & Related (R&R) Budget Format" in text
        assert "A. Senior/Key Person" in text
        assert "K. Budget Total (I + J)" in text

    def test_does_not_contain_nsf_detail(self):
        state = BudgetState.from_par_file(PAR_FILE)
        results = state.finalize()
        lines = format_nasa_table(results, state)
        text = "\n".join(lines)
        assert "Faculty Salary" not in text
        assert "Graduate Tuition" not in text

    def test_format_results_includes_both(self):
        """format_results should contain both NSF and NASA tables."""
        state = BudgetState.from_par_file(PAR_FILE)
        results = state.finalize()
        full = format_results(results, state)
        text = "\n".join(full)
        assert "Faculty Salary" in text
        assert "Federal Research & Related (R&R) Budget Format" in text
        assert "K. Budget Total (I + J)" in text

    def test_nsf_and_nasa_totals_match(self):
        """The total budget from NSF and NASA tables should agree."""
        state = BudgetState.from_par_file(PAR_FILE)
        state.pis = [PIInfo(base_salary=100000, summer_months=0.5)]
        state.travel = 3000
        state.pub_costs = 500
        results = state.finalize()
        nsf_lines = format_nsf_table(results, state)
        nasa_lines = format_nasa_table(results, state)
        # Extract the "Total Budget" line from NSF
        nsf_total_line = [l for l in nsf_lines if "Total Budget" in l][0]
        # Extract "K. Budget Total" line from NASA
        nasa_total_line = [l for l in nasa_lines if "K. Budget Total" in l][0]
        # Both should contain the same total (last dollar amount on the line)
        import re
        nsf_totals = re.findall(r'\$[\d,]+\.\d+', nsf_total_line)
        nasa_totals = re.findall(r'\$[\d,]+\.\d+', nasa_total_line)
        assert nsf_totals[-1] == nasa_totals[-1]


# ── parse_log_file malformed input ─────────────────────────────────


class TestParseLogFileMalformed:
    def test_empty_file(self, tmp_path):
        """Empty file should return a default BudgetState (no fields parsed)."""
        log_file = tmp_path / "empty.log"
        log_file.write_text("")
        state = parse_log_file(str(log_file))
        # No fields match, so we get all defaults from BudgetState.__init__
        assert state.number_years == 3
        assert state.agency == ""
        assert len(state.pis) == 1

    def test_missing_number_of_years(self, tmp_path):
        """Log file with some fields but no 'Number of years' line."""
        log_file = tmp_path / "missing_years.log"
        log_file.write_text(
            "  Agency                       = nsf\n"
            "  Travel                       = $5,000.00\n"
        )
        state = parse_log_file(str(log_file))
        assert state.agency == "nsf"
        assert state.travel == 5000
        # number_years falls back to BudgetState default
        assert state.number_years == 3

    def test_corrupted_dollar_amount(self, tmp_path):
        """A line like 'Travel = $not_a_number' should raise ValueError."""
        log_file = tmp_path / "corrupted.log"
        log_file.write_text(
            "  Number of years              = 3\n"
            "  Travel                       = $not_a_number\n"
        )
        # parse_dollar strips '$' and ',' then calls float(), which will raise
        with pytest.raises(ValueError):
            parse_log_file(str(log_file))

    def test_missing_pi_section(self, tmp_path):
        """Log with no PI salary info should not crash."""
        log_file = tmp_path / "no_pis.log"
        log_file.write_text(
            "  Number of years              = 2\n"
            "  Travel                       = $1,000.00\n"
            "  Indirect rate                = 0.55\n"
        )
        state = parse_log_file(str(log_file))
        assert state.number_years == 2
        assert state.travel == 1000
        # No "Number of faculty" line, so pis stays at default
        assert len(state.pis) == 1

    def test_minimal_valid_log(self, tmp_path):
        """A log with just 'Number of years = 3' and nothing else."""
        log_file = tmp_path / "minimal.log"
        log_file.write_text("  Number of years              = 3\n")
        state = parse_log_file(str(log_file))
        assert state.number_years == 3
        # All other fields should be defaults
        assert state.agency == ""
        assert state.travel == 0
        assert state.equipment == 0
        assert state.indirect_rate == 0.59
        assert state.subaward == [0, 0, 0]


# ── BudgetState._snapshot() tests ─────────────────────────────────


class TestBudgetStateSnapshot:
    def test_identical_states_same_snapshot(self):
        s1 = BudgetState()
        s2 = BudgetState()
        assert s1._snapshot() == s2._snapshot()

    def test_different_after_field_change(self):
        state = BudgetState()
        snap_before = state._snapshot()
        state.agency = "nasa"
        assert state._snapshot() != snap_before

    def test_pi_change_detected(self):
        state = BudgetState()
        snap_before = state._snapshot()
        state.pis[0].base_salary = 120000
        assert state._snapshot() != snap_before

    def test_pi_summer_months_change_detected(self):
        state = BudgetState()
        snap_before = state._snapshot()
        state.pis[0].summer_months = 2.0
        assert state._snapshot() != snap_before

    def test_subaward_change_detected(self):
        state = BudgetState()
        snap_before = state._snapshot()
        state.subaward[1] = 50000
        assert state._snapshot() != snap_before

    def test_all_public_fields_covered(self):
        """Every public attribute of BudgetState should be represented in _snapshot.
        Changing any one should produce a different snapshot."""
        # Map of field name -> value that differs from default
        field_changes = {
            "agency": "nasa",
            "program_call": "compass",
            "use_dates": True,
            "start_date": date(2026, 1, 1),
            "end_date": date(2029, 1, 1),
            "number_years": 5,
            "number_grads": 3,
            "grad_stipend_per": 30000,
            "grad_fees_per": 20000.0,
            "grad_ins_per": 2000.0,
            "undergrad_salary": 5000,
            "postdoc_salary": 60000,
            "postdoc_health": 3000,
            "travel": 5000,
            "pub_costs": 1000,
            "equipment": 10000,
            "indirect_rate": 0.50,
            "fringe_rate": 0.03,
            "fulltime_fringe": 0.40,
            "inflation": 0.05,
        }
        # pis and subaward are tested separately (they are mutable containers)
        for field, new_val in field_changes.items():
            state = BudgetState()
            snap_before = state._snapshot()
            setattr(state, field, new_val)
            snap_after = state._snapshot()
            assert snap_before != snap_after, (
                f"Changing '{field}' did not change _snapshot()"
            )


# ── validate_field edge cases ──────────────────────────────────────


class TestValidateFieldEdgeCases:
    def test_empty_string_for_numeric(self):
        """Empty string for a numeric (int) field should fail validation."""
        state = BudgetState()
        ok, val, err = state.validate_field("equipment", "equipment", "")
        assert ok is False

    def test_negative_salary(self):
        """Negative salary should be rejected."""
        state = BudgetState()
        ok, val, err = state.validate_field("postdocs", "postdoc_salary", "-50000")
        assert ok is False

    def test_zero_number_years(self):
        """'0' for number_years — int validation accepts 0 (>= 0 check)."""
        state = BudgetState()
        ok, val, err = state.validate_field("project_dates", "number_years", "0")
        assert ok is True
        assert val == 0

    def test_very_large_number(self):
        """Extremely large number should still parse as valid int."""
        state = BudgetState()
        ok, val, err = state.validate_field("equipment", "equipment", "999999999999")
        assert ok is True
        assert val == 999999999999

    def test_non_numeric_string(self):
        """'abc' for a numeric field should fail."""
        state = BudgetState()
        ok, val, err = state.validate_field("travel", "travel", "abc")
        assert ok is False

    def test_empty_string_for_float(self):
        """Empty string for a float field should fail."""
        state = BudgetState()
        ok, val, err = state.validate_field("rates_inflation", "indirect_rate", "")
        assert ok is False

    def test_negative_float(self):
        """Negative float for a rate field should fail."""
        state = BudgetState()
        ok, val, err = state.validate_field("rates_inflation", "inflation", "-0.05")
        assert ok is False


# ── generate_log_filename edge cases (write_log alternatives) ──────


class TestWriteLog:
    def test_write_creates_file(self, tmp_path):
        """write_log should create a file with expected content."""
        path = str(tmp_path / "test_output.log")
        lines = ["Line 1", "Line 2", "Line 3"]
        write_log(lines, path)
        assert os.path.exists(path)
        content = open(path).read()
        assert "Line 1" in content
        assert "Line 2" in content
        assert "Line 3" in content

    def test_write_appends(self, tmp_path):
        """Calling write_log twice should append, not overwrite."""
        path = str(tmp_path / "append_test.log")
        write_log(["First call"], path)
        write_log(["Second call"], path)
        content = open(path).read()
        assert "First call" in content
        assert "Second call" in content
        # Should have two separator lines (one per call)
        assert content.count("=" * 60) == 2

    def test_special_characters_in_agency(self, tmp_path, monkeypatch):
        """Agency with spaces or special chars in filename generation."""
        monkeypatch.chdir(tmp_path)
        name = generate_log_filename("My Agency!", "test")
        assert " " not in name
        assert "!" not in name
        assert name.endswith(".log")

    def test_empty_program_call(self, tmp_path, monkeypatch):
        """Empty string for program_call."""
        monkeypatch.chdir(tmp_path)
        name = generate_log_filename("nsf", "")
        assert name.startswith("nsf_")
        assert name.endswith(".log")

    def test_version_increment(self, tmp_path, monkeypatch):
        """Create files that would collide and verify versioning works."""
        monkeypatch.chdir(tmp_path)
        name1 = generate_log_filename("test", "prog")
        (tmp_path / name1).write_text("v1")
        name2 = generate_log_filename("test", "prog")
        assert "_v2" in name2
        (tmp_path / name2).write_text("v2")
        name3 = generate_log_filename("test", "prog")
        assert "_v3" in name3

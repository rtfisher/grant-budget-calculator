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
    summary_subawards, summary_rates,
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
        assert state.grad_fees_per == 0.0
        assert state.grad_ins_per == 0.0
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

    def test_zero_for_zeroed_defaults(self):
        """With zeroed budget.par defaults, estimate should be 0."""
        state = BudgetState.from_par_file(PAR_FILE)
        est = state.recompute_estimate()
        assert est == 0.0

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
    def test_nine_categories(self):
        assert len(MENU_ITEMS) == 9

    def test_all_have_label_and_function(self):
        for label, fn in MENU_ITEMS:
            assert isinstance(label, str)
            assert callable(fn)

    def test_all_summary_fns_work_with_default_state(self):
        state = BudgetState.from_par_file(PAR_FILE)
        for label, fn in MENU_ITEMS:
            result = fn(state)
            assert isinstance(result, str), f"{label} summary_fn did not return string"

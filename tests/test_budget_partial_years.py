"""Tests for the partial-year NSF budget calculator."""

import os
import subprocess
import sys
import pytest
from datetime import date

# Add project root to path so we can import both budget modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from budget_partial_years import (
    load_parameters, dollar, calculate_budget,
    summer_months_in_period, compute_period_fractions,
    GRAD_SUMMER_FRACTION, SUBAWARD_INDIRECT_CAP, SUMMER_MONTHS,
)
from budget import calculate_budget as calc_original


# ── Unit tests for summer_months_in_period ──────────────────────────


class TestSummerMonthsInPeriod:
    def test_full_year_sep_to_sep(self):
        assert summer_months_in_period(date(2026, 9, 1), date(2027, 9, 1)) == 3

    def test_full_calendar_year(self):
        assert summer_months_in_period(date(2026, 1, 1), date(2027, 1, 1)) == 3

    def test_no_summer_oct_to_apr(self):
        assert summer_months_in_period(date(2026, 10, 1), date(2027, 4, 1)) == 0

    def test_exactly_jun_to_sep(self):
        assert summer_months_in_period(date(2026, 6, 1), date(2026, 9, 1)) == 3

    def test_starts_mid_june(self):
        """June not fully contained (starts Jun 15), but Jul and Aug are."""
        assert summer_months_in_period(date(2026, 6, 15), date(2026, 9, 1)) == 2

    def test_ends_mid_august(self):
        """Jun and Jul fully contained, but Aug not (ends Aug 15)."""
        assert summer_months_in_period(date(2026, 6, 1), date(2026, 8, 15)) == 2

    def test_two_year_span(self):
        assert summer_months_in_period(date(2026, 1, 1), date(2028, 1, 1)) == 6

    def test_zero_length(self):
        assert summer_months_in_period(date(2026, 6, 1), date(2026, 6, 1)) == 0

    def test_single_month_june(self):
        assert summer_months_in_period(date(2026, 6, 1), date(2026, 7, 1)) == 1

    def test_single_month_may(self):
        assert summer_months_in_period(date(2026, 5, 1), date(2026, 6, 1)) == 0

    def test_partial_overlap_jan_to_jul(self):
        """Jan 1 - Jul 1: June is fully contained (Jun 1 to Jul 1), Jul is not."""
        assert summer_months_in_period(date(2027, 1, 1), date(2027, 7, 1)) == 1


# ── Unit tests for compute_period_fractions ─────────────────────────


class TestComputePeriodFractions:
    def test_exact_three_years(self):
        periods = compute_period_fractions(date(2026, 9, 1), date(2029, 9, 1))
        assert len(periods) == 3
        # P1: 365 days, P2: 366 days (spans Feb 29 2028), P3: 365 days
        assert periods[0]["duration_days"] == 365
        assert periods[1]["duration_days"] == 366
        assert periods[2]["duration_days"] == 365
        for p in periods:
            assert p["frac"] == pytest.approx(p["duration_days"] / 365.25)
            assert p["summer_months"] == 3

    def test_33_months_equivalent(self):
        periods = compute_period_fractions(date(2026, 9, 1), date(2029, 6, 1))
        assert len(periods) == 3
        assert periods[0]["duration_days"] == 365
        assert periods[0]["summer_months"] == 3
        assert periods[1]["duration_days"] == 366
        assert periods[1]["summer_months"] == 3
        # P3: Sep 1 2028 to Jun 1 2029 = 273 days
        assert periods[2]["duration_days"] == 273
        assert periods[2]["frac"] == pytest.approx(273 / 365.25)
        assert periods[2]["summer_months"] == 0

    def test_6_months_no_summer(self):
        periods = compute_period_fractions(date(2026, 10, 1), date(2027, 4, 1))
        assert len(periods) == 1
        assert periods[0]["duration_days"] == 182
        assert periods[0]["frac"] == pytest.approx(182 / 365.25)
        assert periods[0]["summer_months"] == 0

    def test_18_months_with_summer(self):
        periods = compute_period_fractions(date(2026, 1, 1), date(2027, 7, 1))
        assert len(periods) == 2
        assert periods[0]["duration_days"] == 365
        assert periods[0]["summer_months"] == 3
        assert periods[1]["duration_days"] == 181
        assert periods[1]["frac"] == pytest.approx(181 / 365.25)
        # Period 2 is Jan 1 - Jul 1: June is fully contained
        assert periods[1]["summer_months"] == 1

    def test_single_month(self):
        periods = compute_period_fractions(date(2026, 3, 1), date(2026, 4, 1))
        assert len(periods) == 1
        assert periods[0]["duration_days"] == 31
        assert periods[0]["frac"] == pytest.approx(31 / 365.25)
        assert periods[0]["summer_months"] == 0

    def test_raises_on_end_before_start(self):
        with pytest.raises(ValueError):
            compute_period_fractions(date(2027, 1, 1), date(2026, 1, 1))

    def test_raises_on_equal_dates(self):
        with pytest.raises(ValueError):
            compute_period_fractions(date(2026, 1, 1), date(2026, 1, 1))

    def test_period_boundaries_correct(self):
        periods = compute_period_fractions(date(2026, 9, 1), date(2029, 6, 1))
        assert periods[0]["start"] == date(2026, 9, 1)
        assert periods[0]["end"] == date(2027, 9, 1)
        assert periods[1]["start"] == date(2027, 9, 1)
        assert periods[1]["end"] == date(2028, 9, 1)
        assert periods[2]["start"] == date(2028, 9, 1)
        assert periods[2]["end"] == date(2029, 6, 1)

    def test_mid_month_start(self):
        """Mid-month dates should work without rounding."""
        periods = compute_period_fractions(date(2026, 9, 15), date(2027, 9, 15))
        assert len(periods) == 1
        assert periods[0]["duration_days"] == 365
        assert periods[0]["frac"] == pytest.approx(365 / 365.25)
        assert periods[0]["summer_months"] == 3

    def test_mid_month_short_period(self):
        """Very short period (15 days)."""
        periods = compute_period_fractions(date(2026, 10, 10), date(2026, 10, 25))
        assert len(periods) == 1
        assert periods[0]["duration_days"] == 15
        assert periods[0]["frac"] == pytest.approx(15 / 365.25)
        assert periods[0]["summer_months"] == 0

    def test_feb29_start_nonleap_anniversary(self):
        """Feb 29 start: anniversary in non-leap year falls back to Feb 28."""
        periods = compute_period_fractions(date(2028, 2, 29), date(2029, 2, 28))
        assert len(periods) == 1
        assert periods[0]["start"] == date(2028, 2, 29)
        assert periods[0]["end"] == date(2029, 2, 28)
        assert periods[0]["duration_days"] == 365
        assert periods[0]["summer_months"] == 3

    def test_365_day_period_jan1(self):
        """Non-leap year: Jan 1 to Jan 1 = 365 days."""
        periods = compute_period_fractions(date(2026, 1, 1), date(2027, 1, 1))
        assert len(periods) == 1
        assert periods[0]["duration_days"] == 365
        assert periods[0]["frac"] == pytest.approx(365 / 365.25)

    def test_366_day_period_leap(self):
        """Leap year: Jan 1 to Jan 1 = 366 days."""
        periods = compute_period_fractions(date(2028, 1, 1), date(2029, 1, 1))
        assert len(periods) == 1
        assert periods[0]["duration_days"] == 366
        assert periods[0]["frac"] == pytest.approx(366 / 365.25)

    def test_period_boundaries_mid_month(self):
        """Mid-month start with partial last period."""
        periods = compute_period_fractions(date(2026, 9, 15), date(2028, 6, 15))
        assert len(periods) == 2
        assert periods[0]["start"] == date(2026, 9, 15)
        assert periods[0]["end"] == date(2027, 9, 15)
        assert periods[1]["start"] == date(2027, 9, 15)
        assert periods[1]["end"] == date(2028, 6, 15)
        # Verify continuity
        assert periods[0]["end"] == periods[1]["start"]


# ── Backward compatibility tests ────────────────────────────────────


class TestCalculateBudgetBackwardCompat:
    """Verify that calling calculate_budget without period_fractions
    produces identical results to the original budget.py."""

    BASE_INPUTS = dict(
        number_years=3,
        faculty_salary=120000 / 9.0 * 0.25,
        grad_salary=26000,
        grad_fees=14500.0,
        grad_ins=1232.0,
        undergrad_salary=0,
        postdoc_salary=0,
        postdoc_health=0,
        travel=2500,
        pub_costs=0,
        subaward=[0, 0, 0],
        indirect_rate=0.59,
        fringe_rate=0.0221,
        fulltime_fringe=0.3781,
        inflation=0.03,
    )

    def test_no_period_fractions_matches_original(self):
        r_new = calculate_budget(**self.BASE_INPUTS)
        r_orig = calc_original(**self.BASE_INPUTS)
        for key in ["tdc", "mtdc", "indirect", "yearly"]:
            for i in range(3):
                assert r_new[key][i] == pytest.approx(r_orig[key][i])

    def test_with_all_options_matches_original(self):
        """Test with postdoc, undergrad, subaward, equipment."""
        inputs = {**self.BASE_INPUTS,
                  "postdoc_salary": 60000, "postdoc_health": 3000,
                  "undergrad_salary": 5000, "pub_costs": 1000,
                  "equipment": 8000, "subaward": [30000, 20000, 10000]}
        r_new = calculate_budget(**inputs)
        r_orig = calc_original(**inputs)
        for key in ["tdc", "mtdc", "indirect", "yearly"]:
            for i in range(3):
                assert r_new[key][i] == pytest.approx(r_orig[key][i])

    def test_details_match_original(self):
        """Verify detail dict values match for all shared keys."""
        r_new = calculate_budget(**self.BASE_INPUTS)
        r_orig = calc_original(**self.BASE_INPUTS)
        # The original doesn't have 'frac' or 'summer_months' keys
        shared_keys = set(r_orig["details"][0].keys())
        for i in range(3):
            for key in shared_keys:
                assert r_new["details"][i][key] == pytest.approx(r_orig["details"][i][key]), \
                    f"details[{i}][{key}]: {r_new['details'][i][key]} != {r_orig['details'][i][key]}"


# ── Tests for calculate_budget with partial periods ─────────────────


class TestCalculateBudgetPartialPeriods:
    """Test calculate_budget with period_fractions provided."""

    BASE_INPUTS = dict(
        faculty_salary=120000 / 9.0 * 0.25,
        grad_salary=26000,
        grad_fees=14500.0,
        grad_ins=1232.0,
        undergrad_salary=5000,
        postdoc_salary=60000,
        postdoc_health=3000,
        travel=2500,
        pub_costs=1000,
        indirect_rate=0.59,
        fringe_rate=0.0221,
        fulltime_fringe=0.3781,
        inflation=0.03,
        equipment=0,
    )

    # Oct 1 2026 to Apr 1 2027 = 182 days
    HALF_YEAR_FRAC = 182 / 365.25

    def _full_year_pf(self):
        return {"start": date(2026, 9, 1), "end": date(2027, 9, 1),
                "duration_days": 365, "frac": 365 / 365.25, "summer_months": 3}

    def _half_year_pf(self):
        return {"start": date(2026, 10, 1), "end": date(2027, 4, 1),
                "duration_days": 182, "frac": self.HALF_YEAR_FRAC, "summer_months": 0}

    def test_single_full_year_close_to_plain(self):
        """A 365-day period should produce results very close to no-fractions."""
        r_frac = calculate_budget(
            number_years=1, **self.BASE_INPUTS,
            subaward=[0], period_fractions=[self._full_year_pf()])
        r_plain = calculate_budget(
            number_years=1, **self.BASE_INPUTS, subaward=[0])
        # 365/365.25 ≈ 0.9993, so within 0.1%
        for key in ["tdc", "mtdc", "indirect", "yearly"]:
            assert r_frac[key][0] == pytest.approx(r_plain[key][0], rel=0.001)

    def test_partial_period_costs_scaled(self):
        """A 182-day period should scale salary-type costs by 182/365.25."""
        frac = self.HALF_YEAR_FRAC
        r = calculate_budget(
            number_years=1, **self.BASE_INPUTS,
            subaward=[0], period_fractions=[self._half_year_pf()])
        d = r["details"][0]
        assert d["faculty_salary"] == pytest.approx(self.BASE_INPUTS["faculty_salary"] * frac)
        assert d["travel"] == pytest.approx(self.BASE_INPUTS["travel"] * frac)
        assert d["grad_salary"] == pytest.approx(self.BASE_INPUTS["grad_salary"] * frac)
        assert d["postdoc_salary"] == pytest.approx(self.BASE_INPUTS["postdoc_salary"] * frac)

    def test_equipment_not_scaled(self):
        """Equipment should NOT be prorated by period fraction."""
        r = calculate_budget(
            number_years=1, **{**self.BASE_INPUTS, "equipment": 15000},
            subaward=[0], period_fractions=[self._half_year_pf()])
        assert r["details"][0]["equipment"] == 15000

    def test_subaward_cap_prorated(self):
        """182-day period: cap = $25k * 182/365.25."""
        frac = self.HALF_YEAR_FRAC
        r = calculate_budget(
            number_years=1, **self.BASE_INPUTS,
            subaward=[20000], period_fractions=[self._half_year_pf()])
        assert r["details"][0]["subaward_mtdc"] == pytest.approx(25000 * frac)

    def test_subaward_under_prorated_cap(self):
        """182-day period, subaward $10k < prorated cap ~$12,457."""
        r = calculate_budget(
            number_years=1, **self.BASE_INPUTS,
            subaward=[10000], period_fractions=[self._half_year_pf()])
        assert r["details"][0]["subaward_mtdc"] == pytest.approx(10000)

    def test_zero_summer_months_no_grad_fica(self):
        """Period with 0 summer months: grad_fringe should be 0."""
        frac = self.HALF_YEAR_FRAC
        r = calculate_budget(
            number_years=1, **self.BASE_INPUTS,
            subaward=[0], period_fractions=[self._half_year_pf()])
        d = r["details"][0]
        assert d["grad_fringe"] == pytest.approx(0.0)
        expected_fringe = ((self.BASE_INPUTS["undergrad_salary"] * frac
                            + self.BASE_INPUTS["faculty_salary"] * frac) * self.BASE_INPUTS["fringe_rate"]
                           + self.BASE_INPUTS["fulltime_fringe"] * self.BASE_INPUTS["postdoc_salary"] * frac)
        assert d["total_fringe"] == pytest.approx(expected_fringe)

    def test_three_summer_months_12mo_matches_default(self):
        """365-day period with 3 summer months: grad_fringe close to default."""
        r = calculate_budget(
            number_years=1, **self.BASE_INPUTS,
            subaward=[0], period_fractions=[self._full_year_pf()])
        d = r["details"][0]
        expected = GRAD_SUMMER_FRACTION * self.BASE_INPUTS["grad_salary"] * self.BASE_INPUTS["fringe_rate"]
        assert d["grad_fringe"] == pytest.approx(expected)

    def test_inflation_fractional_exponent(self):
        """2 periods: 365 days then 182 days. Verify inflation compounding."""
        frac1 = 365 / 365.25
        frac2 = 182 / 365.25
        pf = [
            {"start": date(2026, 9, 1), "end": date(2027, 9, 1),
             "duration_days": 365, "frac": frac1, "summer_months": 3},
            {"start": date(2027, 9, 1), "end": date(2028, 3, 1),
             "duration_days": 182, "frac": frac2, "summer_months": 0},
        ]
        r = calculate_budget(
            number_years=2, **self.BASE_INPUTS,
            subaward=[0, 0], period_fractions=pf)
        d = r["details"]
        # After period 1 (frac1 ≈ 0.9993), salary inflated by (1.03)^frac1
        inflated = 26000 * (1.03 ** frac1)
        expected_grad_yr2 = inflated * frac2
        assert d[1]["grad_salary"] == pytest.approx(expected_grad_yr2)

    def test_details_contain_frac_and_summer(self):
        """Details dicts should contain 'frac' and 'summer_months' keys."""
        r = calculate_budget(
            number_years=1, **self.BASE_INPUTS,
            subaward=[0], period_fractions=[self._half_year_pf()])
        d = r["details"][0]
        assert "frac" in d
        assert "summer_months" in d
        assert d["frac"] == pytest.approx(self.HALF_YEAR_FRAC)
        assert d["summer_months"] == 0

    def test_mixed_periods_yearly_consistency(self):
        """yearly[i] must equal tdc[i] + indirect[i] for all periods."""
        pf = compute_period_fractions(date(2026, 9, 1), date(2029, 6, 1))
        r = calculate_budget(
            number_years=3, **self.BASE_INPUTS,
            subaward=[0, 0, 0], period_fractions=pf)
        for i in range(3):
            assert r["yearly"][i] == pytest.approx(r["tdc"][i] + r["indirect"][i])

    def test_all_zeros_fractional(self):
        """All-zero inputs with fractional period should produce zero outputs."""
        inputs = dict(
            number_years=1,
            faculty_salary=0, grad_salary=0, grad_fees=0, grad_ins=0,
            undergrad_salary=0, postdoc_salary=0, postdoc_health=0,
            travel=0, pub_costs=0, subaward=[0],
            indirect_rate=0.59, fringe_rate=0.0221, fulltime_fringe=0.3781,
            inflation=0.03, equipment=0,
        )
        r = calculate_budget(**inputs, period_fractions=[self._half_year_pf()])
        assert r["tdc"][0] == 0.0
        assert r["mtdc"][0] == 0.0
        assert r["indirect"][0] == 0.0
        assert r["yearly"][0] == 0.0

    def test_mid_month_period_consistency(self):
        """Mid-month periods: yearly = tdc + indirect."""
        pf = compute_period_fractions(date(2026, 9, 15), date(2029, 6, 15))
        r = calculate_budget(
            number_years=len(pf), **self.BASE_INPUTS,
            subaward=[0] * len(pf), period_fractions=pf)
        for i in range(len(pf)):
            assert r["yearly"][i] == pytest.approx(r["tdc"][i] + r["indirect"][i])


# ── Integration tests ───────────────────────────────────────────────


class TestIntegrationPartialYears:
    """Run budget_partial_years.py as a subprocess and verify output."""

    SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "budget_partial_years.py")
    PAR_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "budget.par")

    def _run(self, tmpdir, stdin_data):
        import shutil
        shutil.copy(self.PAR_FILE, str(tmpdir))
        result = subprocess.run(
            [sys.executable, self.SCRIPT],
            input=stdin_data,
            capture_output=True,
            text=True,
            cwd=str(tmpdir),
            timeout=30,
        )
        return result

    def test_defaults_no_dates(self, tmp_path):
        """Pressing Enter at date prompt should behave like budget.py."""
        if not os.path.exists(self.PAR_FILE):
            pytest.skip("budget.par not found")
        # Extra Enter for the date prompt, then same as budget.py defaults
        result = self._run(tmp_path, "\n" * 23)
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Total Budget" in result.stdout
        assert "Year 1" in result.stdout
        assert "Year 2" in result.stdout
        assert "Year 3" in result.stdout

    def test_with_dates(self, tmp_path):
        """Run with start/end dates producing a fractional last period."""
        if not os.path.exists(self.PAR_FILE):
            pytest.skip("budget.par not found")
        stdin_lines = [
            "2026-09-01",   # start date
            "2029-06-01",   # end date
        ] + [""] * 18
        result = self._run(tmp_path, "\n".join(stdin_lines) + "\n")
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Total Budget" in result.stdout
        # Should have fractional column header with approximate months
        assert "(9.0mo)" in result.stdout
        assert "2026-09-01" in result.stdout
        assert "2029-06-01" in result.stdout

    def test_with_dates_log_contains_periods(self, tmp_path):
        """Log file should contain period details with day counts."""
        if not os.path.exists(self.PAR_FILE):
            pytest.skip("budget.par not found")
        stdin_lines = ["2026-09-01", "2029-06-01"] + [""] * 18
        self._run(tmp_path, "\n".join(stdin_lines) + "\n")
        log_contents = (tmp_path / "budget.log").read_text()
        assert "Project start" in log_contents
        assert "Project end" in log_contents
        assert "Period 1" in log_contents
        assert "days" in log_contents

    def test_output_contains_nasa_format(self, tmp_path):
        """NASA R&R table should be present with fractional periods."""
        if not os.path.exists(self.PAR_FILE):
            pytest.skip("budget.par not found")
        stdin_lines = ["2026-09-01", "2029-06-01"] + [""] * 18
        result = self._run(tmp_path, "\n".join(stdin_lines) + "\n")
        assert "NASA R&R Budget Format" in result.stdout
        assert "K. Budget Total (I + J)" in result.stdout

    def test_with_mid_month_dates(self, tmp_path):
        """Mid-month dates should work without rounding messages."""
        if not os.path.exists(self.PAR_FILE):
            pytest.skip("budget.par not found")
        stdin_lines = [
            "2026-09-15",   # mid-month start
            "2029-06-15",   # mid-month end
        ] + [""] * 18
        result = self._run(tmp_path, "\n".join(stdin_lines) + "\n")
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Rounding" not in result.stdout
        assert "2026-09-15" in result.stdout
        assert "2029-06-15" in result.stdout
        assert "days" in result.stdout
        assert "Total Budget" in result.stdout

    def test_end_of_month_date(self, tmp_path):
        """Entering 3/31 as end date should work (the original bug)."""
        if not os.path.exists(self.PAR_FILE):
            pytest.skip("budget.par not found")
        stdin_lines = [
            "2026-07-01",
            "2027-03-31",   # end-of-month, previously caused rounding bug
        ] + [""] * 18
        result = self._run(tmp_path, "\n".join(stdin_lines) + "\n")
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Total Budget" in result.stdout
        # Should cover through 3/31, not truncate to 3/1
        assert "2027-03-31" in result.stdout

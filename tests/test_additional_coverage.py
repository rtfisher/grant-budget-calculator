"""Additional coverage tests for budget_partial_years.py."""

import os
import sys
import pytest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from budget_partial_years import (
    dollar, calculate_budget, summer_months_in_period,
    compute_period_fractions, SUBAWARD_INDIRECT_CAP,
)


# ── dollar() edge cases ──────────────────────────────────────────────


class TestDollar:
    def test_zero(self):
        assert dollar(0) == "$0.00"

    def test_positive(self):
        assert dollar(1234.5) == "$1,234.50"

    def test_large_number(self):
        assert dollar(1000000) == "$1,000,000.00"

    def test_fractional_cents(self):
        # Python f-string :.2f rounds half-to-even (banker's rounding)
        result = dollar(1.999)
        assert result == "$2.00"

    def test_negative(self):
        result = dollar(-500)
        # f-string places the minus after the dollar sign
        assert result == "$-500.00"


# ── Equipment excluded from MTDC ─────────────────────────────────────


class TestEquipmentMTDCExclusion:
    BASE = dict(
        number_years=1,
        faculty_salary=10000,
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
        subaward=[0],
    )

    def test_equipment_excluded_from_mtdc(self):
        r_with = calculate_budget(**self.BASE, equipment=50000)
        r_without = calculate_budget(**self.BASE, equipment=0)
        # MTDC = TDC - grad_fees - subaward - equipment
        # Equipment adds to TDC but is then subtracted for MTDC,
        # so MTDC is the same regardless of equipment value.
        assert r_with["mtdc"][0] == pytest.approx(r_without["mtdc"][0])

    def test_equipment_in_tdc_not_mtdc_base(self):
        r = calculate_budget(**self.BASE, equipment=50000)
        d = r["details"][0]
        # Equipment appears in TDC
        assert d["equipment"] == 50000
        # TDC includes equipment, MTDC excludes it
        # MTDC = TDC - grad_fees - subaward - equipment
        assert r["mtdc"][0] == pytest.approx(r["tdc"][0] - d["grad_fees"] - d["subaward"] - d["equipment"])


# ── Postdoc health included in MTDC ──────────────────────────────────


class TestPostdocHealthInMTDC:
    BASE = dict(
        number_years=1,
        faculty_salary=10000,
        grad_salary=26000,
        grad_fees=14500.0,
        grad_ins=1232.0,
        undergrad_salary=5000,
        postdoc_salary=60000,
        travel=2500,
        pub_costs=1000,
        indirect_rate=0.59,
        fringe_rate=0.0221,
        fulltime_fringe=0.3781,
        inflation=0.03,
        equipment=0,
        subaward=[0],
    )

    def test_postdoc_health_in_tdc_and_mtdc(self):
        r_with = calculate_budget(**self.BASE, postdoc_health=5000)
        r_without = calculate_budget(**self.BASE, postdoc_health=0)
        tdc_diff = r_with["tdc"][0] - r_without["tdc"][0]
        mtdc_diff = r_with["mtdc"][0] - r_without["mtdc"][0]
        # postdoc_health is in both TDC and MTDC (not excluded like grad_fees)
        assert tdc_diff == pytest.approx(5000)
        assert mtdc_diff == pytest.approx(5000)

    def test_postdoc_health_subject_to_indirect(self):
        r_with = calculate_budget(**self.BASE, postdoc_health=5000)
        r_without = calculate_budget(**self.BASE, postdoc_health=0)
        indirect_diff = r_with["indirect"][0] - r_without["indirect"][0]
        # Indirect on the postdoc_health portion = indirect_rate * 5000
        assert indirect_diff == pytest.approx(0.59 * 5000)


# ── summer_months_in_period multi-year spans ─────────────────────────


class TestSummerMonthsMultiYear:
    def test_two_full_years(self):
        # Jan 1 2025 to Jan 1 2027 spans summers of 2025 and 2026
        assert summer_months_in_period(date(2025, 1, 1), date(2027, 1, 1)) == 6

    def test_partial_start_year(self):
        # Apr 1 2025 to Jan 1 2027: June-Aug 2025 (3) + June-Aug 2026 (3) = 6
        assert summer_months_in_period(date(2025, 4, 1), date(2027, 1, 1)) == 6

    def test_partial_end_year(self):
        # Jan 1 2025 to Apr 1 2026: June-Aug 2025 fully contained (3),
        # 2026 summer months not reached by Apr 1
        assert summer_months_in_period(date(2025, 1, 1), date(2026, 4, 1)) == 3

    def test_no_summer_months(self):
        # Sep 1 2025 to May 1 2026: no summer months fully contained
        assert summer_months_in_period(date(2025, 9, 1), date(2026, 5, 1)) == 0


# ── compute_period_fractions for 5+ year projects ────────────────────


class TestLongProjects:
    def test_five_year_project(self):
        periods = compute_period_fractions(date(2025, 9, 1), date(2030, 9, 1))
        assert len(periods) == 5
        for p in periods:
            assert p["frac"] == pytest.approx(p["duration_days"] / 365.25)
            # Each period should be close to 1.0 (365 or 366 days)
            assert abs(p["frac"] - 1.0) < 0.005

    def test_five_year_fractional(self):
        # 5 years + 3 months: Sep 1 2025 to Dec 1 2030
        periods = compute_period_fractions(date(2025, 9, 1), date(2030, 12, 1))
        assert len(periods) == 6
        # First 5 periods should be approximately full years
        for p in periods[:5]:
            assert abs(p["frac"] - 1.0) < 0.005
        # Last period is fractional (Sep 1 to Dec 1 = 91 days)
        assert periods[5]["duration_days"] == 91
        assert periods[5]["frac"] == pytest.approx(91 / 365.25)


# ── Subaward above $25k — indirect cap verification ─────────────────


class TestSubawardIndirectCap:
    BASE = dict(
        number_years=1,
        faculty_salary=10000,
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

    def test_subaward_50k_cap_at_25k(self):
        r_50k = calculate_budget(**self.BASE, subaward=[50000])
        r_25k = calculate_budget(**self.BASE, subaward=[25000])
        # With subaward=50k, subaward_mtdc should be capped at 25k
        assert r_50k["details"][0]["subaward_mtdc"] == pytest.approx(25000)
        # With subaward=25k, subaward_mtdc equals the full subaward
        assert r_25k["details"][0]["subaward_mtdc"] == pytest.approx(25000)

    def test_subaward_indirect_matches_cap(self):
        r_50k = calculate_budget(**self.BASE, subaward=[50000])
        r_25k = calculate_budget(**self.BASE, subaward=[25000])
        # The indirect on the subaward portion should be the same for both
        # since the cap is $25k in both cases.
        # But total indirect differs because subaward affects MTDC differently:
        # MTDC = TDC - grad_fees - subaward - equipment
        # So MTDC is lower with 50k subaward than 25k, but the subaward
        # indirect addition (indirect_rate * min(subaward, 25k)) is the same.
        #
        # indirect = indirect_rate * mtdc + indirect_rate * subaward_mtdc
        # The subaward_mtdc contribution is the same for both.
        d_50k = r_50k["details"][0]
        d_25k = r_25k["details"][0]
        subaward_indirect_50k = self.BASE["indirect_rate"] * d_50k["subaward_mtdc"]
        subaward_indirect_25k = self.BASE["indirect_rate"] * d_25k["subaward_mtdc"]
        assert subaward_indirect_50k == pytest.approx(subaward_indirect_25k)
        assert subaward_indirect_50k == pytest.approx(0.59 * 25000)


# ── Travel and pub_costs are NOT scaled in partial periods ───────────


class TestFixedPerPeriodCosts:
    BASE = dict(
        faculty_salary=10000,
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

    def test_travel_not_scaled_in_fractional_period(self):
        # Use a date range that produces a fractional period
        periods = compute_period_fractions(date(2026, 9, 1), date(2029, 6, 1))
        # Last period is fractional (Sep 1 2028 to Jun 1 2029 = 273 days)
        assert periods[-1]["frac"] < 0.8
        r = calculate_budget(
            number_years=len(periods), **self.BASE,
            subaward=[0] * len(periods), period_fractions=periods)
        # Travel should be the full value in every period, including fractional
        for d in r["details"]:
            assert d["travel"] == 2500

    def test_pub_costs_not_scaled_in_fractional_period(self):
        periods = compute_period_fractions(date(2026, 9, 1), date(2029, 6, 1))
        r = calculate_budget(
            number_years=len(periods), **self.BASE,
            subaward=[0] * len(periods), period_fractions=periods)
        for d in r["details"]:
            assert d["pub_costs"] == 1000

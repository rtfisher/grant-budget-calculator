"""Tests for the NSF budget calculator."""

import os
import tempfile
import subprocess
import sys
import pytest

# Add project root to path so we can import budget
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from budget import load_parameters, dollar, calculate_budget, GRAD_SUMMER_FRACTION, SUBAWARD_INDIRECT_CAP


# ── Unit tests for helper functions ──────────────────────────────────


class TestDollar:
    def test_zero(self):
        assert dollar(0) == "$0.00"

    def test_positive(self):
        assert dollar(1234.5) == "$1,234.50"

    def test_large(self):
        assert dollar(1000000) == "$1,000,000.00"

    def test_negative(self):
        assert dollar(-500) == "$-500.00"

    def test_cents(self):
        assert dollar(99.999) == "$100.00"


class TestLoadParameters:
    def test_basic(self, tmp_path):
        par = tmp_path / "test.par"
        par.write_text("key1 = value1\nkey2 = 0.59\n")
        result = load_parameters(str(par))
        assert result == {"key1": "value1", "key2": "0.59"}

    def test_comments_and_blanks(self, tmp_path):
        par = tmp_path / "test.par"
        par.write_text("# comment\n\nkey = val\n  # indented comment\n")
        result = load_parameters(str(par))
        assert result == {"key": "val"}

    def test_whitespace_stripping(self, tmp_path):
        par = tmp_path / "test.par"
        par.write_text("  key_with_spaces   =   value_with_spaces  \n")
        result = load_parameters(str(par))
        assert result == {"key_with_spaces": "value_with_spaces"}

    def test_equals_in_value(self, tmp_path):
        par = tmp_path / "test.par"
        par.write_text("key = a=b\n")
        result = load_parameters(str(par))
        assert result == {"key": "a=b"}

    def test_line_without_equals_is_skipped(self, tmp_path):
        par = tmp_path / "test.par"
        par.write_text("valid = yes\ninvalid line\n")
        result = load_parameters(str(par))
        assert result == {"valid": "yes"}

    def test_real_par_file(self):
        """Verify the shipped budget.par file is parseable."""
        par_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "budget.par")
        if not os.path.exists(par_path):
            pytest.skip("budget.par not found")
        result = load_parameters(par_path)
        assert "indirect_rate" in result
        assert "fringe_rate" in result
        assert "fulltime_fringe" in result
        assert float(result["indirect_rate"]) > 0


# ── Unit tests for calculate_budget ──────────────────────────────────


class TestCalculateBudget:
    """Test the core budget calculation engine with known inputs."""

    # Standard test inputs matching budget.par defaults
    BASE_INPUTS = dict(
        number_years=3,
        faculty_salary=120000 / 9.0 * 0.25,  # 1 PI, 0.25 months
        grad_salary=26000,
        grad_fees=12415.0,
        grad_ins=1395.0,
        undergrad_salary=0,
        postdoc_salary=0,
        postdoc_health=0,
        travel=2500,
        pub_costs=0,
        subaward=[0, 0, 0],
        indirect_rate=0.59,
        fringe_rate=0.0211,
        fulltime_fringe=0.4531,
        inflation=0.03,
    )

    def test_returns_correct_keys(self):
        r = calculate_budget(**self.BASE_INPUTS)
        assert set(r.keys()) == {"tdc", "mtdc", "indirect", "yearly", "details"}

    def test_correct_number_of_years(self):
        r = calculate_budget(**self.BASE_INPUTS)
        assert len(r["tdc"]) == 3
        assert len(r["mtdc"]) == 3
        assert len(r["indirect"]) == 3
        assert len(r["yearly"]) == 3
        assert len(r["details"]) == 3

    def test_yearly_equals_tdc_plus_indirect(self):
        r = calculate_budget(**self.BASE_INPUTS)
        for y in range(3):
            assert r["yearly"][y] == pytest.approx(r["tdc"][y] + r["indirect"][y])

    def test_mtdc_excludes_fees_and_insurance(self):
        r = calculate_budget(**self.BASE_INPUTS)
        for y in range(3):
            # MTDC = TDC - grad_fees - grad_ins - subaward (all zero here)
            expected_diff = r["tdc"][y] - r["mtdc"][y]
            # grad_fees and grad_ins inflate each year
            assert expected_diff > 0

    def test_no_subaward_no_subaward_indirect(self):
        r = calculate_budget(**self.BASE_INPUTS)
        # With zero subawards, indirect should just be indirect_rate * mtdc
        for y in range(3):
            assert r["indirect"][y] == pytest.approx(0.59 * r["mtdc"][y])

    def test_subaward_capped_at_25k(self):
        inputs = {**self.BASE_INPUTS, "subaward": [50000, 0, 0]}
        r = calculate_budget(**inputs)
        # Year 0: indirect = rate * mtdc + rate * min(50000, 25000)
        expected_sub_indirect = 0.59 * 25000
        # The subaward indirect component
        indirect_without_sub = 0.59 * r["mtdc"][0]
        assert r["indirect"][0] == pytest.approx(indirect_without_sub + expected_sub_indirect)

    def test_subaward_under_cap(self):
        inputs = {**self.BASE_INPUTS, "subaward": [10000, 0, 0]}
        r = calculate_budget(**inputs)
        expected_sub_indirect = 0.59 * 10000
        indirect_without_sub = 0.59 * r["mtdc"][0]
        assert r["indirect"][0] == pytest.approx(indirect_without_sub + expected_sub_indirect)

    def test_subaward_per_year(self):
        """Verify subaward indirect is calculated independently for each year."""
        inputs = {**self.BASE_INPUTS, "subaward": [0, 50000, 30000]}
        r = calculate_budget(**inputs)
        # Year 0: no subaward, no subaward indirect
        assert r["details"][0]["subaward_mtdc"] == 0
        # Year 1: subaward of 50000, capped at 25000
        assert r["details"][1]["subaward_mtdc"] == 25000
        # Year 2: subaward of 30000, capped at 25000
        assert r["details"][2]["subaward_mtdc"] == 25000

    def test_subaward_excluded_from_mtdc(self):
        inputs = {**self.BASE_INPUTS, "subaward": [10000, 0, 0]}
        r = calculate_budget(**inputs)
        r_no_sub = calculate_budget(**self.BASE_INPUTS)
        # MTDC should not include the subaward
        # TDC increases by subaward, but MTDC stays the same
        assert r["mtdc"][0] == pytest.approx(r_no_sub["mtdc"][0])

    def test_inflation_applied_correctly(self):
        r = calculate_budget(**self.BASE_INPUTS)
        # Year 2 grad_salary should be year 1 * 1.03
        d = r["details"]
        assert d[1]["grad_salary"] == pytest.approx(d[0]["grad_salary"] * 1.03)
        assert d[2]["grad_salary"] == pytest.approx(d[0]["grad_salary"] * 1.03**2)

    def test_inflation_compounds_faculty(self):
        r = calculate_budget(**self.BASE_INPUTS)
        d = r["details"]
        assert d[1]["faculty_salary"] == pytest.approx(d[0]["faculty_salary"] * 1.03)

    def test_zero_inflation(self):
        inputs = {**self.BASE_INPUTS, "inflation": 0.0}
        r = calculate_budget(**inputs)
        d = r["details"]
        assert d[0]["grad_salary"] == d[1]["grad_salary"] == d[2]["grad_salary"]

    def test_one_year(self):
        inputs = {**self.BASE_INPUTS, "number_years": 1, "subaward": [0]}
        r = calculate_budget(**inputs)
        assert len(r["tdc"]) == 1
        assert len(r["details"]) == 1

    def test_fringe_computation(self):
        """Verify fringe = (0.25*grad + undergrad + faculty) * fringe_rate + fulltime*postdoc."""
        inputs = {**self.BASE_INPUTS,
                  "postdoc_salary": 50000,
                  "undergrad_salary": 5000}
        r = calculate_budget(**inputs)
        d = r["details"][0]
        faculty = inputs["faculty_salary"]
        expected_fringe = ((GRAD_SUMMER_FRACTION * 26000 + 5000 + faculty) * 0.0211
                           + 0.4531 * 50000)
        assert d["total_fringe"] == pytest.approx(expected_fringe)

    def test_postdoc_total(self):
        inputs = {**self.BASE_INPUTS, "postdoc_salary": 55000, "postdoc_health": 3000}
        r = calculate_budget(**inputs)
        d = r["details"][0]
        expected = (1 + 0.4531) * 55000 + 3000
        assert d["total_postdoc"] == pytest.approx(expected)

    def test_all_zeros(self):
        """Budget with all-zero inputs should produce all-zero outputs."""
        inputs = dict(
            number_years=1,
            faculty_salary=0, grad_salary=0, grad_fees=0, grad_ins=0,
            undergrad_salary=0, postdoc_salary=0, postdoc_health=0,
            travel=0, pub_costs=0, subaward=[0],
            indirect_rate=0.59, fringe_rate=0.0211, fulltime_fringe=0.4531,
            inflation=0.03,
        )
        r = calculate_budget(**inputs)
        assert r["tdc"][0] == 0.0
        assert r["mtdc"][0] == 0.0
        assert r["indirect"][0] == 0.0
        assert r["yearly"][0] == 0.0

    def test_detail_years_are_one_indexed(self):
        r = calculate_budget(**self.BASE_INPUTS)
        assert r["details"][0]["year"] == 1
        assert r["details"][2]["year"] == 3

    def test_tdc_components_sum(self):
        """Verify TDC is the sum of all its components."""
        inputs = {**self.BASE_INPUTS,
                  "postdoc_salary": 50000, "postdoc_health": 2000,
                  "undergrad_salary": 3000, "pub_costs": 500,
                  "subaward": [10000, 0, 0]}
        r = calculate_budget(**inputs)
        d = r["details"][0]
        expected_tdc = (d["faculty_salary"] + d["grad_salary"] + inputs["grad_fees"]
                        + inputs["grad_ins"] + d["postdoc_salary"] + d["undergrad_salary"]
                        + d["travel"] + d["pub_costs"] + d["total_fringe"]
                        + inputs["postdoc_health"] + d["subaward"])
        assert r["tdc"][0] == pytest.approx(expected_tdc)


# ── Integration test via subprocess ──────────────────────────────────


class TestIntegration:
    """Run budget.py as a subprocess with piped input and verify output."""

    SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "budget.py")
    PAR_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "budget.par")

    def _run_with_defaults(self, tmpdir):
        """Run the script accepting all defaults (press Enter for every prompt)."""
        # Copy budget.par to tmpdir so the script finds it
        import shutil
        shutil.copy(self.PAR_FILE, str(tmpdir))

        # 18 Enter presses: years, PIs, base salary, months, grad, fees, ins,
        # undergrad, postdoc, postdoc_health, travel, pub, subaward,
        # indirect, fringe, fulltime_fringe, inflation
        # (some prompts use two-line entry for subaward)
        stdin_data = "\n" * 20

        result = subprocess.run(
            [sys.executable, self.SCRIPT],
            input=stdin_data,
            capture_output=True,
            text=True,
            cwd=str(tmpdir),
            timeout=30,
        )
        return result

    def test_exits_cleanly_with_defaults(self, tmp_path):
        if not os.path.exists(self.PAR_FILE):
            pytest.skip("budget.par not found")
        result = self._run_with_defaults(tmp_path)
        assert result.returncode == 0, f"stderr: {result.stderr}"

    def test_output_contains_summary(self, tmp_path):
        if not os.path.exists(self.PAR_FILE):
            pytest.skip("budget.par not found")
        result = self._run_with_defaults(tmp_path)
        assert "Total Budget" in result.stdout

    def test_output_contains_three_years(self, tmp_path):
        if not os.path.exists(self.PAR_FILE):
            pytest.skip("budget.par not found")
        result = self._run_with_defaults(tmp_path)
        assert "Year 1" in result.stdout
        assert "Year 2" in result.stdout
        assert "Year 3" in result.stdout

    def test_log_file_created(self, tmp_path):
        if not os.path.exists(self.PAR_FILE):
            pytest.skip("budget.par not found")
        self._run_with_defaults(tmp_path)
        log_path = tmp_path / "budget.log"
        assert log_path.exists()
        contents = log_path.read_text()
        assert "Input Parameters" in contents

    def test_dollar_formatting_in_output(self, tmp_path):
        if not os.path.exists(self.PAR_FILE):
            pytest.skip("budget.par not found")
        result = self._run_with_defaults(tmp_path)
        # Output should contain dollar-formatted values
        assert "$" in result.stdout

    def test_missing_par_file(self, tmp_path):
        """Script should exit with error if budget.par is missing."""
        result = subprocess.run(
            [sys.executable, self.SCRIPT],
            input="\n" * 20,
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            timeout=10,
        )
        assert result.returncode != 0
        assert "budget.par" in result.stdout

"""
RealityDB Configuration Loader
================================
All financial constants, distributions,
scenario definitions, and document
formatting live in config/ YAML files.

This module loads and caches them.
Generator code imports from here —
never hardcodes values directly.

Usage:
  from realitydb_docs.config import cfg

  # Financial constants
  ss_rate = cfg.ss_rate
  ss_base = cfg.ss_wage_base

  # Scenario parameters
  scenario = cfg.get_scenario("approved")
  income = scenario["annual_income"]

  # Distribution ranges
  inc_min, inc_max = cfg.income_min, cfg.income_max

  # Document formatting
  header_color = cfg.documents["colors"]["header_bg"]

Updating for a new tax year:
  Edit config/financial.yaml:
    tax_year: 2025
    fica:
      ss_wage_base: 168600   # 2025 IRS value
  No code changes needed.

Adding a new scenario:
  Edit config/scenarios.yaml:
    scenarios:
      jumbo_prime:
        annual_income: 350000
        ...
  Available immediately in the CLI.

Pointing at your own config
---------------------------
Set REALITYDB_CONFIG_DIR to a directory holding your own
financial.yaml / distributions.yaml / scenarios.yaml /
documents.yaml. Any file present there wins; anything absent
falls back to the bundled defaults, so an override directory
containing only scenarios.yaml is valid.

  set REALITYDB_CONFIG_DIR=C:\\acme\\realitydb-config

This is how a customer ships their own scenarios and
underwriting thresholds without forking the generator.
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
except ImportError:  # pragma: no cover - dependency is declared in setup.py
    raise ImportError(
        "PyYAML required. Install with: "
        "pip install pyyaml"
    )

# The bundled defaults, one level up from this file.
DEFAULT_CONFIG_DIR = Path(__file__).parent.parent / "config"

# Environment variable naming an override directory.
CONFIG_DIR_ENV = "REALITYDB_CONFIG_DIR"

CONFIG_FILES = (
    "financial.yaml",
    "distributions.yaml",
    "scenarios.yaml",
    "documents.yaml",
)


def config_search_path() -> List[Path]:
    """Directories searched for a config file, highest priority first.

    The bundled directory sits beside the package rather than inside it, so a
    wheel built from setup.py's find_packages() would not carry it. The
    override entry is what makes that recoverable, and it is the documented
    way for a customer to supply their own scenarios.
    """
    candidates: List[Path] = []
    override = os.environ.get(CONFIG_DIR_ENV)
    if override:
        candidates.append(Path(override).expanduser())
    candidates.append(DEFAULT_CONFIG_DIR)
    # Working-directory fallback, for a checkout invoked from its root.
    candidates.append(Path.cwd() / "config")
    seen = set()
    ordered = []
    for path in candidates:
        resolved = str(path)
        if resolved not in seen:
            seen.add(resolved)
            ordered.append(path)
    return ordered


class _Config:
    """
    Lazy-loading config container.
    Files are read once and cached.
    """

    def __init__(self):
        self._cache: Dict[str, dict] = {}

    def _load(self, filename: str) -> dict:
        """Load a YAML config file from the first directory that has it."""
        searched = config_search_path()
        for directory in searched:
            path = directory / filename
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if not isinstance(data, dict):
                    raise ValueError(
                        f"Config file {path} did not parse to a mapping "
                        f"(got {type(data).__name__})."
                    )
                return data
        locations = "\n".join(f"  {d}" for d in searched)
        raise FileNotFoundError(
            f"Config file not found: {filename}\n"
            f"Searched:\n{locations}\n"
            f"Run from the repo root, or set {CONFIG_DIR_ENV} to a "
            f"directory containing it."
        )

    def _section(self, filename: str) -> dict:
        if filename not in self._cache:
            self._cache[filename] = self._load(filename)
        return self._cache[filename]

    @property
    def financial(self) -> dict:
        return self._section("financial.yaml")

    @property
    def distributions(self) -> dict:
        return self._section("distributions.yaml")

    @property
    def scenarios_data(self) -> dict:
        return self._section("scenarios.yaml")

    @property
    def documents(self) -> dict:
        return self._section("documents.yaml")

    # ── Convenience accessors ──────────────────────

    def get_scenario(self, name: str) -> dict:
        """Get scenario parameters by name."""
        all_scenarios = self.scenarios_data.get("scenarios", {}) or {}
        if name not in all_scenarios:
            available = sorted(all_scenarios)
            raise ValueError(
                f"Unknown scenario '{name}'. "
                f"Available: {available}"
            )
        return all_scenarios[name]

    def scenario_params(self, name: str) -> dict:
        """Scenario parameters with the prose `description` removed.

        `description` is documentation for a human reading the YAML; passing it
        through to FinancialCaseGenerator.generate() as a keyword would be a
        TypeError, so it is stripped once here rather than at each call site.
        """
        return {
            k: v for k, v in self.get_scenario(name).items()
            if k != "description"
        }

    def list_scenarios(self) -> list:
        """List all available scenario names."""
        return list((self.scenarios_data.get("scenarios", {}) or {}).keys())

    def get_alignment(self, code: str) -> dict:
        """Get alignment class definition."""
        classes = self.scenarios_data.get("alignment_classes", {}) or {}
        if code not in classes:
            available = sorted(classes)
            raise ValueError(
                f"Unknown alignment '{code}'. "
                f"Available: {available}"
            )
        return classes[code]

    def list_alignments(self, available_only: bool = True) -> list:
        """List alignment classes."""
        classes = self.scenarios_data.get("alignment_classes", {}) or {}
        if available_only:
            return [
                k for k, v in classes.items()
                if v.get("available", False)
            ]
        return list(classes.keys())

    def is_alignment_available(self, code: str) -> bool:
        return bool(self.get_alignment(code).get("available", False))

    # ── Financial shortcuts ────────────────────────

    @property
    def tax_year(self) -> int:
        return self.financial["tax_year"]

    @property
    def ss_rate(self) -> float:
        return self.financial["fica"]["ss_rate"]

    @property
    def ss_wage_base(self) -> int:
        return self.financial["fica"]["ss_wage_base"]

    @property
    def medicare_rate(self) -> float:
        return self.financial["fica"]["medicare_rate"]

    @property
    def pay_periods_biweekly(self) -> int:
        return self.financial["pay_periods"]["bi_weekly"]

    @property
    def retirement_options(self) -> list:
        return self.financial["retirement"]["contribution_options"]

    @property
    def retirement_cap(self) -> float:
        return self.financial["retirement"]["cap"]

    @property
    def capped_retirement_options(self) -> list:
        """Contribution options at or below the cap.

        Raises rather than returning an empty list: a silently empty option
        list would fail later inside random.choice with a message that says
        nothing about the config.
        """
        options = [
            r for r in self.retirement_options if r <= self.retirement_cap
        ]
        if not options:
            raise ValueError(
                f"No retirement contribution_options at or below cap "
                f"{self.retirement_cap} in config/financial.yaml"
            )
        return options

    @property
    def withholding_federal_range(self) -> tuple:
        w = self.financial["withholding"]
        return (w["federal_rate_min"], w["federal_rate_max"])

    @property
    def withholding_state_range(self) -> tuple:
        w = self.financial["withholding"]
        return (w["state_rate_min"], w["state_rate_max"])

    @property
    def underwriting(self) -> dict:
        return self.financial["underwriting"]

    @property
    def dti_threshold_qm(self) -> float:
        return self.underwriting["dti_threshold_qm"]

    @property
    def dti_threshold_max(self) -> float:
        return self.underwriting["dti_threshold_max"]

    @property
    def ltv_threshold(self) -> float:
        return self.underwriting["ltv_threshold"]

    @property
    def min_credit_score(self) -> int:
        return self.underwriting["min_credit_score"]

    @property
    def housing_ratio_range(self) -> tuple:
        u = self.underwriting
        return (u["housing_ratio_min"], u["housing_ratio_max"])

    @property
    def ssn_config(self) -> dict:
        return self.financial["ssn"]

    @property
    def ssn_prefix(self) -> str:
        return self.financial["ssn"]["prefix"]

    # ── Distribution shortcuts ─────────────────────

    @property
    def income_min(self) -> float:
        return self.distributions["income"]["min"]

    @property
    def income_max(self) -> float:
        return self.distributions["income"]["max"]

    @property
    def checking_months_range(self) -> tuple:
        a = self.distributions["assets"]
        return (a["checking_months_min"], a["checking_months_max"])

    @property
    def savings_months_range(self) -> tuple:
        a = self.distributions["assets"]
        return (a["savings_months_min"], a["savings_months_max"])

    @property
    def retirement_balance_range(self) -> tuple:
        a = self.distributions["assets"]
        return (
            a["retirement_income_ratio_min"],
            a["retirement_income_ratio_max"],
        )

    @property
    def credit_card_range(self) -> tuple:
        li = self.distributions["liabilities"]
        return (li["credit_card_min"], li["credit_card_max"])

    @property
    def other_debt_range(self) -> tuple:
        li = self.distributions["liabilities"]
        return (li["other_debt_min"], li["other_debt_max"])

    @property
    def debt_shares(self) -> tuple:
        li = self.distributions["liabilities"]
        return (li["car_share"], li["student_share"])

    @property
    def loan_terms(self) -> tuple:
        loan = self.distributions["loan"]
        return (loan["term_years"], loan["term_weights"])

    @property
    def loan_types(self) -> tuple:
        loan = self.distributions["loan"]
        return (loan["types"], loan["type_weights"])

    @property
    def loan_amount_range(self) -> tuple:
        loan = self.distributions["loan"]
        return (loan["amount_min"], loan["amount_max"])

    @property
    def employment_types(self) -> tuple:
        emp = self.distributions["employment"]
        return (emp["types"], emp["type_weights"])

    @property
    def years_at_job_range(self) -> tuple:
        emp = self.distributions["employment"]
        return (emp["years_at_job_min"], emp["years_at_job_max"])

    @property
    def age_range(self) -> tuple:
        b = self.distributions["borrower"]
        return (b["age_min"], b["age_max"])

    @property
    def years_at_address_range(self) -> tuple:
        b = self.distributions["borrower"]
        return (b["years_at_address_min"], b["years_at_address_max"])

    @property
    def variable_transactions_range(self) -> tuple:
        t = self.distributions["transactions"]
        return (t["variable_per_month_min"], t["variable_per_month_max"])

    @property
    def payroll_variation(self) -> float:
        return self.distributions["transactions"]["payroll_variation"]

    @property
    def income_variation(self) -> float:
        return self.distributions["transactions"]["income_variation"]

    # ── Document shortcuts ─────────────────────────

    @property
    def watermark_text(self) -> str:
        return self.documents["watermark"]["text"]

    @property
    def watermark_opacity(self) -> float:
        return self.documents["watermark"]["opacity"]

    @property
    def watermark_font_size(self) -> float:
        return self.documents["watermark"]["font_size"]

    @property
    def footer_text(self) -> str:
        return self.documents["footer"]["text"].strip()

    def color(self, name: str) -> str:
        return self.documents["colors"][name]

    def font(self, name: str) -> Any:
        return self.documents["fonts"][name]

    @property
    def legal(self) -> dict:
        return self.documents["legal"]

    def reload(self) -> None:
        """Force reload all config files.

        Note that modules which snapshot a config value into a module-level
        constant at import time (paystub.TOTAL_PERIODS, profile.SS_RATE) are
        not affected by a reload; they are read once when the module is first
        imported.
        """
        self._cache.clear()

    def describe(self) -> dict:
        """Where each config file was actually loaded from.

        Useful when an override directory is in play and a value is not what
        was expected.
        """
        out = {}
        for filename in CONFIG_FILES:
            found: Optional[str] = None
            for directory in config_search_path():
                if (directory / filename).exists():
                    found = str(directory / filename)
                    break
            out[filename] = found
        return out


# ── Singleton instance ─────────────────────────────
# Import this everywhere:
#   from realitydb_docs.config import cfg
cfg = _Config()

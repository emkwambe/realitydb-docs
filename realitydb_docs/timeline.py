"""
RealityDB Financial Cases — Life Event Engine
===============================================
Transforms static borrower snapshots into
living financial profiles that evolve over time.

A BorrowerProfile describes a financial state
at one moment in time.

A BorrowerTimeline describes how that state
evolved — what events happened, when, and
what financial consequences they produced.

Every document in a timeline case is a
snapshot of the borrower's financial world
at a specific moment — not a standalone artifact.

Architecture:
  LifeEvent — something that happened
    (pure function: profile_before → profile_after)

  BorrowerTimeline — sequence of events
    over a period of months

  state_at(month) — returns BorrowerProfile
    representing financial state at that month,
    with all prior events applied

  TimelineCaseBundler.generate_timeline_case() —
    generates a complete case folder (documents +
    truth + evaluation) reflecting state at that month

Three views of one timeline
---------------------------
A fraud case is only a fraud case if some document
disagrees with the world. Three accessors exist so
that disagreement is representable:

  state_at(month)         every event applied
  world_state_at(month)   what is actually true
  claimed_state_at(month) what the application says

For a timeline with no fraud events all three are
identical, and the case is A0. The split matters
only when a fraud event is present:

  INCOME_INFLATION, EMPLOYER_MISMATCH
    claim-side. The borrower states something the
    world does not support, so the event applies to
    the application and NOT to the W-2, the pay
    stubs or the bank statements.

  UNDISCLOSED_DEBT
    world-side. The debt is real and shows up as a
    recurring payment on the bank statements; it is
    the application that omits it.

The documents are rendered accordingly: the 1003
comes from the claimed state, every other document
from the world state. That is what makes the
inconsistency detectable by reading the PDFs, which
is the task a customer is buying.

Usage:
  from realitydb_docs.timeline import (
      BorrowerTimeline,
      LifeEvent,
      EventType,
      TimelineCaseBundler,
  )
  from realitydb_docs.profile import (
      BorrowerProfile,
      FinancialCaseGenerator,
  )

  gen = FinancialCaseGenerator()
  starting_profile = gen.generate(
      seed=42,
      annual_income=72000,
      loan_amount=320000,
      property_value=420000,
      dti_target=0.36,
  )

  timeline = BorrowerTimeline(
      profile=starting_profile,
      months=18,
      seed=42,
  )

  timeline.add_event(LifeEvent(
      month=3,
      event_type=EventType.PROMOTION,
      description="Promoted to Senior Analyst",
      params={"income_increase_pct": 0.20},
  ))

  timeline.add_event(LifeEvent(
      month=7,
      event_type=EventType.CAR_PURCHASE,
      description="Purchased used Honda Civic",
      params={
          "monthly_payment": 449.0,
          "down_payment": 3000.0,
          "vehicle": "2021 Honda Civic",
      },
  ))

  state_at_18 = timeline.state_at(18)
  print(f"Income at month 18: {state_at_18.annual_gross_income:,.0f}")
  print(f"DTI at month 18: {state_at_18.dti_ratio:.1%}")

A note on the expected decision
-------------------------------
`profile.expected_decision` is the scenario label the
timeline started from. It is NOT recomputed from the
evolved state — a career-growth timeline that improves
DTI still carries the label it began with. Every file
this module writes says so rather than implying the
decision was derived. Deriving it is the obvious next
sprint; asserting it here would be a claim the code
does not support.
"""

import copy
import json
import os
import shutil
import zipfile
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from realitydb_docs.profile import (
    BorrowerProfile,
    FinancialCaseGenerator,
)

GENERATOR_VERSION = "0.6.0"


# ── Event types ───────────────────────────────────────────

class EventType(str, Enum):
    """
    Life events that change a borrower's
    financial state over time.
    """
    # Career
    PROMOTION      = "promotion"
    RAISE          = "raise"
    JOB_CHANGE     = "job_change"
    LAYOFF         = "layoff"
    NEW_EMPLOYMENT = "new_employment"
    SELF_EMPLOYED  = "self_employed"

    # Financial
    CAR_PURCHASE   = "car_purchase"
    CAR_PAYOFF     = "car_payoff"
    STUDENT_PAYOFF = "student_loan_payoff"
    LARGE_DEPOSIT  = "large_deposit"
    MEDICAL_BILL   = "medical_bill"
    DEBT_PAYOFF    = "debt_payoff"

    # Life
    MOVE           = "move"
    MARRIAGE       = "marriage"
    BABY           = "baby"
    DIVORCE        = "divorce"

    # Property
    HOME_PURCHASE  = "home_purchase"
    REFINANCE      = "refinance"

    # Fraud injection (A3/A4 cases)
    INCOME_INFLATION   = "income_inflation"
    UNDISCLOSED_DEBT   = "undisclosed_debt"
    EMPLOYER_MISMATCH  = "employer_mismatch"


# Events that change only what the APPLICATION claims. The W-2, the pay stubs
# and the bank statements are rendered without them, so the overstatement is
# visible by comparing documents rather than only by reading the truth files.
CLAIM_ONLY_EVENTS = frozenset({
    EventType.INCOME_INFLATION,
    EventType.EMPLOYER_MISMATCH,
})

# Events that are real but omitted from the application. The payment appears
# on the bank statements; the 1003 does not declare it.
HIDDEN_EVENTS = frozenset({
    EventType.UNDISCLOSED_DEBT,
})

# Every event that marks a case as misaligned.
FRAUD_EVENTS = CLAIM_ONLY_EVENTS | HIDDEN_EVENTS


# ── LifeEvent ─────────────────────────────────────────────

@dataclass
class LifeEvent:
    """
    A single event in a borrower's financial life.

    Events are pure functions:
      apply(profile_before) → profile_after

    Same event applied to same profile
    always produces the same result.
    Nothing is mutated — a new profile
    is returned each time.

    Attributes:
        month: Month number in the timeline
               (1 = first month, 18 = final month)
        event_type: What kind of event
        description: Human-readable narrative
        params: Event-specific parameters
                (income_increase_pct, monthly_payment, etc.)
        fraud_flag: If not None, this event introduces
                    a deliberate inconsistency (A3/A4)
    """
    month: int
    event_type: EventType
    description: str
    params: dict = field(default_factory=dict)
    fraud_flag: Optional[str] = None

    def apply(
        self,
        profile: BorrowerProfile,
    ) -> BorrowerProfile:
        """
        Apply this event to a profile.
        Returns a new profile — does not mutate.
        """
        # Deep copy so we never mutate the original
        p = copy.deepcopy(profile)

        handler = _EVENT_HANDLERS.get(self.event_type)
        if handler is None:
            raise ValueError(
                f"No handler for event type: "
                f"{self.event_type}"
            )

        return handler(p, self.params)

    @property
    def is_fraud(self) -> bool:
        """Whether this event introduces a deliberate inconsistency.

        Keyed off the event type rather than off fraud_flag: an
        INCOME_INFLATION event still splits world from claim whether or not
        the caller remembered to label it.
        """
        return (
            self.event_type in FRAUD_EVENTS
            or self.fraud_flag is not None
        )

    def to_dict(self) -> dict:
        return {
            "month": self.month,
            "event_type": self.event_type.value,
            "description": self.description,
            "params": self.params,
            "fraud_flag": self.fraud_flag,
        }


# ── Event handlers ────────────────────────────────────────
# Each handler: (profile, params) → new profile
# The profile passed in is already a copy (LifeEvent.apply deep-copies before
# calling), so mutating it here is local and the caller's profile is untouched.

def _handle_promotion(
    p: BorrowerProfile, params: dict
) -> BorrowerProfile:
    """
    Promotion: income increases, title may change.
    params:
      income_increase_pct: float (e.g. 0.20 = 20%)
      new_title: str (optional)
    """
    pct = params.get("income_increase_pct", 0.15)
    p.annual_gross_income *= (1 + pct)
    if "new_title" in params:
        p.job_title = params["new_title"]
    return p


def _handle_raise(
    p: BorrowerProfile, params: dict
) -> BorrowerProfile:
    """
    Raise: income increases, title unchanged.
    params:
      income_increase_pct: float
      OR income_increase_amount: float
    """
    if "income_increase_pct" in params:
        p.annual_gross_income *= (
            1 + params["income_increase_pct"]
        )
    elif "income_increase_amount" in params:
        p.annual_gross_income += (
            params["income_increase_amount"]
        )
    return p


def _handle_job_change(
    p: BorrowerProfile, params: dict
) -> BorrowerProfile:
    """
    Job change: new employer, possibly new income.
    params:
      new_employer: str
      new_title: str (optional)
      income_change_pct: float (optional, default 0)
    """
    p.employer_name = params.get(
        "new_employer", p.employer_name
    )
    if "new_title" in params:
        p.job_title = params["new_title"]
    if "income_change_pct" in params:
        p.annual_gross_income *= (
            1 + params["income_change_pct"]
        )
    p.years_at_job = 0.0  # Reset tenure
    return p


def _handle_layoff(
    p: BorrowerProfile, params: dict
) -> BorrowerProfile:
    """
    Layoff: income stops or drops significantly.
    params:
      unemployment_pct: float (income replacement,
        default 0.40 — typical unemployment benefit)
    """
    replacement = params.get("unemployment_pct", 0.40)
    p.annual_gross_income *= replacement
    return p


def _handle_new_employment(
    p: BorrowerProfile, params: dict
) -> BorrowerProfile:
    """
    New employment after gap.
    params:
      new_employer: str
      new_annual_income: float
      new_title: str (optional)
    """
    if "new_employer" in params:
        p.employer_name = params["new_employer"]
    if "new_annual_income" in params:
        p.annual_gross_income = params["new_annual_income"]
    if "new_title" in params:
        p.job_title = params["new_title"]
    p.years_at_job = 0.0
    return p


def _handle_car_purchase(
    p: BorrowerProfile, params: dict
) -> BorrowerProfile:
    """
    Car purchase: new monthly debt, checking drops.
    params:
      monthly_payment: float
      down_payment: float (optional, default 0)
      vehicle: str (optional, for narrative)
    """
    payment = params.get("monthly_payment", 449.0)
    down = params.get("down_payment", 0.0)
    p.monthly_car_payment += payment
    p.checking_balance = max(
        0, p.checking_balance - down
    )
    return p


def _handle_car_payoff(
    p: BorrowerProfile, params: dict
) -> BorrowerProfile:
    """
    Car loan paid off: monthly debt decreases.
    params:
      payment_amount: float (amount removed,
        default = all car payment)
    """
    amount = params.get(
        "payment_amount", p.monthly_car_payment
    )
    p.monthly_car_payment = max(
        0, p.monthly_car_payment - amount
    )
    return p


def _handle_student_payoff(
    p: BorrowerProfile, params: dict
) -> BorrowerProfile:
    """Student loan fully paid off."""
    p.monthly_student_loan = 0.0
    return p


def _handle_large_deposit(
    p: BorrowerProfile, params: dict
) -> BorrowerProfile:
    """
    Large deposit: checking balance increases.
    This may be a bonus, gift, inheritance, etc.
    In A3/A4 cases this could be unexplained.
    params:
      amount: float
      source: str (optional, for narrative)
    """
    amount = params.get("amount", 10000.0)
    p.checking_balance += amount
    return p


def _handle_medical_bill(
    p: BorrowerProfile, params: dict
) -> BorrowerProfile:
    """
    Medical bill: checking drops, possible new debt.
    params:
      amount: float (total bill)
      monthly_payment: float (optional payment plan)
    """
    amount = params.get("amount", 5000.0)
    monthly = params.get("monthly_payment", 0.0)
    p.checking_balance = max(
        0, p.checking_balance - amount
    )
    if monthly > 0:
        p.monthly_other_debt += monthly
    return p


def _handle_debt_payoff(
    p: BorrowerProfile, params: dict
) -> BorrowerProfile:
    """
    Generic debt payoff.
    params:
      debt_type: str (car/student/credit_card/other)
      amount: float (monthly reduction)
    """
    debt_type = params.get("debt_type", "other")
    amount = params.get("amount", 0.0)
    if debt_type == "car":
        p.monthly_car_payment = max(
            0, p.monthly_car_payment - amount
        )
    elif debt_type == "student":
        p.monthly_student_loan = max(
            0, p.monthly_student_loan - amount
        )
    elif debt_type == "credit_card":
        p.monthly_credit_card_min = max(
            0, p.monthly_credit_card_min - amount
        )
    else:
        p.monthly_other_debt = max(
            0, p.monthly_other_debt - amount
        )
    return p


def _handle_move(
    p: BorrowerProfile, params: dict
) -> BorrowerProfile:
    """
    Move: address changes, rent may change.
    params:
      new_monthly_rent: float (optional)
      new_city: str (optional)
      new_state: str (optional)
      new_zip: str (optional)
      new_street: str (optional)
    """
    if "new_monthly_rent" in params:
        p.monthly_rent_mortgage = params[
            "new_monthly_rent"
        ]
    if "new_city" in params:
        p.city = params["new_city"]
    if "new_state" in params:
        p.state = params["new_state"]
    if "new_zip" in params:
        p.zip_code = params["new_zip"]
    if "new_street" in params:
        p.street_name = params["new_street"]
    p.years_at_address = 0
    return p


def _handle_marriage(
    p: BorrowerProfile, params: dict
) -> BorrowerProfile:
    """
    Marriage: possible income change, last name change.
    params:
      spouse_income_added: float (optional)
      new_last_name: str (optional)
    """
    if "spouse_income_added" in params:
        p.annual_gross_income += params[
            "spouse_income_added"
        ]
    if "new_last_name" in params:
        p.last_name = params["new_last_name"]
    return p


def _handle_baby(
    p: BorrowerProfile, params: dict
) -> BorrowerProfile:
    """
    Baby: new recurring expense.
    params:
      monthly_childcare: float (default 1200)
    """
    childcare = params.get("monthly_childcare", 1200.0)
    p.monthly_other_debt += childcare
    return p


def _handle_divorce(
    p: BorrowerProfile, params: dict
) -> BorrowerProfile:
    """
    Divorce: income may split, support payments.
    params:
      income_reduction_pct: float (optional)
      monthly_support_payment: float (optional)
    """
    if "income_reduction_pct" in params:
        p.annual_gross_income *= (
            1 - params["income_reduction_pct"]
        )
    if "monthly_support_payment" in params:
        p.monthly_other_debt += params[
            "monthly_support_payment"
        ]
    return p


def _handle_home_purchase(
    p: BorrowerProfile, params: dict
) -> BorrowerProfile:
    """
    Home purchase: rent → mortgage, assets drop.
    params:
      monthly_mortgage: float
      down_payment: float
      property_value: float (optional)
    """
    mortgage = params.get("monthly_mortgage", 1800.0)
    down = params.get("down_payment", 0.0)
    p.monthly_rent_mortgage = mortgage
    p.checking_balance = max(
        0, p.checking_balance - down
    )
    if "property_value" in params:
        p.property_value = params["property_value"]
    return p


def _handle_refinance(
    p: BorrowerProfile, params: dict
) -> BorrowerProfile:
    """
    Refinance: monthly payment changes.
    params:
      new_monthly_payment: float
    """
    if "new_monthly_payment" in params:
        p.monthly_rent_mortgage = params[
            "new_monthly_payment"
        ]
    return p


def _handle_income_inflation(
    p: BorrowerProfile, params: dict
) -> BorrowerProfile:
    """
    FRAUD A3/A4: Application overstates income.

    Claim-side (see CLAIM_ONLY_EVENTS): this handler produces the figure the
    1003 states. The W-2, pay stubs and bank statements are rendered from the
    world state, which does not carry it — so the overstatement is detectable
    by comparing the application against the income documents.

    params:
      inflation_factor: float (e.g. 1.35 = 35% over)
    """
    factor = params.get("inflation_factor", 1.30)
    p.annual_gross_income *= factor
    return p


def _handle_undisclosed_debt(
    p: BorrowerProfile, params: dict
) -> BorrowerProfile:
    """
    FRAUD A3/A4: Hidden debt not on application.

    World-side (see HIDDEN_EVENTS): the payment is real, so it is applied to
    the world state and appears on the bank statements. The application is
    rendered from the claimed state, which omits it.

    params:
      hidden_monthly_payment: float
      description: str (what the payment is for)
    """
    hidden = params.get("hidden_monthly_payment", 600.0)
    p.monthly_other_debt += hidden
    return p


def _handle_employer_mismatch(
    p: BorrowerProfile, params: dict
) -> BorrowerProfile:
    """
    FRAUD A3/A4: W-2 employer differs from application.

    Claim-side: the false employer reaches the 1003 only. The W-2 and pay
    stubs keep the real one.

    params:
      false_employer: str (what application claims)
    """
    if "false_employer" in params:
        p.employer_name = params["false_employer"]
    return p


# ── Handler registry ──────────────────────────────────────

_EVENT_HANDLERS = {
    EventType.PROMOTION:       _handle_promotion,
    EventType.RAISE:           _handle_raise,
    EventType.JOB_CHANGE:      _handle_job_change,
    EventType.LAYOFF:          _handle_layoff,
    EventType.NEW_EMPLOYMENT:  _handle_new_employment,
    EventType.SELF_EMPLOYED:   _handle_new_employment,
    EventType.CAR_PURCHASE:    _handle_car_purchase,
    EventType.CAR_PAYOFF:      _handle_car_payoff,
    EventType.STUDENT_PAYOFF:  _handle_student_payoff,
    EventType.LARGE_DEPOSIT:   _handle_large_deposit,
    EventType.MEDICAL_BILL:    _handle_medical_bill,
    EventType.DEBT_PAYOFF:     _handle_debt_payoff,
    EventType.MOVE:            _handle_move,
    EventType.MARRIAGE:        _handle_marriage,
    EventType.BABY:            _handle_baby,
    EventType.DIVORCE:         _handle_divorce,
    EventType.HOME_PURCHASE:   _handle_home_purchase,
    EventType.REFINANCE:       _handle_refinance,
    EventType.INCOME_INFLATION:  _handle_income_inflation,
    EventType.UNDISCLOSED_DEBT:  _handle_undisclosed_debt,
    EventType.EMPLOYER_MISMATCH: _handle_employer_mismatch,
}


# ── BorrowerTimeline ──────────────────────────────────────

class BorrowerTimeline:
    """
    A sequence of life events applied to
    a starting BorrowerProfile.

    The timeline produces a financial state
    at any point in time by applying all
    events that occurred on or before
    that month.

    Key guarantee:
      state_at(month) is deterministic.
      Same timeline + same month = same state.
      No randomness after construction.

    Example:
      starting income: $72,000
      Month 3: PROMOTION (+20%) → $86,400
      Month 7: CAR_PURCHASE → new $449/mo debt
      Month 12: MOVE → rent $1,200 → $1,650
      Month 18: state_at(18) → full evolved profile
    """

    def __init__(
        self,
        profile: BorrowerProfile,
        months: int = 18,
        seed: int = None,
    ):
        """
        Args:
            profile: Starting financial state.
                     This profile represents month 0
                     (before any events).
            months: Length of the timeline in months.
                    Documents are generated at
                    the final month by default.
            seed: Optional seed for reproducibility.
                  If not provided uses profile.seed.
        """
        if months < 1:
            raise ValueError(
                f"months must be at least 1, got {months}"
            )
        self.starting_profile = copy.deepcopy(profile)
        self.months = months
        self.seed = seed if seed is not None else profile.seed
        self._events: List[LifeEvent] = []

    def add_event(self, event: LifeEvent) -> None:
        """Add a life event to the timeline."""
        if event.month < 1 or event.month > self.months:
            raise ValueError(
                f"Event month {event.month} out of "
                f"range 1-{self.months}"
            )
        self._events.append(event)
        # Keep events sorted by month. Stable, so two events in the same month
        # stay in the order they were added — which is the order they apply in.
        self._events.sort(key=lambda e: e.month)

    def _fold(self, month: int, skip) -> BorrowerProfile:
        """Apply every event up to `month` whose type is not in `skip`."""
        if month < 0 or month > self.months:
            raise ValueError(
                f"Month {month} out of range "
                f"0-{self.months}"
            )
        state = copy.deepcopy(self.starting_profile)
        for event in self.events:
            if event.month <= month and event.event_type not in skip:
                state = event.apply(state)
        return state

    def state_at(self, month: int) -> BorrowerProfile:
        """
        Return the borrower's financial state
        at the given month, with every event applied.

        Pure function — does not mutate anything.

        For a fraud timeline see world_state_at() and claimed_state_at(),
        which are what the documents are rendered from. Without a fraud event
        all three return the same values.
        """
        return self._fold(month, skip=frozenset())

    def world_state_at(self, month: int) -> BorrowerProfile:
        """What is actually true at `month` — claim-only events excluded."""
        return self._fold(month, skip=CLAIM_ONLY_EVENTS)

    def claimed_state_at(self, month: int) -> BorrowerProfile:
        """What the application states at `month` — hidden events excluded."""
        return self._fold(month, skip=HIDDEN_EVENTS)

    @property
    def events(self) -> List[LifeEvent]:
        """Events sorted by month."""
        return sorted(self._events, key=lambda e: e.month)

    @property
    def fraud_events(self) -> List[LifeEvent]:
        """Events that make this case misaligned."""
        return [e for e in self.events if e.is_fraud]

    @property
    def final_state(self) -> BorrowerProfile:
        """Financial state at end of timeline."""
        return self.state_at(self.months)

    @property
    def alignment_class(self) -> str:
        """A4 if any fraud event is present, else A0.

        A3 (material inconsistency without manipulation) is not distinguished
        yet: nothing in the event model separates an omission from an
        alteration, so claiming A3 would be a label the data does not support.
        """
        return "A4" if self.fraud_events else "A0"

    def narrative(self) -> List[dict]:
        """
        Human-readable timeline narrative.
        Each entry describes what changed
        and when.
        """
        entries = []
        prev_state = copy.deepcopy(self.starting_profile)

        entries.append({
            "month": 0,
            "event": "Timeline start",
            "description": (
                f"{self.starting_profile.full_name} "
                f"at {self.starting_profile.employer_name}. "
                f"Income: ${self.starting_profile.annual_gross_income:,.0f}. "
                f"DTI: {self.starting_profile.dti_ratio:.1%}."
            ),
            "financial_state": {
                "annual_income": round(
                    prev_state.annual_gross_income, 2
                ),
                "dti_ratio": round(
                    prev_state.dti_ratio, 4
                ),
                "monthly_debt": round(
                    prev_state.total_monthly_debt, 2
                ),
                "checking_balance": round(
                    prev_state.checking_balance, 2
                ),
            },
        })

        for event in self.events:
            new_state = event.apply(prev_state)

            # Compute what changed
            income_change = (
                new_state.annual_gross_income
                - prev_state.annual_gross_income
            )
            debt_change = (
                new_state.total_monthly_debt
                - prev_state.total_monthly_debt
            )
            dti_change = (
                new_state.dti_ratio
                - prev_state.dti_ratio
            )

            changes = []
            if abs(income_change) > 1:
                direction = "up" if income_change > 0 else "down"
                changes.append(
                    f"Income {direction} "
                    f"${abs(income_change):,.0f}/yr"
                )
            if abs(debt_change) > 1:
                direction = "up" if debt_change > 0 else "down"
                changes.append(
                    f"Monthly debt {direction} "
                    f"${abs(debt_change):,.0f}"
                )
            if abs(dti_change) > 0.001:
                direction = "up" if dti_change > 0 else "down"
                changes.append(
                    f"DTI {direction} "
                    f"{abs(dti_change):.1%}"
                )

            entries.append({
                "month": event.month,
                "event": event.event_type.value,
                "description": event.description,
                "changes": changes,
                "fraud_flag": event.fraud_flag,
                "financial_state": {
                    "annual_income": round(
                        new_state.annual_gross_income, 2
                    ),
                    "dti_ratio": round(
                        new_state.dti_ratio, 4
                    ),
                    "monthly_debt": round(
                        new_state.total_monthly_debt, 2
                    ),
                    "checking_balance": round(
                        new_state.checking_balance, 2
                    ),
                    "employer": new_state.employer_name,
                },
            })

            prev_state = new_state

        return entries

    def to_dict(self) -> dict:
        """Serialize timeline to dict for JSON export."""
        return {
            "seed": self.seed,
            "months": self.months,
            "generator_version": GENERATOR_VERSION,
            "borrower": self.starting_profile.full_name,
            "alignment_class": self.alignment_class,
            "starting_state": {
                "annual_income": round(
                    self.starting_profile.annual_gross_income,
                    2
                ),
                "employer": (
                    self.starting_profile.employer_name
                ),
                "dti_ratio": round(
                    self.starting_profile.dti_ratio, 4
                ),
            },
            "events": [e.to_dict() for e in self.events],
            "narrative": self.narrative(),
            "final_state": {
                "annual_income": round(
                    self.final_state.annual_gross_income,
                    2
                ),
                "employer": self.final_state.employer_name,
                "dti_ratio": round(
                    self.final_state.dti_ratio, 4
                ),
                "expected_decision": (
                    self.final_state.expected_decision
                ),
                "expected_decision_basis": (
                    "Scenario label carried from the starting profile. "
                    "It is not recomputed from the evolved state."
                ),
            },
        }


# ── Preset timelines ──────────────────────────────────────

def career_growth_timeline(
    profile: BorrowerProfile,
    months: int = 18,
) -> BorrowerTimeline:
    """
    A borrower who gets promoted, buys a car,
    and applies for a mortgage at peak earning.
    Classic approved case with rich history.
    """
    tl = BorrowerTimeline(profile, months)

    tl.add_event(LifeEvent(
        month=3,
        event_type=EventType.PROMOTION,
        description="Promoted to Senior Analyst",
        params={"income_increase_pct": 0.18},
    ))

    tl.add_event(LifeEvent(
        month=6,
        event_type=EventType.CAR_PURCHASE,
        description="Purchased used Honda Civic",
        params={
            "monthly_payment": 389.0,
            "down_payment": 2500.0,
        },
    ))

    tl.add_event(LifeEvent(
        month=12,
        event_type=EventType.RAISE,
        description="Annual performance raise",
        params={"income_increase_pct": 0.05},
    ))

    return tl


def financial_stress_timeline(
    profile: BorrowerProfile,
    months: int = 18,
) -> BorrowerTimeline:
    """
    A borrower who loses a job, recovers,
    but applies with elevated DTI.
    Classic flagged/manual review case.
    """
    tl = BorrowerTimeline(profile, months)

    tl.add_event(LifeEvent(
        month=2,
        event_type=EventType.LAYOFF,
        description="Position eliminated in restructuring",
        params={"unemployment_pct": 0.42},
    ))

    tl.add_event(LifeEvent(
        month=5,
        event_type=EventType.NEW_EMPLOYMENT,
        description="New position at competitor",
        params={
            "new_employer": "Summit Analytics Group",
            "new_annual_income": profile.annual_gross_income
            * 0.88,
        },
    ))

    tl.add_event(LifeEvent(
        month=9,
        event_type=EventType.MEDICAL_BILL,
        description="Emergency medical expense",
        params={
            "amount": 4200.0,
            "monthly_payment": 150.0,
        },
    ))

    return tl


def income_inflation_fraud_timeline(
    profile: BorrowerProfile,
    months: int = 18,
) -> BorrowerTimeline:
    """
    A borrower who inflates income on application.
    Classic A3/A4 fraud case.
    W-2 and bank deposits tell the true story.
    Application overstates by 30%.
    """
    tl = BorrowerTimeline(profile, months)

    tl.add_event(LifeEvent(
        month=12,
        event_type=EventType.LAYOFF,
        description="Laid off — income reduced",
        params={"unemployment_pct": 0.50},
    ))

    tl.add_event(LifeEvent(
        month=17,
        event_type=EventType.INCOME_INFLATION,
        description=(
            "Borrower overstated income on application "
            "to qualify for loan"
        ),
        params={"inflation_factor": 1.30},
        fraud_flag="income_inflation_30pct",
    ))

    return tl


PRESET_TIMELINES = {
    "career_growth": career_growth_timeline,
    "financial_stress": financial_stress_timeline,
    "fraud": income_inflation_fraud_timeline,
}


# ── TimelineCaseBundler ───────────────────────────────────

class TimelineCaseBundler:
    """
    Generates complete timeline cases:
      timeline.json — causal narrative
      documents/ — PDFs at application month
      truth/ — world truth + document truth
      evaluation/ — expected extractions,
                    alignment matrix,
                    causal evidence
      README.md — human-readable summary
    """

    def generate_timeline_case(
        self,
        timeline: BorrowerTimeline,
        output_dir: str,
        application_month: int = None,
        case_id: str = None,
    ) -> str:
        """
        Generate a complete timeline case folder.

        Args:
            timeline: BorrowerTimeline with events
            output_dir: Parent directory
            application_month: Month at which to
                render documents (default: last month)
            case_id: Folder name override
                     (default: timeline-{seed:06d})

        Returns:
            Path to generated case folder
        """
        from realitydb_docs.loan_app import LoanAppRenderer
        from realitydb_docs.packet import CaseBundler

        app_month = (
            timeline.months if application_month is None
            else application_month
        )
        world_profile = timeline.world_state_at(app_month)
        claimed_profile = timeline.claimed_state_at(app_month)

        cid = case_id or (
            f"timeline-{timeline.seed:06d}"
        )
        case_dir = os.path.join(output_dir, cid)
        docs_dir = os.path.join(case_dir, "documents")
        truth_dir = os.path.join(case_dir, "truth")
        eval_dir = os.path.join(case_dir, "evaluation")

        os.makedirs(docs_dir, exist_ok=True)
        os.makedirs(truth_dir, exist_ok=True)
        os.makedirs(eval_dir, exist_ok=True)

        # Documents come from the WORLD state: the W-2, the pay stubs and the
        # bank statements describe what actually happened.
        bundler = CaseBundler()
        doc_paths = bundler._render_documents(
            world_profile, docs_dir
        )

        # The application is re-rendered from the CLAIMED state when the two
        # differ, which is the whole content of a fraud case. Re-rendering
        # just the 1003 rather than duplicating the six-document filename
        # table keeps one definition of what a case contains, in packet.py.
        if timeline.fraud_events:
            doc_paths["loan_app_1003"] = LoanAppRenderer(
                claimed_profile
            ).render(
                os.path.join(docs_dir, "loan_app_1003.pdf")
            )

        # Write truth layers
        self._write_timeline_truth(
            timeline, world_profile, claimed_profile,
            truth_dir, doc_paths, app_month,
        )

        # Write evaluation layer
        self._write_timeline_evaluation(
            timeline, world_profile, claimed_profile,
            eval_dir, app_month,
        )

        # Write README
        self._write_timeline_readme(
            timeline, world_profile, claimed_profile,
            case_dir, cid, app_month,
        )

        return case_dir

    def _write_timeline_truth(
        self,
        timeline: BorrowerTimeline,
        world_profile: BorrowerProfile,
        claimed_profile: BorrowerProfile,
        truth_dir: str,
        doc_paths: dict,
        app_month: int,
    ) -> None:
        """Write truth layer for timeline case."""
        start = timeline.starting_profile
        final = world_profile

        # world_truth.json — what is ACTUALLY true
        world_truth = {
            "note": (
                "World truth represents the borrower's "
                "actual financial state based on their "
                "real life events. This is what a "
                "perfect underwriting system would know. "
                "Claim-side fraud events are excluded here "
                "and appear only in document_truth.json."
            ),
            "application_month": app_month,
            "starting_state": {
                "annual_income": round(
                    start.annual_gross_income, 2
                ),
                "employer": start.employer_name,
                "dti_ratio": round(start.dti_ratio, 4),
                "address": start.full_address,
            },
            "final_state": {
                "full_name": final.full_name,
                "annual_income": round(
                    final.annual_gross_income, 2
                ),
                "employer": final.employer_name,
                "job_title": final.job_title,
                "dti_ratio": round(final.dti_ratio, 4),
                "ltv_ratio": round(final.ltv_ratio, 4),
                "address": final.full_address,
                "checking_balance": round(
                    final.checking_balance, 2
                ),
                "total_monthly_debt": round(
                    final.total_monthly_debt, 2
                ),
            },
            "causal_chain": timeline.narrative(),
            "fraud_flags": [
                {
                    "month": e.month,
                    "type": e.fraud_flag,
                    "event": e.event_type.value,
                    "description": e.description,
                }
                for e in timeline.fraud_events
            ],
        }
        self._write_json(
            os.path.join(truth_dir, "world_truth.json"),
            world_truth
        )

        # document_truth.json — what documents CLAIM.
        #
        # The W-2, pay stub and bank blocks are read off the WORLD profile
        # because that is what those documents were rendered from; the loan
        # application block is read off the CLAIMED profile. In a case with no
        # fraud event the two profiles are equal and every block agrees.
        document_truth = {
            "note": (
                "Document truth represents what each "
                "document claims about the borrower. "
                "In fraud cases this differs from "
                "world truth — compare the loan_application "
                "block against w2_2024 and bank_statements."
            ),
            "w2_2024": {
                "employee_name": final.full_name,
                "employer_name": final.employer_name,
                "wages_box_1": round(
                    final.w2_box1_wages, 2
                ),
                "federal_withheld": round(
                    final.w2_box2_federal_withheld, 2
                ),
            },
            "loan_application": {
                "borrower_name": claimed_profile.full_name,
                "employer_name": claimed_profile.employer_name,
                "gross_monthly_income": round(
                    claimed_profile.monthly_gross_income, 2
                ),
                "total_monthly_debt": round(
                    claimed_profile.total_monthly_debt, 2
                ),
                "dti_declared": round(
                    claimed_profile.dti_ratio, 4
                ),
            },
            "bank_statements": {
                "account_holder": final.full_name,
                "avg_monthly_deposit": round(
                    final.monthly_gross_income, 2
                ),
                "recurring_car_payment": round(
                    final.monthly_car_payment, 2
                ),
                "recurring_student_loan": round(
                    final.monthly_student_loan, 2
                ),
            },
            "discrepancies": self._discrepancies(
                final, claimed_profile
            ),
        }
        self._write_json(
            os.path.join(
                truth_dir, "document_truth.json"
            ),
            document_truth
        )

        # timeline.json — the causal narrative
        self._write_json(
            os.path.join(truth_dir, "timeline.json"),
            timeline.to_dict()
        )

    @staticmethod
    def _discrepancies(
        world: BorrowerProfile,
        claimed: BorrowerProfile,
    ) -> list:
        """Where the application disagrees with the world.

        Computed by comparing the two profiles rather than restated from the
        event list, so a discrepancy cannot be claimed unless the documents
        actually carry it.
        """
        out = []
        if (
            abs(
                claimed.annual_gross_income
                - world.annual_gross_income
            ) > 1
        ):
            overstated = (
                claimed.annual_gross_income
                / world.annual_gross_income - 1
            )
            out.append({
                "field": "annual_income",
                "world": round(world.annual_gross_income, 2),
                "claimed_on_application": round(
                    claimed.annual_gross_income, 2
                ),
                "overstatement_pct": round(overstated * 100, 1),
                "detect_by": (
                    "Compare gross monthly income on the 1003 against "
                    "W-2 box 1 and the payroll deposits on the bank "
                    "statements."
                ),
            })
        if claimed.employer_name != world.employer_name:
            out.append({
                "field": "employer_name",
                "world": world.employer_name,
                "claimed_on_application": claimed.employer_name,
                "detect_by": (
                    "Compare the employer on the 1003 against the W-2 "
                    "and the pay stub banner."
                ),
            })
        if (
            abs(
                claimed.total_monthly_debt
                - world.total_monthly_debt
            ) > 1
        ):
            out.append({
                "field": "total_monthly_debt",
                "world": round(world.total_monthly_debt, 2),
                "claimed_on_application": round(
                    claimed.total_monthly_debt, 2
                ),
                "undisclosed_monthly": round(
                    world.total_monthly_debt
                    - claimed.total_monthly_debt, 2
                ),
                "detect_by": (
                    "Look for a recurring debit on the bank statements "
                    "that is not declared on the 1003."
                ),
            })
        return out

    def _write_timeline_evaluation(
        self,
        timeline: BorrowerTimeline,
        world_profile: BorrowerProfile,
        claimed_profile: BorrowerProfile,
        eval_dir: str,
        app_month: int,
    ) -> None:
        """Write evaluation layer."""

        fraud_events = timeline.fraud_events
        key_events = [
            e for e in timeline.events
            if e.event_type in (
                EventType.PROMOTION,
                EventType.LAYOFF,
                EventType.JOB_CHANGE,
                EventType.CAR_PURCHASE,
                EventType.MOVE,
            )
        ]
        # Concatenated, then de-duplicated by (month, type): an event that is
        # both key and fraudulent would otherwise be listed twice.
        causal_events = []
        seen = set()
        for e in key_events + fraud_events:
            key = (e.month, e.event_type)
            if key in seen:
                continue
            seen.add(key)
            causal_events.append(e)
        causal_events.sort(key=lambda e: e.month)

        def relevance(event: LifeEvent) -> str:
            if event.event_type in FRAUD_EVENTS:
                return "fraud"
            if event.event_type in (
                EventType.PROMOTION, EventType.RAISE,
                EventType.LAYOFF, EventType.JOB_CHANGE,
                EventType.NEW_EMPLOYMENT,
            ):
                return "income"
            if event.event_type in (
                EventType.CAR_PURCHASE, EventType.MEDICAL_BILL,
                EventType.BABY,
            ):
                return "debt"
            if event.event_type is EventType.LARGE_DEPOSIT:
                return "asset"
            if event.event_type in (
                EventType.MOVE, EventType.MARRIAGE,
            ):
                return "identity"
            return "other"

        def what_to_detect(event: LifeEvent) -> str:
            if event.event_type is EventType.INCOME_INFLATION:
                return (
                    "Income on the application does not match the W-2 "
                    "or the bank deposits"
                )
            if event.event_type is EventType.UNDISCLOSED_DEBT:
                return (
                    "Recurring payment visible on the bank statements "
                    "is not declared on the application"
                )
            if event.event_type is EventType.EMPLOYER_MISMATCH:
                return (
                    "Employer on the application does not match the "
                    "W-2 employer"
                )
            return "Anomaly labelled by the case author"

        causal_evidence = {
            "expected_decision": (
                world_profile.expected_decision
            ),
            "expected_decision_basis": (
                "Scenario label carried from the starting profile; not "
                "recomputed from the evolved state."
            ),
            "application_month": app_month,
            "alignment_class": timeline.alignment_class,
            "decision_factors": {
                "world_dti_ratio": round(
                    world_profile.dti_ratio, 4
                ),
                "declared_dti_ratio": round(
                    claimed_profile.dti_ratio, 4
                ),
                "ltv_ratio": round(
                    world_profile.ltv_ratio, 4
                ),
                "world_annual_income": round(
                    world_profile.annual_gross_income, 2
                ),
                "declared_annual_income": round(
                    claimed_profile.annual_gross_income, 2
                ),
            },
            "causal_events": [
                {
                    "month": e.month,
                    "event": e.event_type.value,
                    "description": e.description,
                    "relevance": relevance(e),
                }
                for e in causal_events
            ],
            "fraud_flags": [
                {
                    "flag": e.fraud_flag or e.event_type.value,
                    "month": e.month,
                    "description": e.description,
                    "what_to_detect": what_to_detect(e),
                }
                for e in fraud_events
            ],
        }
        self._write_json(
            os.path.join(
                eval_dir, "causal_evidence.json"
            ),
            causal_evidence
        )

        # expected_decision.json
        decision = {
            "expected_decision": (
                world_profile.expected_decision
            ),
            "expected_decision_basis": (
                "Scenario label carried from the starting profile; not "
                "recomputed from the evolved state."
            ),
            "dti_ratio": round(
                world_profile.dti_ratio, 4
            ),
            "declared_dti_ratio": round(
                claimed_profile.dti_ratio, 4
            ),
            "ltv_ratio": round(
                world_profile.ltv_ratio, 4
            ),
            "alignment_class": timeline.alignment_class,
            "fraud_present": len(fraud_events) > 0,
            "fraud_flags": [
                e.fraud_flag or e.event_type.value
                for e in fraud_events
            ],
            "rationale": (
                f"Final DTI {world_profile.dti_ratio:.1%} "
                f"after {len(timeline.events)} life events "
                f"over {timeline.months} months. "
                + (
                    f"Fraud present: "
                    f"{fraud_events[0].fraud_flag or fraud_events[0].event_type.value}"
                    if fraud_events else ""
                )
            ).strip(),
        }
        self._write_json(
            os.path.join(
                eval_dir, "expected_decision.json"
            ),
            decision
        )

    def _write_timeline_readme(
        self,
        timeline: BorrowerTimeline,
        world_profile: BorrowerProfile,
        claimed_profile: BorrowerProfile,
        case_dir: str,
        case_id: str,
        app_month: int,
    ) -> None:
        """Write human-readable README."""
        start = timeline.starting_profile
        fraud_events = timeline.fraud_events

        event_table = "\n".join([
            f"| Month {e.month:2d} "
            f"| {e.event_type.value:25s} "
            f"| {e.description[:50]:50s} |"
            for e in timeline.events
        ])

        if fraud_events:
            flag = (
                fraud_events[0].fraud_flag
                or fraud_events[0].event_type.value
            )
            fraud_cell = f"YES — {flag}"
            alignment_cell = "A4 — Probable Manipulation"
            discrepancy_section = "\n".join(
                f"- **{d['field']}**: world "
                f"{d['world']}, application "
                f"{d['claimed_on_application']}. {d['detect_by']}"
                for d in self._discrepancies(
                    world_profile, claimed_profile
                )
            ) or "- (none detected between the two profiles)"
        else:
            fraud_cell = "No"
            alignment_cell = "A0 — Perfectly Aligned"
            discrepancy_section = (
                "None. Every document is rendered from the same world "
                "state."
            )

        content = f"""# {case_id.upper()}

**RealityDB Financial Cases — Timeline Case**
{timeline.months}-month living financial profile
Generated by Mpingo Systems LLC | v{GENERATOR_VERSION}

---

## Borrower

| Field | Start | At Application |
|-------|-------|----------------|
| Name | {start.full_name} | {world_profile.full_name} |
| Employer | {start.employer_name} | {world_profile.employer_name} |
| Annual Income | ${start.annual_gross_income:,.0f} | ${world_profile.annual_gross_income:,.0f} |
| Monthly Debt | ${start.total_monthly_debt:,.0f} | ${world_profile.total_monthly_debt:,.0f} |
| DTI | {start.dti_ratio:.1%} | {world_profile.dti_ratio:.1%} |
| Checking | ${start.checking_balance:,.0f} | ${world_profile.checking_balance:,.0f} |

The "At Application" column is world truth — what is actually the case at
month {app_month}. What the application *states* may differ; see below.

---

## Timeline ({timeline.months} months)

| Month | Event | Description |
|-------|-------|-------------|
{event_table}

---

## Application (Month {app_month})

| Metric | Value |
|--------|-------|
| Loan Amount | ${world_profile.loan_amount:,.0f} |
| Property Value | ${world_profile.property_value:,.0f} |
| LTV | {world_profile.ltv_ratio:.1%} |
| DTI (world) | {world_profile.dti_ratio:.1%} |
| DTI (as declared) | {claimed_profile.dti_ratio:.1%} |
| Expected Decision | **{world_profile.expected_decision.upper()}** |
| Fraud Present | {fraud_cell} |
| Alignment Class | {alignment_cell} |

The expected decision is the scenario label this timeline started from. It is
not recomputed from the evolved state.

### Document discrepancies

{discrepancy_section}

---

## Files

| Layer | File | Contents |
|-------|------|----------|
| Documents | documents/ | 6 PDFs at month {app_month} |
| Truth | truth/world_truth.json | Actual financial state |
| Truth | truth/document_truth.json | What documents claim |
| Truth | truth/timeline.json | Full causal narrative |
| Evaluation | evaluation/causal_evidence.json | Event causality |
| Evaluation | evaluation/expected_decision.json | Decision + rationale |

---

© 2026 Mpingo Systems LLC | eddy@mpingo.ai
SYNTHETIC — NOT VALID
"""
        # encoding is explicit: this file carries em dashes and the copyright
        # sign, which cp1252 — the Windows default for open() — cannot encode.
        with open(
            os.path.join(case_dir, "README.md"),
            "w", encoding="utf-8", newline="\n",
        ) as f:
            f.write(content)

    @staticmethod
    def _write_json(path: str, data: dict) -> None:
        # Same reason as the README: default encoding on Windows is cp1252 and
        # these files carry an em dash.
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                data, f, indent=2, default=str, ensure_ascii=False
            )
            f.write("\n")


# ── Pack generation ───────────────────────────────────────

DEFAULT_TIMELINE_MIX = (
    ("career_growth", 0.4),
    ("financial_stress", 0.3),
    ("fraud", 0.3),
)

# Starting parameters per timeline type. Income and loan sizing mirror the
# three scenario tiers in config/scenarios.yaml.
TIMELINE_SCENARIO_PARAMS = {
    "career_growth": {
        "annual_income": 72000,
        "loan_amount": 320000,
        "property_value": 420000,
        "dti_target": 0.36,
        "scenario": "approved",
    },
    "financial_stress": {
        "annual_income": 74400,
        "loan_amount": 380000,
        "property_value": 460000,
        "dti_target": 0.45,
        "scenario": "flagged",
    },
    "fraud": {
        "annual_income": 57600,
        "loan_amount": 450000,
        "property_value": 500000,
        "dti_target": 0.55,
        "scenario": "rejected",
    },
}


def _timeline_mix(count: int) -> list:
    """Ordered list of timeline types, 40/30/30, remainder to the last tier."""
    types = []
    for name, share in DEFAULT_TIMELINE_MIX[:-1]:
        types.extend([name] * int(count * share))
    last = DEFAULT_TIMELINE_MIX[-1][0]
    types.extend([last] * (count - len(types)))
    return types[:count]


def generate_timeline_pack(
    count: int = 10,
    output_dir: str = "output",
    pack_name: str = "timeline_pack",
    seed_start: int = 1,
    months: int = 18,
    zip_output: bool = True,
) -> str:
    """
    Generate a pack of timeline cases.

    Default distribution:
      40% career growth (approved)
      30% financial stress (flagged)
      30% income inflation fraud (A4)

    Returns path to ZIP file (or the folder if zip_output is False).
    """
    if count < 1:
        raise ValueError(f"count must be at least 1, got {count}")

    gen = FinancialCaseGenerator()
    bundler = TimelineCaseBundler()

    cases_dir = os.path.join(
        output_dir, f"{pack_name}_cases"
    )

    # The staging directory is removed wholesale once the ZIP is written, so
    # it must not already hold anything — otherwise unrelated files would be
    # packed into a customer deliverable and then deleted. Same guard as
    # packet.generate_case_pack.
    if zip_output and os.path.isdir(cases_dir) and os.listdir(cases_dir):
        raise FileExistsError(
            f"staging directory is not empty: {cases_dir}\n"
            f"It is deleted after the ZIP is written, so it must be empty "
            f"or absent. Remove it or choose another --pack-name."
        )
    os.makedirs(cases_dir, exist_ok=True)

    timeline_types = _timeline_mix(count)

    print(f"\nGenerating {count} timeline cases...")
    print("-" * 50)

    summaries = []
    for i, tl_type in enumerate(timeline_types):
        seed = seed_start + i
        params = dict(TIMELINE_SCENARIO_PARAMS[tl_type])

        profile = gen.generate(seed=seed, **params)
        timeline = PRESET_TIMELINES[tl_type](profile, months)

        bundler.generate_timeline_case(
            timeline=timeline,
            output_dir=cases_dir,
            case_id=f"timeline-{seed:06d}",
        )

        world = timeline.world_state_at(months)
        summaries.append({
            "case_id": f"timeline-{seed:06d}",
            "timeline_type": tl_type,
            "borrower_name": world.full_name,
            "events": len(timeline.events),
            "world_dti_ratio": round(world.dti_ratio, 4),
            "alignment_class": timeline.alignment_class,
            "expected_decision": world.expected_decision,
        })

        print(
            f"  [{i+1:02d}/{count}] "
            f"timeline-{seed:06d} | "
            f"{tl_type:20s} | "
            f"{world.full_name:20s} | "
            f"DTI {world.dti_ratio:.1%} | "
            f"{timeline.alignment_class}"
        )

    TimelineCaseBundler._write_json(
        os.path.join(cases_dir, "PACK_MANIFEST.json"),
        {
            "pack_name": pack_name,
            "generator_version": GENERATOR_VERSION,
            "total_cases": count,
            "months_per_timeline": months,
            "seed_range": f"{seed_start}-{seed_start + count - 1}",
            "documents_per_case": 6,
            "mix": dict(DEFAULT_TIMELINE_MIX),
            "cases": summaries,
        },
    )

    if not zip_output:
        return cases_dir

    zip_name = f"{pack_name}_{count}cases.zip"
    zip_path = os.path.join(output_dir, zip_name)

    with zipfile.ZipFile(
        zip_path, "w", zipfile.ZIP_DEFLATED
    ) as zf:
        # Sorted, so the same pack produces a byte-comparable archive listing
        # rather than whatever order the filesystem returns.
        for root, dirs, files in os.walk(cases_dir):
            dirs.sort()
            for file in sorted(files):
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(
                    file_path, output_dir
                )
                zf.write(file_path, arcname)

    shutil.rmtree(cases_dir)

    size_mb = os.path.getsize(zip_path) / 1024 / 1024
    print(f"\nZIP: {zip_path} ({size_mb:.2f} MB)")

    return zip_path

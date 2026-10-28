"""Pydantic validation boundary for rows entering the persistence layer.

Cross-row checks (FK existence, non-overlapping assignments, and stage transitions)
are deliberately performed by PostgreSQL and the validation service, not individual
row models.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .enums import (ActivityOutcome, ActivityType, Industry, OpportunityStage,
                    ProductType, Region, RepRole, SnapshotStatus)
import re

Money = Annotated[Decimal, Field(max_digits=18, decimal_places=2, ge=0)]
ISO_CURRENCY = re.compile(r"^[A-Z]{3}$")


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Territory(ContractModel):
    territory_id: str = Field(pattern=r"^TER-\d{3}$")
    territory_name: str = Field(min_length=1, max_length=100)
    region: Region
    active_from: date
    active_to: Optional[date] = None

    @model_validator(mode="after")
    def valid_dates(self):
        if self.active_to and self.active_to < self.active_from:
            raise ValueError("active_to must not precede active_from")
        return self


class SalesRep(ContractModel):
    sales_rep_id: str = Field(pattern=r"^REP-\d{6}$")
    rep_name: str = Field(min_length=1, max_length=100)
    hire_date: date
    role: RepRole
    active_from: date
    active_to: Optional[date] = None

    @model_validator(mode="after")
    def valid_dates(self):
        if self.active_from < self.hire_date or (self.active_to and self.active_to < self.active_from):
            raise ValueError("invalid rep effective dates")
        return self


class RepTerritoryAssignment(ContractModel):
    assignment_id: str = Field(pattern=r"^RTA-REP-\d{6}-\d{3}$")
    sales_rep_id: str = Field(pattern=r"^REP-\d{6}$")
    territory_id: str = Field(pattern=r"^TER-\d{3}$")
    effective_from: date
    effective_to: Optional[date] = None

    @model_validator(mode="after")
    def valid_dates(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not precede effective_from")
        return self


class Account(ContractModel):
    account_id: str = Field(pattern=r"^ACC-\d{6}$")
    account_name: str = Field(min_length=1, max_length=200)
    territory_id: str = Field(pattern=r"^TER-\d{3}$")
    industry: Industry
    employee_count: int = Field(gt=0)
    active_from: date
    active_to: Optional[date] = None

    @model_validator(mode="after")
    def valid_dates(self):
        if self.active_to and self.active_to < self.active_from:
            raise ValueError("active_to must not precede active_from")
        return self


class Opportunity(ContractModel):
    opportunity_id: str = Field(pattern=r"^OPP-\d{4}-\d{6}$")
    account_id: str = Field(pattern=r"^ACC-\d{6}$")
    owner_rep_id: str = Field(pattern=r"^REP-\d{6}$")
    product_name: str = Field(min_length=1, max_length=100)
    product_type: ProductType
    created_at: datetime
    original_expected_close_date: date
    transaction_currency: str
    initial_amount: Money

    @field_validator("transaction_currency")
    @classmethod
    def iso_currency(cls, value: str) -> str:
        if not ISO_CURRENCY.fullmatch(value):
            raise ValueError("transaction_currency must be uppercase ISO-4217-style code")
        return value

    @model_validator(mode="after")
    def close_after_creation(self):
        if self.original_expected_close_date < self.created_at.date():
            raise ValueError("original expected close date must not precede creation")
        return self


class Stage(ContractModel):
    stage_code: OpportunityStage
    display_name: str = Field(min_length=1, max_length=50)
    stage_rank: int = Field(ge=1)
    is_terminal: bool

    @model_validator(mode="after")
    def terminal_stage_consistency(self):
        terminal = self.stage_code in {OpportunityStage.CLOSED_WON, OpportunityStage.CLOSED_LOST}
        if self.is_terminal != terminal:
            raise ValueError("only closed stages are terminal")
        return self


class StageHistory(ContractModel):
    stage_event_id: str = Field(pattern=r"^STG-OPP-\d{4}-\d{6}-\d{3}$")
    opportunity_id: str = Field(pattern=r"^OPP-\d{4}-\d{6}$")
    lifecycle_number: int = Field(ge=1)
    event_sequence: int = Field(ge=1)
    from_stage: Optional[OpportunityStage] = None
    to_stage: OpportunityStage
    occurred_at: datetime
    reason_code: str = Field(min_length=1, max_length=50)


class Activity(ContractModel):
    activity_id: str = Field(pattern=r"^ACT-OPP-\d{4}-\d{6}-\d{3}$")
    opportunity_id: str = Field(pattern=r"^OPP-\d{4}-\d{6}$")
    sales_rep_id: str = Field(pattern=r"^REP-\d{6}$")
    occurred_at: datetime
    activity_type: ActivityType
    outcome: ActivityOutcome
    duration_minutes: int = Field(ge=0, le=1440)


class Quota(ContractModel):
    quota_id: str = Field(pattern=r"^QUOTA-REP-\d{6}-\d{4}Q[1-4]$")
    sales_rep_id: str = Field(pattern=r"^REP-\d{6}$")
    fiscal_quarter: str = Field(pattern=r"^\d{4}Q[1-4]$")
    quota_amount: Money
    currency: str

    @field_validator("currency")
    @classmethod
    def iso_currency(cls, value: str) -> str:
        if not ISO_CURRENCY.fullmatch(value):
            raise ValueError("currency must be uppercase ISO-4217-style code")
        return value


class HistoricalBooking(ContractModel):
    booking_id: str = Field(pattern=r"^BKG-OPP-\d{4}-\d{6}-\d{3}$")
    opportunity_id: str = Field(pattern=r"^OPP-\d{4}-\d{6}$")
    recognized_at: datetime
    booking_amount: Money
    currency: str

    @field_validator("currency")
    @classmethod
    def iso_currency(cls, value: str) -> str:
        if not ISO_CURRENCY.fullmatch(value):
            raise ValueError("currency must be uppercase ISO-4217-style code")
        return value


class ForecastSnapshot(ContractModel):
    forecast_snapshot_id: str = Field(pattern=r"^FCST-\d{4}-\d{2}-\d{2}-\d{3}$")
    snapshot_at: datetime
    horizon_start: date
    horizon_end: date
    reporting_currency: str
    status: SnapshotStatus

    @model_validator(mode="after")
    def valid_horizon(self):
        if self.horizon_end < self.horizon_start:
            raise ValueError("horizon_end must not precede horizon_start")
        if not ISO_CURRENCY.fullmatch(self.reporting_currency):
            raise ValueError("reporting_currency must be uppercase ISO-4217-style code")
        return self


class StageProbabilityVersion(ContractModel):
    """Configured forecasting prior, never a realized historical conversion metric."""
    version_name: str = Field(min_length=1, max_length=100)
    stage_code: OpportunityStage
    scenario: str = Field(pattern=r"^(CONSERVATIVE|BASE|OPTIMISTIC)$")
    probability: Annotated[Decimal, Field(ge=0, le=1, max_digits=7, decimal_places=6)]
    effective_from: date
    effective_to: Optional[date] = None

    @model_validator(mode="after")
    def valid_dates(self):
        if self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to must not precede effective_from")
        return self

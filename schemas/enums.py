"""Shared, wire-safe enumerations for the sales forecasting data contract."""
from enum import Enum


class Region(str, Enum):
    NA = "NA"
    EMEA = "EMEA"
    APAC = "APAC"


class RepRole(str, Enum):
    ACCOUNT_EXECUTIVE = "ACCOUNT_EXECUTIVE"
    SALES_MANAGER = "SALES_MANAGER"


class Industry(str, Enum):
    TECHNOLOGY = "TECHNOLOGY"
    FINANCIAL_SERVICES = "FINANCIAL_SERVICES"
    HEALTHCARE = "HEALTHCARE"
    MANUFACTURING = "MANUFACTURING"
    RETAIL = "RETAIL"
    PROFESSIONAL_SERVICES = "PROFESSIONAL_SERVICES"


class ProductType(str, Enum):
    SUBSCRIPTION = "SUBSCRIPTION"
    SERVICES = "SERVICES"


class OpportunityStage(str, Enum):
    PROSPECTING = "PROSPECTING"
    QUALIFICATION = "QUALIFICATION"
    DISCOVERY = "DISCOVERY"
    PROPOSAL = "PROPOSAL"
    NEGOTIATION = "NEGOTIATION"
    CLOSED_WON = "CLOSED_WON"
    CLOSED_LOST = "CLOSED_LOST"


class ActivityType(str, Enum):
    CALL = "CALL"
    EMAIL = "EMAIL"
    MEETING = "MEETING"
    DEMO = "DEMO"
    TASK = "TASK"


class ActivityOutcome(str, Enum):
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"
    BOUNCED = "BOUNCED"
    CANCELLED = "CANCELLED"


class ForecastScenario(str, Enum):
    CONSERVATIVE = "CONSERVATIVE"
    BASE = "BASE"
    OPTIMISTIC = "OPTIMISTIC"


class SnapshotStatus(str, Enum):
    DRAFT = "DRAFT"
    FINALIZED = "FINALIZED"
    SUPERSEDED = "SUPERSEDED"

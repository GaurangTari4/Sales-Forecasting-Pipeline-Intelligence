"""Simulation engine. It uses one seeded Random instance, so row order is reproducible."""
from __future__ import annotations
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import math
import random
from .config import GeneratorConfig
from .constants import TERRITORIES, STAGES, STAGE_PRIORS, INDUSTRIES, PRODUCTS, FIRST, LAST

UTC = timezone.utc


def stamp(day: date, hour: int = 12) -> datetime:
    return datetime.combine(day, time(hour, tzinfo=UTC))


def quarter_label(day: date) -> str:
    return f"{day.year}Q{(day.month - 1) // 3 + 1}"


def quarter_end(day: date) -> date:
    month = ((day.month - 1) // 3 + 1) * 3
    next_month = date(day.year + (month == 12), 1 if month == 12 else month + 1, 1)
    return next_month - timedelta(days=1)


def sigmoid(value: float) -> float:
    return 1 / (1 + math.exp(-max(-15, min(15, value))))


class SalesDataGenerator:
    def __init__(self, config: GeneratorConfig):
        self.config = config
        self.rng = random.Random(config.seed)
        self.data: dict[str, list[dict]] = defaultdict(list)
        self.reps_by_territory: dict[str, list[str]] = defaultdict(list)
        self.outcome_truth: list[dict] = []

    def generate(self) -> dict[str, list[dict]]:
        self._masters()
        self._reps_and_assignments()
        self._accounts()
        self._opportunities_events_activities_bookings()
        self._quotas()
        self._snapshots()
        self.data["ground_truth_outcomes"] = self.outcome_truth
        # Baseline deliberately has no corrupt rows; this is an explicit protected label export.
        self.data["ground_truth_anomalies"] = []
        self.data["exchange_rates"] = [] if self.config.reporting_currency == "USD" else self._exchange_rates()
        return dict(self.data)

    def manifest(self) -> dict:
        return {"seed": self.config.seed, "config": {k: str(v) for k, v in asdict(self.config).items()},
                "baseline_valid": True, "anomaly_injection_rate": self.config.anomaly_injection_rate,
                "empty_table_columns": {"ground_truth_anomalies": ["anomaly_id", "entity_name", "entity_id", "rule_code", "injected", "detected_at", "severity"], "exchange_rates": ["rate_date", "from_currency", "to_currency", "rate", "source"]}}

    def _masters(self):
        for territory_id, name, region in TERRITORIES:
            self.data["territories"].append({"territory_id": territory_id, "territory_name": name, "region": region, "active_from": self.config.history_start, "active_to": None})
        for code, name, rank, terminal in STAGES:
            self.data["stages"].append({"stage_code": code, "display_name": name, "stage_rank": rank, "is_terminal": terminal})
            self.data["stage_probability_versions"].append({"stage_probability_version_id": len(self.data["stage_probability_versions"]) + 1, "version_name": "synthetic-v1", "stage_code": code, "scenario": "BASE", "probability": Decimal(str(STAGE_PRIORS[code])), "effective_from": self.config.history_start, "effective_to": None, "created_at": stamp(self.config.history_start)})

    def _reps_and_assignments(self):
        for number in range(1, self.config.reps + 1):
            rep_id = f"REP-{number:06d}"; territory = TERRITORIES[(number - 1) % len(TERRITORIES)][0]
            hire = self.config.history_start - timedelta(days=self.rng.randint(30, 1600))
            self.data["sales_reps"].append({"sales_rep_id": rep_id, "rep_name": f"{FIRST[number % len(FIRST)]} {LAST[(number * 3) % len(LAST)]}", "hire_date": hire, "role": "ACCOUNT_EXECUTIVE", "active_from": self.config.history_start, "active_to": None})
            transfer = number % 10 == 0
            if transfer:
                transfer_day = self.config.history_start + timedelta(days=self.rng.randint(120, max(121, (self.config.history_end-self.config.history_start).days - 120)))
                target = TERRITORIES[number % len(TERRITORIES)][0]
                self.data["rep_territory_assignments"].extend([
                    {"assignment_id": f"RTA-{rep_id}-001", "sales_rep_id": rep_id, "territory_id": territory, "effective_from": self.config.history_start, "effective_to": transfer_day - timedelta(days=1)},
                    {"assignment_id": f"RTA-{rep_id}-002", "sales_rep_id": rep_id, "territory_id": target, "effective_from": transfer_day, "effective_to": None},
                ])
            else:
                self.data["rep_territory_assignments"].append({"assignment_id": f"RTA-{rep_id}-001", "sales_rep_id": rep_id, "territory_id": territory, "effective_from": self.config.history_start, "effective_to": None})
            self.reps_by_territory[territory].append(rep_id)

    def _accounts(self):
        for number in range(1, self.config.accounts + 1):
            territory = TERRITORIES[(number * 5) % len(TERRITORIES)][0]
            self.data["accounts"].append({"account_id": f"ACC-{number:06d}", "account_name": f"{['Atlas','Beacon','Cobalt','Delta','Evergreen'][number % 5]} {number:06d}", "territory_id": territory, "industry": INDUSTRIES[number % len(INDUSTRIES)], "employee_count": 25 + (number * 137) % 50_000, "active_from": self.config.history_start, "active_to": None})

    def _opportunities_events_activities_bookings(self):
        total_days = (self.config.history_end - self.config.history_start).days
        for number in range(1, self.config.opportunities + 1):
            account = self.data["accounts"][(number * 17) % self.config.accounts]
            created = self.config.history_start + timedelta(days=self.rng.randrange(total_days + 1))
            opp_id = f"OPP-{created.year:04d}-{number:06d}"; owner = self.reps_by_territory[account["territory_id"]][number % len(self.reps_by_territory[account["territory_id"]])]
            product, product_type = PRODUCTS[number % len(PRODUCTS)]
            season = 1.22 if created.month in (9, 10, 11, 12) else .86 if created.month in (1, 2) else 1.0
            amount = Decimal(str(round(max(2500, self.rng.lognormvariate(10.35, .65) * season), 2))).quantize(Decimal(".01"))
            expected = created + timedelta(days=self.rng.randint(45, 180))
            self.data["opportunities"].append({"opportunity_id": opp_id, "account_id": account["account_id"], "owner_rep_id": owner, "product_name": product, "product_type": product_type, "created_at": stamp(created), "original_expected_close_date": expected, "transaction_currency": self.config.reporting_currency, "initial_amount": amount})
            self._simulate_lifecycle(opp_id, owner, created, expected, amount, account["industry"])

    def _simulate_lifecycle(self, opp_id, owner, created, expected, amount, industry):
        quality = self.rng.gauss(0, 1); urgency = self.rng.gauss(0, .7); activity_total = 0
        stages = ["PROSPECTING", "QUALIFICATION", "DISCOVERY", "PROPOSAL", "NEGOTIATION"]
        current_day, sequence, change_seq = created, 1, 1
        prior = None
        for index, stage in enumerate(stages):
            self.data["stage_history"].append({"stage_event_id": f"STG-{opp_id}-{sequence:03d}", "opportunity_id": opp_id, "lifecycle_number": 1, "event_sequence": sequence, "from_stage": prior, "to_stage": stage, "occurred_at": stamp(current_day), "reason_code": "CREATED" if not prior else "PROGRESSED"})
            sequence += 1; prior = stage
            dwell = self.rng.randint(9 + index * 3, 25 + index * 8)
            activities = max(0, int(self.rng.gauss(2 + index + max(quality, 0), 1.2)))
            for activity_no in range(activities):
                activity_day = current_day + timedelta(days=min(dwell - 1, 1 + activity_no * max(1, dwell // max(1, activities))))
                if activity_day > self.config.history_end: break
                activity_total += 1
                self.data["activities"].append({"activity_id": f"ACT-{opp_id}-{activity_total:03d}", "opportunity_id": opp_id, "sales_rep_id": owner, "occurred_at": stamp(activity_day, 10), "activity_type": ["CALL", "EMAIL", "MEETING", "DEMO"][activity_no % 4], "outcome": "COMPLETED", "duration_minutes": 15 + self.rng.randint(0, 6) * 15})
            decision_day = current_day + timedelta(days=dwell)
            if decision_day > self.config.history_end: break
            score = -0.55 + .70 * quality + .30 * urgency + .12 * activity_total - .12 * index - .000003 * float(amount) + (.2 if industry == "TECHNOLOGY" else 0)
            progress_probability = sigmoid(score)
            if self.rng.random() > progress_probability:
                self._terminal(opp_id, prior, sequence, decision_day, "CLOSED_LOST", quality, urgency, activity_total, score)
                return
            current_day = decision_day
            if current_day > expected and self.rng.random() < .55:
                new_expected = expected + timedelta(days=self.rng.randint(14, 60))
                self.data["opportunity_change_events"].append({"change_event_id": f"CHG-{opp_id}-{change_seq:03d}", "opportunity_id": opp_id, "occurred_at": stamp(current_day, 9), "change_type": "EXPECTED_CLOSE_DATE", "old_value": {"date": expected.isoformat()}, "new_value": {"date": new_expected.isoformat()}, "reason_code": "BUYER_DELAY"})
                change_seq += 1; expected = new_expected
        close_day = max(current_day + timedelta(days=self.rng.randint(3, 15)), expected)
        if close_day > self.config.history_end: return
        final_score = .25 + .8 * quality + .35 * urgency + .10 * activity_total - .000002 * float(amount)
        outcome = "CLOSED_WON" if self.rng.random() < sigmoid(final_score) else "CLOSED_LOST"
        self._terminal(opp_id, prior, sequence, close_day, outcome, quality, urgency, activity_total, final_score)
        if outcome == "CLOSED_WON":
            recognized = min(close_day + timedelta(days=self.rng.randint(0, 7)), self.config.history_end)
            self.data["historical_bookings"].append({"booking_id": f"BKG-{opp_id}-001", "opportunity_id": opp_id, "recognized_at": stamp(recognized), "booking_amount": amount, "currency": self.config.reporting_currency, "booking_type": "INITIAL"})

    def _terminal(self, opp_id, prior, sequence, day, outcome, quality, urgency, activities, score):
        self.data["stage_history"].append({"stage_event_id": f"STG-{opp_id}-{sequence:03d}", "opportunity_id": opp_id, "lifecycle_number": 1, "event_sequence": sequence, "from_stage": prior, "to_stage": outcome, "occurred_at": stamp(day), "reason_code": "SIMULATED_DECISION"})
        self.outcome_truth.append({"opportunity_id": opp_id, "final_outcome": outcome, "latent_quality": round(quality, 6), "buyer_urgency": round(urgency, 6), "activity_count_at_decision": activities, "decision_score": round(score, 6), "random_seed": self.config.seed})

    def _quotas(self):
        for rep in self.data["sales_reps"]:
            day = self.config.history_start
            while day <= self.config.history_end:
                q = quarter_label(day); territory_factor = 1 + (int(rep["sales_rep_id"][-2:]) % 6) * .04
                target = Decimal(str(round((180_000 + self.rng.randint(-30_000, 65_000)) * territory_factor, 2)))
                self.data["quotas"].append({"quota_id": f"QUOTA-{rep['sales_rep_id']}-{q}", "sales_rep_id": rep["sales_rep_id"], "fiscal_quarter": q, "quota_amount": target, "currency": self.config.reporting_currency})
                day = quarter_end(day) + timedelta(days=1)

    def _snapshots(self):
        for snapshot_day in self._snapshot_days():
            sid = f"FCST-{snapshot_day.isoformat()}-001"; horizon_start = snapshot_day + timedelta(days=1); horizon_end = quarter_end(horizon_start)
            self.data["forecast_snapshots"].append({"forecast_snapshot_id": sid, "snapshot_at": stamp(snapshot_day, 23), "horizon_start": horizon_start, "horizon_end": horizon_end, "reporting_currency": self.config.reporting_currency, "status": "FINALIZED", "created_at": stamp(snapshot_day, 23)})
            stage_by_opp = self._as_of(self.data["stage_history"], "occurred_at", snapshot_day, "opportunity_id")
            change_by_opp = self._as_of(self.data["opportunity_change_events"], "occurred_at", snapshot_day, "opportunity_id")
            for opp in self.data["opportunities"]:
                if opp["created_at"].date() > snapshot_day or opp["opportunity_id"] not in stage_by_opp: continue
                change = change_by_opp.get(opp["opportunity_id"]); close = date.fromisoformat(change["new_value"]["date"]) if change and change["change_type"] == "EXPECTED_CLOSE_DATE" else opp["original_expected_close_date"]
                self.data["snapshot_opportunities"].append({"forecast_snapshot_id": sid, "opportunity_id": opp["opportunity_id"], "stage_at_snapshot": stage_by_opp[opp["opportunity_id"]]["to_stage"], "amount_transaction_currency": opp["initial_amount"], "transaction_currency": opp["transaction_currency"], "expected_close_date": close})

    @staticmethod
    def _as_of(rows, timestamp_key, day, entity_key):
        cutoff = stamp(day, 23); result = {}
        for row in rows:
            # Input is append-only and stable; on equal timestamps, the later event is the effective state.
            if row[timestamp_key] <= cutoff and (entity_key not in result or row[timestamp_key] >= result[entity_key][timestamp_key]): result[row[entity_key]] = row
        return result

    def _snapshot_days(self):
        days, day = [], self.config.history_start
        while day <= self.config.history_end:
            end = quarter_end(day) if self.config.snapshot_frequency == "QUARTERLY" else (date(day.year + (day.month == 12), 1 if day.month == 12 else day.month + 1, 1) - timedelta(days=1))
            if self.config.history_start <= end <= self.config.history_end and end not in days: days.append(end)
            day = end + timedelta(days=1)
        return days

    def _exchange_rates(self):
        return []  # Reserved for a future multi-currency scenario; baseline uses reporting currency.

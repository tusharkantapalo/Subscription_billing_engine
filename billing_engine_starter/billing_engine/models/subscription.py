"""Subscription dataclass + status enum. ✅ COMPLETE."""

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional


class SubscriptionStatus(str, Enum):
    TRIAL = "TRIAL"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class Subscription:
    id: Optional[int]
    customer_id: int
    plan_id: int
    status: SubscriptionStatus
    current_period_start: date
    current_period_end: date     # exclusive: period covers [start, end)
    trial_end: Optional[date] = None
    discount_id: Optional[int] = None
    past_due_since: Optional[date] = None   # set when status moves to PAST_DUE

"""Plan dataclass + enums. ✅ COMPLETE."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PricingType(str, Enum):
    FLAT = "FLAT"
    TIERED = "TIERED"
    USAGE = "USAGE"
    FREEMIUM = "FREEMIUM"


class BillingPeriod(str, Enum):
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


@dataclass(frozen=True)
class Plan:
    id: Optional[int]
    name: str
    pricing_type: PricingType
    billing_period: BillingPeriod
    currency: str
    config_json: str = "{}"   # JSON blob of strategy-specific config

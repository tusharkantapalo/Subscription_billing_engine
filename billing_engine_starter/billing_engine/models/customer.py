"""Customer dataclass. ✅ COMPLETE."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class Customer:
    id: Optional[int]            # None before insert; set by DB after
    name: str
    email: str
    country_code: str            # "IN", "DE", "US", ...
    state_code: str = ""         # e.g. "MH" for Maharashtra; "" if N/A
    created_at: Optional[datetime] = None

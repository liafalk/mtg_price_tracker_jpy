"""
Assigns each set a freshness tier based on release recency, and picks
which sets to crawl on a given day.

    hot  -- released in the last 60 days -> crawl daily
    warm -- released in the last 365 days -> crawl on a rotating
            schedule, roughly once a week (1/7th of the warm pool/day)
    cold -- everything else -> crawl on a slow rotation,
            roughly once a month (1/30th of the cold pool/day)

This is intentionally simple: no ML, no per-card volatility detection.
See project notes for why -- it captures the large majority of real
price movement (new releases + actively-traded staples) for very
little engineering, and self-balances load across the week/month.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Set, Tier

HOT_WINDOW_DAYS = 60
WARM_WINDOW_DAYS = 365

WARM_ROTATION_DAYS = 7
COLD_ROTATION_DAYS = 30


def assign_tiers(session: Session, today: dt.date | None = None) -> None:
    """Recompute each set's tier from its release_date. Cheap; run daily
    before picking today's crawl list."""
    today = today or dt.date.today()

    sets = session.execute(select(Set)).scalars().all()
    for s in sets:
        if s.release_date is None:
            # Unknown release date (old/miscellaneous products) -> cold.
            s.tier = Tier.cold
            continue

        age_days = (today - s.release_date).days
        if age_days < 0:
            # Not yet released -- nothing to price yet.
            continue
        elif age_days <= HOT_WINDOW_DAYS:
            s.tier = Tier.hot
        elif age_days <= WARM_WINDOW_DAYS:
            s.tier = Tier.warm
        else:
            s.tier = Tier.cold

    session.commit()


def _rotation_bucket(set_id: int, num_buckets: int, today: dt.date) -> int:
    """Deterministic day-of-rotation bucket for a set, spread evenly.

    Using the set's own id (stable) mod num_buckets means the same set
    always falls on the same day-of-week/month, rather than reshuffling
    randomly every run.
    """
    day_index = today.toordinal()
    return (set_id + day_index) % num_buckets


def sets_to_crawl_today(session: Session, today: dt.date | None = None) -> list[Set]:
    """Returns the list of Set rows that should be crawled today."""
    today = today or dt.date.today()

    hot = session.execute(select(Set).where(Set.tier == Tier.hot)).scalars().all()

    warm_pool = session.execute(select(Set).where(Set.tier == Tier.warm)).scalars().all()
    warm_today = [
        s for s in warm_pool
        if _rotation_bucket(s.id, WARM_ROTATION_DAYS, today) == 0
    ]

    cold_pool = session.execute(select(Set).where(Set.tier == Tier.cold)).scalars().all()
    cold_today = [
        s for s in cold_pool
        if _rotation_bucket(s.id, COLD_ROTATION_DAYS, today) == 0
    ]

    return [*hot, *warm_today, *cold_today]

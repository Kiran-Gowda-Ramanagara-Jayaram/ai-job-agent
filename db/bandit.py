# db/bandit.py
from __future__ import annotations

import random
from datetime import datetime
from typing import List

from sqlalchemy import (
    Column, Integer, String, DateTime, create_engine, select
)
from sqlalchemy.orm import declarative_base, sessionmaker

# SQLite file next to the repo root (same style as crm.py)
ENGINE = create_engine("sqlite:///bandit.sqlite3", future=True)
Session = sessionmaker(bind=ENGINE, expire_on_commit=False, future=True)
Base = declarative_base()


class BanditStat(Base):
    __tablename__ = "bandit_stats"
    id        = Column(Integer, primary_key=True)
    bucket    = Column(String, index=True, nullable=False)   # e.g. "role:ml engineer|company:acme"
    template  = Column(String, index=True, nullable=False)   # e.g. "ai_value_prop_v1"
    success   = Column(Integer, default=0, nullable=False)
    fail      = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)


# ---------- helpers ----------
def _to_int(x) -> int:
    """Best-effort convert DB values to int (handles None and digit-like strings)."""
    if x is None:
        return 0
    if isinstance(x, int):
        return x
    if isinstance(x, float):
        return int(x)
    if isinstance(x, str):
        try:
            return int(x.strip() or "0")
        except ValueError:
            # If the string isn't a plain number, ignore and return 0
            return 0
    return 0


def init_bandit() -> None:
    """Create table and sanitize any bad rows (string counts -> ints)."""
    Base.metadata.create_all(ENGINE)
    with Session() as s:
        rows = s.execute(select(BanditStat)).scalars().all()
        changed = False
        for r in rows:
            # coerce to ints if they came back as strings
            new_succ = _to_int(r.success)
            new_fail = _to_int(r.fail)
            if (new_succ != r.success) or (new_fail != r.fail):
                r.success = new_succ
                r.fail = new_fail
                r.updated_at = datetime.utcnow()
                changed = True
        if changed:
            s.commit()


def reward_from_outcome(outcome: str) -> int:
    """
    Map an outcome to a binary reward for a Bernoulli bandit.
    Feel free to tune, but keep it {0,1} for the Beta model below.
    """
    outcome = (outcome or "").lower()
    if outcome in {"positive_reply", "interview"}:
        return 1
    # sent / no_reply / rejected -> 0
    return 0


def update_stat(bucket: str, template: str, reward: int) -> None:
    """Increment success/fail for a (bucket, template)."""
    with Session() as s:
        row = s.query(BanditStat).filter_by(bucket=bucket, template=template).first()
        if not row:
            row = BanditStat(bucket=bucket, template=template, success=0, fail=0)
            s.add(row)
            s.flush()
        # make sure we always treat the stored values as ints
        row.success = _to_int(row.success)
        row.fail = _to_int(row.fail)

        if int(reward) > 0:
            row.success += 1
        else:
            row.fail += 1
        row.updated_at = datetime.utcnow()
        s.commit()


def pick_template(bucket: str, templates: List[str]) -> str:
    """
    Thompson sampling (Beta-Bernoulli) to pick a template for a given bucket.
    Robust to bad DB types (coerces to ints).
    """
    if not templates:
        raise ValueError("templates list is empty")

    # Read stats for this bucket
    with Session() as s:
        stats = {t: {"success": 0, "fail": 0} for t in templates}
        rows = s.query(BanditStat).filter_by(bucket=bucket).all()
        for r in rows:
            t = r.template
            if t in stats:
                stats[t]["success"] += _to_int(r.success)
                stats[t]["fail"]    += _to_int(r.fail)

    # Thompson sampling with mild priors (Beta(0.5, 0.5))
    prior_success = 0.5
    prior_fail = 0.5
    best_t = templates[0]
    best_sample = -1.0

    for t in templates:
        succ = stats[t]["success"]
        fail = stats[t]["fail"]
        # draw a sample from Beta(succ+prior, fail+prior)
        sample = random.betavariate(prior_success + succ, prior_fail + fail)
        if sample > best_sample:
            best_sample = sample
            best_t = t

    return best_t

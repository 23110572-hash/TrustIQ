"""Generate realistic synthetic banking event data for demos and training.

Produces a labelled dataset of 10,000 events mixing normal users with four
attack archetypes: account-takeover, KYC-fraud, insider-threat and
account-recovery attacks. Output is a pandas DataFrame and/or CSV.
"""
from __future__ import annotations

import argparse
import logging
import os
from typing import List

import numpy as np
import pandas as pd

logger = logging.getLogger("trustiq.synthetic")

ACTIONS = ["login", "transfer", "otp", "profile_change", "account_recovery"]
CITIES = ["Mumbai", "Delhi", "Bengaluru", "Chennai", "Kolkata", "Pune"]
LABELS = ["normal", "account_takeover", "kyc_fraud", "insider_threat", "recovery_attack"]


def _normal_event(rng: np.random.Generator, user_id: str) -> dict:
    """Create a single normal-user event.

    Args:
        rng: Seeded random generator.
        user_id: The user identifier.

    Returns:
        A dict describing a normal event.
    """
    return {
        "user_id": user_id,
        "action": rng.choice(ACTIONS, p=[0.5, 0.2, 0.15, 0.1, 0.05]),
        "amount": float(max(0, rng.normal(4000, 1500))),
        "hour_of_day": int(rng.integers(8, 21)),
        "velocity_last_hour": int(rng.integers(0, 3)),
        "distance_from_home_km": float(abs(rng.normal(3, 2))),
        "device_id": f"dev_{user_id}",
        "is_new_device": False,
        "is_vpn_or_tor": False,
        "dwell_mean": float(rng.normal(100, 8)),
        "flight_mean": float(rng.normal(80, 8)),
        "label": "normal",
    }


def _account_takeover(rng: np.random.Generator, user_id: str) -> dict:
    """Create an account-takeover event (new device + location + odd amount)."""
    return {
        "user_id": user_id,
        "action": "transfer",
        "amount": float(max(0, rng.normal(80000, 20000))),
        "hour_of_day": int(rng.choice([2, 3, 4, 23])),
        "velocity_last_hour": int(rng.integers(4, 10)),
        "distance_from_home_km": float(rng.normal(800, 200)),
        "device_id": f"dev_attacker_{rng.integers(1000)}",
        "is_new_device": True,
        "is_vpn_or_tor": True,
        "dwell_mean": float(rng.normal(60, 20)),
        "flight_mean": float(rng.normal(140, 30)),
        "label": "account_takeover",
    }


def _kyc_fraud(rng: np.random.Generator, user_id: str, shared_device: str) -> dict:
    """Create a KYC-fraud event (multiple accounts from one device)."""
    return {
        "user_id": user_id,
        "action": "profile_change",
        "amount": 0.0,
        "hour_of_day": int(rng.integers(0, 24)),
        "velocity_last_hour": int(rng.integers(5, 15)),
        "distance_from_home_km": float(abs(rng.normal(10, 5))),
        "device_id": shared_device,
        "is_new_device": True,
        "is_vpn_or_tor": bool(rng.random() < 0.5),
        "dwell_mean": float(rng.normal(90, 15)),
        "flight_mean": float(rng.normal(85, 15)),
        "label": "kyc_fraud",
    }


def _insider_threat(rng: np.random.Generator, emp_id: str) -> dict:
    """Create an insider-threat event (bulk off-hours access)."""
    return {
        "user_id": emp_id,
        "action": "login",
        "amount": 0.0,
        "hour_of_day": int(rng.choice([0, 1, 2, 3, 23])),
        "velocity_last_hour": int(rng.integers(50, 250)),
        "distance_from_home_km": float(abs(rng.normal(5, 3))),
        "device_id": f"workstation_{rng.integers(50)}",
        "is_new_device": False,
        "is_vpn_or_tor": False,
        "dwell_mean": float(rng.normal(100, 10)),
        "flight_mean": float(rng.normal(80, 10)),
        "label": "insider_threat",
    }


def _recovery_attack(rng: np.random.Generator, user_id: str) -> dict:
    """Create an account-recovery attack event (failed liveness + new device)."""
    return {
        "user_id": user_id,
        "action": "account_recovery",
        "amount": 0.0,
        "hour_of_day": int(rng.integers(0, 24)),
        "velocity_last_hour": int(rng.integers(1, 5)),
        "distance_from_home_km": float(rng.normal(600, 150)),
        "device_id": f"dev_unknown_{rng.integers(1000)}",
        "is_new_device": True,
        "is_vpn_or_tor": bool(rng.random() < 0.6),
        "dwell_mean": float(rng.normal(70, 25)),
        "flight_mean": float(rng.normal(120, 30)),
        "label": "recovery_attack",
    }


def generate(n: int = 10000, seed: int = 42) -> pd.DataFrame:
    """Generate a labelled synthetic banking-event dataset.

    Args:
        n: Total number of events to generate.
        seed: Random seed for reproducibility.

    Returns:
        A pandas DataFrame of events with a ``label`` column.
    """
    rng = np.random.default_rng(seed)
    rows: List[dict] = []

    # Class proportions: mostly normal, with realistic minorities of attacks.
    proportions = {
        "normal": 0.85,
        "account_takeover": 0.05,
        "kyc_fraud": 0.04,
        "insider_threat": 0.03,
        "recovery_attack": 0.03,
    }
    shared_fraud_device = "dev_shared_fraud_001"

    for i in range(n):
        label = rng.choice(LABELS, p=[proportions[l] for l in LABELS])
        uid = f"user_{rng.integers(1, 2000):04d}"
        if label == "normal":
            rows.append(_normal_event(rng, uid))
        elif label == "account_takeover":
            rows.append(_account_takeover(rng, uid))
        elif label == "kyc_fraud":
            rows.append(_kyc_fraud(rng, f"applicant_{i}", shared_fraud_device))
        elif label == "insider_threat":
            rows.append(_insider_threat(rng, f"emp_{rng.integers(1, 200):03d}"))
        else:
            rows.append(_recovery_attack(rng, uid))

    df = pd.DataFrame(rows)
    logger.info("Generated %d events: %s", len(df), df["label"].value_counts().to_dict())
    return df


def main() -> None:
    """CLI entry point: generate data and write it to CSV."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Generate synthetic banking data")
    parser.add_argument("--n", type=int, default=10000, help="number of events")
    parser.add_argument("--out", default="ml/data/synthetic_events.csv")
    args = parser.parse_args()

    df = generate(args.n)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    df.to_csv(args.out, index=False)
    logger.info("Wrote %s", args.out)


if __name__ == "__main__":
    main()

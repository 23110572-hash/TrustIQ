"""Train an Isolation Forest on synthetic behavioural data.

Generates (or loads) labelled events, engineers features, trains an Isolation
Forest with contamination=0.05, evaluates precision/recall against the known
attack labels and persists the model to ``ml/models/anomaly_model.pkl``.
"""
from __future__ import annotations

import argparse
import logging
import os

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import precision_score, recall_score, f1_score

from feature_engineering import engineer, to_matrix
from synthetic_data import generate

logger = logging.getLogger("trustiq.train_anomaly")


def train(n: int = 10000, model_out: str = "ml/models/anomaly_model.pkl") -> dict:
    """Train and evaluate the Isolation Forest anomaly model.

    Args:
        n: Number of synthetic events to train on.
        model_out: Destination path for the persisted model.

    Returns:
        A dict of evaluation metrics (precision, recall, f1).
    """
    df = engineer(generate(n))
    X, y = to_matrix(df)

    model = IsolationForest(contamination=0.05, random_state=42, n_estimators=200)
    model.fit(X)

    # Isolation Forest predicts -1 (anomaly) / 1 (normal); map to 1/0.
    raw_pred = model.predict(X)
    y_pred = (raw_pred == -1).astype(int)

    metrics = {
        "precision": round(float(precision_score(y, y_pred, zero_division=0)), 3),
        "recall": round(float(recall_score(y, y_pred, zero_division=0)), 3),
        "f1": round(float(f1_score(y, y_pred, zero_division=0)), 3),
        "anomaly_rate": round(float(y_pred.mean()), 3),
    }
    logger.info("Isolation Forest metrics: %s", metrics)

    os.makedirs(os.path.dirname(model_out), exist_ok=True)
    joblib.dump(model, model_out)
    logger.info("Saved model -> %s", model_out)
    return metrics


def main() -> None:
    """CLI entry point for training the anomaly model."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Train Isolation Forest")
    parser.add_argument("--n", type=int, default=10000)
    parser.add_argument("--out", default="ml/models/anomaly_model.pkl")
    args = parser.parse_args()
    train(args.n, args.out)


if __name__ == "__main__":
    main()

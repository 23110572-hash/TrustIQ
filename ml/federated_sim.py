"""Simulated federated learning across bank branches.

Splits the synthetic dataset across 5 "branch" silos, trains a local logistic
model per branch *without sharing raw data*, aggregates the model weights using
FedAvg, and compares the federated model's accuracy against a centralised model
trained on all data. Demonstrates the privacy benefit of no raw-data exchange.
"""
from __future__ import annotations

import argparse
import logging
from typing import List, Tuple

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from feature_engineering import engineer, to_matrix
from synthetic_data import generate

logger = logging.getLogger("trustiq.federated")


def _train_local(X: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, float]:
    """Train a local logistic-regression model on one branch's data.

    Args:
        X: Branch feature matrix.
        y: Branch labels.

    Returns:
        A tuple ``(weights, bias)`` of the fitted model. Falls back to zeros if
        the branch happens to contain a single class.
    """
    if len(np.unique(y)) < 2:
        return np.zeros(X.shape[1]), 0.0
    clf = LogisticRegression(max_iter=200)
    clf.fit(X, y)
    return clf.coef_.ravel(), float(clf.intercept_[0])


def _fedavg(params: List[Tuple[np.ndarray, float]], sizes: List[int]):
    """Aggregate local model parameters using weighted FedAvg.

    Args:
        params: List of ``(weights, bias)`` tuples per branch.
        sizes: Number of samples per branch (aggregation weights).

    Returns:
        The aggregated ``(weights, bias)``.
    """
    total = sum(sizes)
    agg_w = np.zeros_like(params[0][0])
    agg_b = 0.0
    for (w, b), n in zip(params, sizes):
        agg_w += w * (n / total)
        agg_b += b * (n / total)
    return agg_w, agg_b


def _predict(weights: np.ndarray, bias: float, X: np.ndarray) -> np.ndarray:
    """Predict binary labels from logistic parameters.

    Args:
        weights: Model weight vector.
        bias: Model bias term.
        X: Feature matrix.

    Returns:
        Binary predictions (0/1).
    """
    logits = X @ weights + bias
    return (1.0 / (1.0 + np.exp(-logits)) >= 0.5).astype(int)


def run(num_branches: int = 5, n: int = 10000) -> dict:
    """Run the federated-vs-centralised comparison.

    Args:
        num_branches: Number of simulated branch silos.
        n: Total synthetic events to generate.

    Returns:
        A dict with federated and centralised accuracies.
    """
    df = engineer(generate(n))
    X, y = to_matrix(df)
    X = StandardScaler().fit_transform(X)

    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=42)

    # Partition the training data across branches (no cross-branch sharing).
    idx = np.array_split(np.arange(len(X_tr)), num_branches)
    local_params: List[Tuple[np.ndarray, float]] = []
    sizes: List[int] = []
    for b, branch_idx in enumerate(idx):
        w, bias = _train_local(X_tr[branch_idx], y_tr[branch_idx])
        local_params.append((w, bias))
        sizes.append(len(branch_idx))
        logger.info("Branch %d trained on %d samples (raw data kept local).", b + 1, len(branch_idx))

    fed_w, fed_b = _fedavg(local_params, sizes)
    fed_acc = accuracy_score(y_te, _predict(fed_w, fed_b, X_te))

    central = LogisticRegression(max_iter=200).fit(X_tr, y_tr)
    central_acc = accuracy_score(y_te, central.predict(X_te))

    result = {
        "federated_accuracy": round(float(fed_acc), 3),
        "centralised_accuracy": round(float(central_acc), 3),
        "branches": num_branches,
        "privacy_note": "No raw data left any branch; only model weights were aggregated.",
    }
    logger.info("Federated result: %s", result)
    return result


def main() -> None:
    """CLI entry point for the federated-learning simulation."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Federated learning simulation")
    parser.add_argument("--branches", type=int, default=5)
    parser.add_argument("--n", type=int, default=10000)
    args = parser.parse_args()
    result = run(args.branches, args.n)
    print("\n=== Federated vs Centralised ===")
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()

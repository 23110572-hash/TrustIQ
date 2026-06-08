"""Anomaly detection: Isolation Forest + LSTM.

* **Isolation Forest** detects point-anomalies in transaction context
  (amount, hour, frequency, geographic distance).
* **LSTM** (optional, PyTorch) detects *sequential* anomalies in a user's
  action flow; if PyTorch is unavailable a Markov-style fallback is used.

Both return an anomaly probability (0-1) plus the top contributing features.
"""
from __future__ import annotations

import logging
import os
from typing import Dict, List, Tuple

import numpy as np
from sklearn.ensemble import IsolationForest

from models import BankingEvent

logger = logging.getLogger("trustiq.anomaly")

# Optional PyTorch / saved LSTM ------------------------------------------------
try:
    import torch
    import torch.nn as nn

    _TORCH_AVAILABLE = True

    class SessionLSTM(nn.Module):
        """LSTM predicting the next session action from a sequence of actions.

        Architecture matches ``ml/train_lstm.py`` so saved weights load cleanly.
        """

        def __init__(self, num_actions: int = 5, embed: int = 16, hidden: int = 32):
            """Initialise the network.

            Args:
                num_actions: Number of distinct action classes.
                embed: Embedding dimension for actions.
                hidden: LSTM hidden units.
            """
            super().__init__()
            self.embedding = nn.Embedding(num_actions, embed)
            self.lstm = nn.LSTM(embed, hidden, batch_first=True)
            self.fc = nn.Linear(hidden, num_actions)

        def forward(self, x):  # noqa: D401 - torch forward
            """Run a forward pass returning per-action logits."""
            emb = self.embedding(x)
            out, _ = self.lstm(emb)
            return self.fc(out[:, -1, :])

except Exception:  # pragma: no cover
    _TORCH_AVAILABLE = False
    SessionLSTM = None  # type: ignore
    logger.warning("PyTorch unavailable - LSTM uses statistical fallback.")


class AnomalyDetector:
    """Combine Isolation Forest and an LSTM/sequence model for anomalies."""

    FEATURE_NAMES = [
        "amount",
        "hour_of_day",
        "velocity_last_hour",
        "distance_from_home_km",
    ]

    def __init__(
        self, model_path: str | None = None, lstm_path: str | None = None
    ) -> None:
        """Initialise detectors, loading saved models if present.

        Args:
            model_path: Optional path to a persisted Isolation Forest pickle.
            lstm_path: Optional path to persisted LSTM weights. The LSTM is only
                used for scoring when trained weights are successfully loaded;
                otherwise a deterministic statistical fallback is used.
        """
        self.iso_forest = IsolationForest(contamination=0.05, random_state=42)
        self._fit_default()
        self.lstm = SessionLSTM() if _TORCH_AVAILABLE else None
        self.lstm_trained = False
        self._maybe_load(model_path)
        self._maybe_load_lstm(lstm_path)

    def _fit_default(self) -> None:
        """Fit the Isolation Forest on synthetic 'normal' behaviour.

        The normal profile deliberately includes zero-amount events (logins,
        OTP, profile changes) alongside typical transfers so that a legitimate
        login is *not* treated as anomalous purely because it has no amount.
        """
        rng = np.random.default_rng(42)
        n = 3000
        # Half the events are zero-amount (non-transfer) actions.
        amounts = np.where(
            rng.random(n) < 0.5, 0.0, rng.normal(5000, 2500, n).clip(0)
        )
        normal = np.column_stack(
            [
                amounts,                                   # amount
                rng.uniform(6, 22, n),                     # hour (daytime span)
                rng.uniform(0, 4, n),                      # velocity
                rng.uniform(0, 15, n),                     # distance
            ]
        )
        self.iso_forest.fit(normal)
        # Cache the fitted normal statistics for feature attribution.
        self._means = normal.mean(axis=0)
        self._stds = normal.std(axis=0) + 1e-6

    def _maybe_load(self, model_path: str | None) -> None:
        """Load a persisted Isolation Forest model if the path exists.

        Args:
            model_path: Path to a joblib pickle, or None.
        """
        if model_path and os.path.exists(model_path):
            try:
                import joblib

                self.iso_forest = joblib.load(model_path)
                logger.info("Loaded Isolation Forest from %s", model_path)
            except Exception as exc:  # pragma: no cover
                logger.warning("Failed loading IF model: %s", exc)

    def _maybe_load_lstm(self, lstm_path: str | None) -> None:
        """Load persisted LSTM weights if available.

        Args:
            lstm_path: Path to a saved state-dict, or None.
        """
        if _TORCH_AVAILABLE and lstm_path and os.path.exists(lstm_path):
            try:
                self.lstm.load_state_dict(torch.load(lstm_path))  # type: ignore
                self.lstm.eval()  # type: ignore
                self.lstm_trained = True
                logger.info("Loaded trained LSTM from %s", lstm_path)
            except Exception as exc:  # pragma: no cover
                logger.warning("Failed loading LSTM: %s", exc)

    def _context_vector(self, event: BankingEvent) -> np.ndarray:
        """Extract the Isolation Forest input vector from an event.

        Args:
            event: The banking event.

        Returns:
            A 4-dimensional feature vector.
        """
        ctx = event.context
        return np.array(
            [
                ctx.amount,
                float(ctx.hour_of_day),
                float(ctx.velocity_last_hour),
                ctx.distance_from_home_km,
            ],
            dtype=float,
        )

    def detect(self, event: BankingEvent) -> Tuple[float, List[Dict[str, float]]]:
        """Run point-anomaly detection on a single event.

        Args:
            event: The banking event.

        Returns:
            A tuple ``(anomaly_probability, top_features)`` where the
            probability is 0-1 and ``top_features`` lists contributing factors.
        """
        vector = self._context_vector(event)
        # decision_function: higher = more normal, ~0 at the trained boundary.
        # Map through a sigmoid so typical events score near 0 and clear
        # outliers approach 1, with a gentle slope around the boundary.
        raw = self.iso_forest.decision_function([vector])[0]
        anomaly_prob = float(1.0 / (1.0 + np.exp(12.0 * (raw + 0.05))))
        anomaly_prob = float(np.clip(anomaly_prob, 0.0, 1.0))

        # Rank features by deviation from the fitted "normal" means.
        z = np.abs((vector - self._means) / self._stds)
        order = np.argsort(z)[::-1]
        top = [
            {"feature": self.FEATURE_NAMES[i], "deviation": float(round(z[i], 2))}
            for i in order[:3]
        ]
        logger.info("Anomaly prob=%.2f top=%s", anomaly_prob, top[0]["feature"])
        return anomaly_prob, top

    def sequence_anomaly(self, action_sequence: List[int]) -> float:
        """Score a sequence of encoded actions for sequential anomaly.

        Uses the LSTM only when *trained* weights are loaded; otherwise a
        transition-rarity heuristic that returns 0 for repetitive, predictable
        sequences (the common legitimate case).

        Args:
            action_sequence: A list of integer-encoded actions.

        Returns:
            An anomaly probability 0-1 (higher = more unusual flow).
        """
        if len(action_sequence) < 3:
            return 0.0

        if _TORCH_AVAILABLE and self.lstm is not None and self.lstm_trained:
            with torch.no_grad():
                seq = torch.tensor([action_sequence[:-1]], dtype=torch.long)
                logits = self.lstm(seq)
                probs = torch.softmax(logits, dim=-1).numpy().ravel()
                actual = action_sequence[-1] % len(probs)
                predicted_p = float(probs[actual])
                # Per the spec, only flag genuinely rare transitions: an action
                # the model assigns <5% probability. Common flows score ~0; the
                # rarer the action, the closer the score climbs toward 1.
                if predicted_p >= 0.05:
                    return 0.0
                return float(np.clip((0.05 - predicted_p) / 0.05, 0.0, 1.0))

        # Fallback: measure how often the most-recent transition has been seen
        # before in this session. Repeated/known transitions => low anomaly.
        transitions = list(zip(action_sequence[:-1], action_sequence[1:]))
        last = transitions[-1]
        seen = transitions[:-1].count(last)
        if seen > 0:
            return 0.0
        # An unseen final transition is mildly anomalous, scaled by variety.
        distinct_ratio = len(set(transitions)) / len(transitions)
        return float(np.clip(0.3 * distinct_ratio, 0.0, 0.5))

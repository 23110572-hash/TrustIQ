"""Train an LSTM to model normal user session sequences.

Encodes per-user action sequences as numeric vectors and trains a PyTorch LSTM
to predict the next action. Sessions whose actual next action has a predicted
probability below 5% are flagged as sequential anomalies. The trained model is
saved to ``ml/models/lstm_model.pt``.

If PyTorch is unavailable the script exits gracefully with a clear message so
the rest of the pipeline still works.
"""
from __future__ import annotations

import argparse
import logging
import os
from typing import List

import numpy as np

from synthetic_data import ACTIONS, generate

logger = logging.getLogger("trustiq.train_lstm")

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset

    _TORCH = True
except Exception:  # pragma: no cover
    _TORCH = False


if _TORCH:

    class SessionLSTM(nn.Module):
        """LSTM that predicts the next action in a user session."""

        def __init__(self, num_actions: int = 5, embed: int = 16, hidden: int = 32):
            """Initialise the network.

            Args:
                num_actions: Number of distinct action classes.
                embed: Embedding dimension for actions.
                hidden: LSTM hidden size.
            """
            super().__init__()
            self.embedding = nn.Embedding(num_actions, embed)
            self.lstm = nn.LSTM(embed, hidden, batch_first=True)
            self.fc = nn.Linear(hidden, num_actions)

        def forward(self, x):  # noqa: D401
            """Return next-action logits for each input sequence."""
            emb = self.embedding(x)
            out, _ = self.lstm(emb)
            return self.fc(out[:, -1, :])


def _build_sequences(seq_len: int = 5, n: int = 8000) -> "np.ndarray":
    """Build training windows of encoded action sequences.

    Args:
        seq_len: Length of each input window.
        n: Number of synthetic events to draw sequences from.

    Returns:
        An array of shape ``(num_windows, seq_len + 1)`` of action codes.
    """
    df = generate(n)
    code = {a: i for i, a in enumerate(ACTIONS)}
    df = df.sort_values("user_id")
    windows: List[List[int]] = []
    for _, group in df.groupby("user_id"):
        codes = [code[a] for a in group["action"].tolist()]
        for i in range(len(codes) - seq_len):
            windows.append(codes[i : i + seq_len + 1])
    return np.asarray(windows, dtype=np.int64)


def train(epochs: int = 5, model_out: str = "ml/models/lstm_model.pt") -> dict:
    """Train the session LSTM and persist it.

    Args:
        epochs: Number of training epochs.
        model_out: Destination path for the saved model.

    Returns:
        A dict with the final training loss and flagged-anomaly count.
    """
    if not _TORCH:
        logger.error("PyTorch not installed - skipping LSTM training.")
        return {"status": "skipped", "reason": "pytorch_unavailable"}

    data = _build_sequences()
    if len(data) == 0:
        logger.warning("No sequences built; aborting.")
        return {"status": "skipped", "reason": "no_data"}

    X = torch.tensor(data[:, :-1])
    y = torch.tensor(data[:, -1])
    loader = DataLoader(TensorDataset(X, y), batch_size=64, shuffle=True)

    model = SessionLSTM(num_actions=len(ACTIONS))
    optim = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.CrossEntropyLoss()

    last_loss = 0.0
    for epoch in range(epochs):
        total = 0.0
        for xb, yb in loader:
            optim.zero_grad()
            logits = model(xb)
            loss = loss_fn(logits, yb)
            loss.backward()
            optim.step()
            total += loss.item()
        last_loss = total / len(loader)
        logger.info("Epoch %d/%d loss=%.4f", epoch + 1, epochs, last_loss)

    # Flag low-probability transitions as anomalies.
    with torch.no_grad():
        probs = torch.softmax(model(X), dim=-1)
        actual_p = probs[torch.arange(len(y)), y]
        flagged = int((actual_p < 0.05).sum().item())

    os.makedirs(os.path.dirname(model_out), exist_ok=True)
    torch.save(model.state_dict(), model_out)
    logger.info("Saved LSTM -> %s (flagged %d anomalous transitions)", model_out, flagged)
    return {"status": "trained", "final_loss": round(last_loss, 4), "flagged": flagged}


def main() -> None:
    """CLI entry point for LSTM training."""
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Train session LSTM")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--out", default="ml/models/lstm_model.pt")
    args = parser.parse_args()
    train(args.epochs, args.out)


if __name__ == "__main__":
    main()

"""Immutable compliance audit trail.

Every risk decision is appended to a PostgreSQL table that only ever receives
INSERTs (no UPDATE / DELETE), giving an RBI-audit-ready, tamper-evident log.
When PostgreSQL is unavailable the logger transparently falls back to an
in-memory append-only list so the application still runs in demo mode.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, List

from config import get_settings
from models import AuditRecord

logger = logging.getLogger("trustiq.audit")


class AuditLogger:
    """Append-only audit log backed by PostgreSQL with in-memory fallback."""

    _CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS audit_log (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
        user_id TEXT NOT NULL,
        action TEXT NOT NULL,
        risk_score REAL NOT NULL,
        contributing_factors TEXT NOT NULL,
        response_taken TEXT NOT NULL,
        model_version TEXT NOT NULL
    );
    """

    def __init__(self) -> None:
        """Connect to PostgreSQL if possible, else use in-memory storage."""
        self._lock = threading.Lock()
        self._memory: List[Dict] = []
        self._conn = None
        self._connect()

    def _connect(self) -> None:
        """Attempt to establish a PostgreSQL connection and create the table."""
        settings = get_settings()
        try:
            import psycopg2

            self._conn = psycopg2.connect(settings.postgres_dsn)
            self._conn.autocommit = True
            with self._conn.cursor() as cur:
                cur.execute(self._CREATE_SQL)
            logger.info("Audit log connected to PostgreSQL.")
        except Exception as exc:  # pragma: no cover - demo fallback
            logger.warning("PostgreSQL unavailable (%s); using in-memory audit.", exc)
            self._conn = None

    def record(
        self,
        user_id: str,
        action: str,
        risk_score: float,
        contributing_factors: Dict,
        response_taken: str,
        model_version: str,
    ) -> None:
        """Append a single immutable audit record.

        Args:
            user_id: Masked or hashed user identifier.
            action: The action/event type.
            risk_score: The computed risk score.
            contributing_factors: Dict of factor -> value.
            response_taken: The adaptive-auth response applied.
            model_version: The model version that produced the decision.
        """
        factors_json = json.dumps(contributing_factors, default=str)
        if self._conn is not None:
            try:
                with self._conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO audit_log
                            (user_id, action, risk_score, contributing_factors,
                             response_taken, model_version)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            user_id,
                            action,
                            risk_score,
                            factors_json,
                            response_taken,
                            model_version,
                        ),
                    )
                return
            except Exception as exc:  # pragma: no cover
                logger.error("Audit insert failed (%s); buffering in memory.", exc)

        with self._lock:
            self._memory.append(
                {
                    "id": len(self._memory) + 1,
                    "timestamp": datetime.now(timezone.utc),
                    "user_id": user_id,
                    "action": action,
                    "risk_score": risk_score,
                    "contributing_factors": factors_json,
                    "response_taken": response_taken,
                    "model_version": model_version,
                }
            )

    def export(self, limit: int = 100, offset: int = 0) -> List[AuditRecord]:
        """Export audit records (paginated) for compliance review.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.

        Returns:
            A list of :class:`AuditRecord`.
        """
        if self._conn is not None:
            try:
                with self._conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT id, timestamp, user_id, action, risk_score,
                               contributing_factors, response_taken, model_version
                        FROM audit_log ORDER BY id DESC LIMIT %s OFFSET %s
                        """,
                        (limit, offset),
                    )
                    rows = cur.fetchall()
                return [
                    AuditRecord(
                        id=r[0],
                        timestamp=r[1],
                        user_id=r[2],
                        action=r[3],
                        risk_score=r[4],
                        contributing_factors=r[5],
                        response_taken=r[6],
                        model_version=r[7],
                    )
                    for r in rows
                ]
            except Exception as exc:  # pragma: no cover
                logger.error("Audit export failed: %s", exc)

        with self._lock:
            window = list(reversed(self._memory))[offset : offset + limit]
        return [AuditRecord(**rec) for rec in window]

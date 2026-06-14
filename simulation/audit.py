from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from simulation.models import SimulationRequest, SimulationResult


class AuditStore:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self):
        with self._connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS simulations (
                    sim_id TEXT PRIMARY KEY, requested_by TEXT, request_json TEXT NOT NULL,
                    result_json TEXT NOT NULL, graph_version TEXT NOT NULL,
                    telemetry_timestamp TEXT, telemetry_provenance TEXT NOT NULL,
                    allowed INTEGER NOT NULL, approval_status TEXT NOT NULL,
                    approved_by TEXT, approved_at TEXT, created_at TEXT NOT NULL,
                    execution_time_ms REAL NOT NULL, report_html TEXT
                )
            """)

    def save(self, request: SimulationRequest, result: SimulationResult, report_html: str | None = None):
        status = "PENDING" if result.allowed else "NOT_REQUIRED"
        with self._connect() as db:
            db.execute(
                """INSERT OR REPLACE INTO simulations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)""",
                (
                    result.sim_id, request.requested_by,
                    request.model_dump_json(), result.model_dump_json(),
                    result.graph_version,
                    result.telemetry_timestamp.isoformat() if result.telemetry_timestamp else None,
                    result.telemetry_provenance, int(result.allowed), status,
                    result.timestamp.isoformat(), result.execution_time_ms, report_html,
                ),
            )

    def get(self, sim_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM simulations WHERE sim_id = ?", (sim_id,)).fetchone()
        return _row(row)

    def list(self, limit: int = 50, offset: int = 0) -> list[dict]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM simulations ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (min(limit, 100), max(offset, 0)),
            ).fetchall()
        return [_row(row) for row in rows]

    def decide(self, sim_id: str, status: str, actor: str) -> dict | None:
        if status not in {"APPROVED", "REJECTED"}:
            raise ValueError("invalid approval status")
        with self._connect() as db:
            row = db.execute("SELECT approval_status FROM simulations WHERE sim_id = ?", (sim_id,)).fetchone()
            if not row:
                return None
            if row["approval_status"] != "PENDING":
                raise ValueError(f"cannot transition from {row['approval_status']}")
            db.execute(
                "UPDATE simulations SET approval_status=?, approved_by=?, approved_at=? WHERE sim_id=?",
                (status, actor, datetime.now(timezone.utc).isoformat(), sim_id),
            )
        return self.get(sim_id)


def _row(row):
    if row is None:
        return None
    value = dict(row)
    value["request"] = json.loads(value.pop("request_json"))
    value["result"] = json.loads(value.pop("result_json"))
    value["allowed"] = bool(value["allowed"])
    return value

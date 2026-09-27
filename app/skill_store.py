"""Auditable SQLite storage for simulation-skill candidates.

The store is deliberately internal-only.  It records evidence-bound candidates
but never decides that a skill is active; Q3/Q4 activation arrives with the
scenario physics gate in a later implementation package.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

SCHEMA_VERSION = 1
_LOCK = threading.Lock()
_QUALITY_LEVELS = {"Q0", "Q1", "Q2", "Q3", "Q4"}
_STATUSES = {"candidate", "active", "questioned", "retired"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise ValueError("structured value must be a JSON object")
    try:
        return json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("structured value must be finite JSON") from exc


class SkillStore:
    """Own a SQLite skill database at a server-selected path."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    @contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def migrate(self) -> None:
        """Create schema atomically; rerunning is safe."""
        with _LOCK, self._db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)")
            applied = {row[0] for row in db.execute("SELECT version FROM schema_migrations")}
            if 1 in applied:
                return
            db.executescript("""
                CREATE TABLE simulation_skills (
                    skill_id TEXT PRIMARY KEY,
                    scenario_type TEXT NOT NULL,
                    state_text TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('candidate','active','questioned','retired')),
                    quality_level TEXT NOT NULL CHECK(quality_level IN ('Q0','Q1','Q2','Q3','Q4')),
                    source_run_id TEXT NOT NULL,
                    validator_version TEXT NOT NULL,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE skill_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_id TEXT NOT NULL REFERENCES simulation_skills(skill_id),
                    version INTEGER NOT NULL,
                    normalized_params TEXT NOT NULL,
                    code_template TEXT NOT NULL,
                    code_hash TEXT NOT NULL,
                    postconditions TEXT NOT NULL,
                    physics_evidence TEXT NOT NULL,
                    source_run_id TEXT NOT NULL,
                    validator_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(skill_id, version)
                );
                CREATE TABLE skill_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    skill_id TEXT NOT NULL REFERENCES simulation_skills(skill_id),
                    event_type TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE skill_retrievals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT,
                    query_text TEXT NOT NULL,
                    candidates_json TEXT NOT NULL,
                    latency_ms REAL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX idx_skills_status ON simulation_skills(status, quality_level);
                CREATE INDEX idx_skill_versions_hash ON skill_versions(code_hash);
            """)
            db.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)", (1, _now()))

    def create_candidate(
        self,
        *,
        scenario_type: str,
        state_text: str,
        normalized_params: Mapping[str, Any],
        code_template: str,
        postconditions: Mapping[str, Any],
        physics_evidence: Mapping[str, Any],
        source_run_id: str,
        validator_version: str,
        quality_level: str,
    ) -> str:
        """Persist an evidence-bound candidate; callers cannot activate it here."""
        self.migrate()
        if not scenario_type.strip() or not state_text.strip() or not code_template.strip():
            raise ValueError("scenario_type, state_text, and code_template are required")
        if quality_level not in _QUALITY_LEVELS or quality_level in {"Q0", "Q1"}:
            raise ValueError("candidate requires quality level Q2 or higher")
        if not source_run_id.strip() or not validator_version.strip():
            raise ValueError("source_run_id and validator_version are required")
        skill_id, now = str(uuid.uuid4()), _now()
        code_hash = hashlib.sha256(code_template.encode("utf-8")).hexdigest()
        with self._db() as db:
            db.execute(
                "INSERT INTO simulation_skills VALUES (?, ?, ?, 'candidate', ?, ?, ?, 0, 0, ?, ?)",
                (skill_id, scenario_type.strip(), state_text.strip(), quality_level, source_run_id, validator_version, now, now),
            )
            db.execute(
                "INSERT INTO skill_versions(skill_id,version,normalized_params,code_template,code_hash,postconditions,physics_evidence,source_run_id,validator_version,created_at) VALUES (?,1,?,?,?,?,?,?,?,?)",
                (skill_id, _canonical_json(normalized_params), code_template, code_hash,
                 _canonical_json(postconditions), _canonical_json(physics_evidence), source_run_id, validator_version, now),
            )
            db.execute("INSERT INTO skill_events(skill_id,event_type,detail,created_at) VALUES (?, 'candidate_created', ?, ?)",
                       (skill_id, json.dumps({"quality_level": quality_level}), now))
        return skill_id

    def get_skill(self, skill_id: str) -> dict[str, Any] | None:
        self.migrate()
        with self._db() as db:
            row = db.execute("SELECT * FROM simulation_skills WHERE skill_id = ?", (skill_id,)).fetchone()
        return dict(row) if row else None

    def backup_to(self, destination: str | Path) -> None:
        """Create a consistent SQLite backup without mutating the source."""
        self.migrate()
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as source, sqlite3.connect(target) as destination_db:
            source.backup(destination_db)

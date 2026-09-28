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
SCENARIO_TYPES = {
    "point_source_2d", "point_source_3d", "plane_wave_2d", "initial_pressure_2d",
    "interface_2d", "attenuation_helmholtz_2d", "heterogeneous_2d",
}
_UNIT_KEYS = {
    "frequency_mhz": ("frequency_hz", 1_000_000.0),
    "source_frequency_mhz": ("frequency_hz", 1_000_000.0),
    "frequency_hz": ("frequency_hz", 1.0),
    "source_frequency": ("frequency_hz", 1.0),
    "dx_mm": ("dx_m", 0.001),
    "domain_dx_mm": ("dx_m", 0.001),
    "grid_step_mm": ("dx_m", 0.001),
    "dx_m": ("dx_m", 1.0),
    "domain_dx": ("dx_m", 1.0),
    "sound_speed_m_s": ("sound_speed_m_s", 1.0),
    "sound_speed": ("sound_speed_m_s", 1.0),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Mapping[str, Any]) -> str:
    if not isinstance(value, Mapping):
        raise ValueError("structured value must be a JSON object")
    try:
        return json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("structured value must be finite JSON") from exc


def normalize_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    """Return a canonical, unit-explicit parameter object without guessing units."""
    if not isinstance(parameters, Mapping) or not parameters:
        raise ValueError("parameters must be a non-empty JSON object")
    normalized: dict[str, Any] = {}
    for key, value in parameters.items():
        if key in _UNIT_KEYS:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{key} must be numeric")
            target, multiplier = _UNIT_KEYS[key]
            converted = float(value) * multiplier
            previous = normalized.get(target)
            if previous is not None and previous != converted:
                raise ValueError(f"conflicting values for {target}")
            normalized[target] = converted
        elif key in {"domain_N", "grid_size"}:
            values = value if isinstance(value, list) else [value]
            if not values or any(isinstance(v, bool) or not isinstance(v, int) or v <= 0 for v in values):
                raise ValueError(f"{key} must be positive integer dimensions")
            normalized["grid_shape"] = values
        elif key in {"solver_mode", "source_type", "medium_type", "has_sensor", "attenuation_db_cm_mhz"}:
            normalized[key] = value
        else:
            # Unknown fields are kept only when already unit-explicit or structural.
            if key.endswith(("_hz", "_m", "_s", "_pa", "_kg_m3")) or key in {"pml_size", "cfl", "dimensions"}:
                normalized[key] = value
            else:
                raise ValueError(f"unknown or unit-ambiguous parameter: {key}")
    _canonical_json(normalized)
    return normalized


def skill_fingerprint(scenario_type: str, normalized_params: Mapping[str, Any]) -> str:
    """Stable identity for one controlled scenario and its canonical parameters."""
    if scenario_type not in SCENARIO_TYPES:
        raise ValueError(f"unsupported scenario_type: {scenario_type}")
    material = _canonical_json({"scenario_type": scenario_type, "parameters": dict(normalized_params)})
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


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
            if 1 not in applied:
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
            if 2 not in applied:
                db.execute("ALTER TABLE simulation_skills ADD COLUMN fingerprint TEXT")
                db.execute("CREATE UNIQUE INDEX idx_skills_fingerprint ON simulation_skills(fingerprint)")
                db.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)", (2, _now()))

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
        if not state_text.strip() or not code_template.strip():
            raise ValueError("scenario_type, state_text, and code_template are required")
        if quality_level not in _QUALITY_LEVELS or quality_level in {"Q0", "Q1"}:
            raise ValueError("candidate requires quality level Q2 or higher")
        if not source_run_id.strip() or not validator_version.strip():
            raise ValueError("source_run_id and validator_version are required")
        normalized = normalize_parameters(normalized_params)
        fingerprint = skill_fingerprint(scenario_type, normalized)
        skill_id, now = str(uuid.uuid4()), _now()
        code_hash = hashlib.sha256(code_template.encode("utf-8")).hexdigest()
        # Serialize the read/decide/write sequence in this gateway process.
        # The unique fingerprint index remains the cross-process safety net.
        with _LOCK, self._db() as db:
            existing = db.execute("SELECT skill_id FROM simulation_skills WHERE fingerprint = ?", (fingerprint,)).fetchone()
            if existing:
                skill_id = existing["skill_id"]
                version = db.execute("SELECT COALESCE(MAX(version), 0) FROM skill_versions WHERE skill_id = ?", (skill_id,)).fetchone()[0]
                existing_hash = db.execute("SELECT code_hash FROM skill_versions WHERE skill_id = ? AND version = ?", (skill_id, version)).fetchone()[0]
                db.execute("UPDATE simulation_skills SET success_count = success_count + 1, updated_at = ? WHERE skill_id = ?", (now, skill_id))
                if existing_hash == code_hash:
                    db.execute("INSERT INTO skill_events(skill_id,event_type,detail,created_at) VALUES (?, 'candidate_observed', ?, ?)", (skill_id, json.dumps({"source_run_id": source_run_id}), now))
                    return skill_id
                next_version = version + 1
                db.execute(
                    "INSERT INTO skill_versions(skill_id,version,normalized_params,code_template,code_hash,postconditions,physics_evidence,source_run_id,validator_version,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (skill_id, next_version, _canonical_json(normalized), code_template, code_hash, _canonical_json(postconditions), _canonical_json(physics_evidence), source_run_id, validator_version, now),
                )
                db.execute("INSERT INTO skill_events(skill_id,event_type,detail,created_at) VALUES (?, 'candidate_versioned', ?, ?)", (skill_id, json.dumps({"version": next_version}), now))
                return skill_id
            db.execute(
                "INSERT INTO simulation_skills(skill_id,scenario_type,state_text,status,quality_level,source_run_id,validator_version,success_count,failure_count,created_at,updated_at,fingerprint) VALUES (?, ?, ?, 'candidate', ?, ?, ?, 1, 0, ?, ?, ?)",
                (skill_id, scenario_type, state_text.strip(), quality_level, source_run_id, validator_version, now, now, fingerprint),
            )
            db.execute(
                "INSERT INTO skill_versions(skill_id,version,normalized_params,code_template,code_hash,postconditions,physics_evidence,source_run_id,validator_version,created_at) VALUES (?,1,?,?,?,?,?,?,?,?)",
                (skill_id, _canonical_json(normalized), code_template, code_hash,
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

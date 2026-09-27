"""Isolated prototype for a quality-gated simulation skill store."""

from __future__ import annotations

import hashlib
import json
import math
import secrets
import sqlite3
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


MAX_PRESSURE_PA = 1_000_000_000.0
MIN_SIMILARITY = 0.5
MAX_PARAMETER_KEYS = 64
MAX_PARAMETER_ITEMS = 256
MAX_PARAMETER_DEPTH = 8
MAX_PARAMETER_STRING = 2048
MAX_PARAMETER_BYTES = 16_384
MAX_PARAMETER_NODES = 512
MAX_TEXT_FIELD = 20_000
MAX_SHAPE_DIMENSIONS = 8
MAX_RETRIEVAL_LIMIT = 50
SCHEMA_VERSION = 1
SUPPORTED_VERIFIER_VERSIONS = {"analyze_simulation_result.v1"}
_INIT_LOCK = threading.Lock()


@dataclass(frozen=True)
class ValidationEvidence:
    analysis_run_id: str
    verifier_version: str
    artifact_sha256: str
    verdict: str
    finite: bool
    has_signal: bool
    max_pressure_pa: float
    rms_pressure_pa: float
    field_shape: tuple[int, ...]
    summary: str


@dataclass(frozen=True)
class SkillCandidate:
    task_type: str
    parameters: Mapping[str, Any]
    summary: str
    code: str
    evidence: ValidationEvidence


@dataclass(frozen=True)
class QualityDecision:
    accepted: bool
    reason: str
    skill_id: int | None = None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_dumps(value: Any, *, allow_nan: bool) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=allow_nan,
    )


def _validate_json_value(
    value: Any,
    depth: int = 0,
    budget: list[int] | None = None,
) -> None:
    if budget is None:
        budget = [MAX_PARAMETER_NODES]
    budget[0] -= 1
    if budget[0] < 0:
        raise ValueError("parameter tree is too large")
    if depth > MAX_PARAMETER_DEPTH:
        raise ValueError("parameter nesting is too deep")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        if len(value) > MAX_PARAMETER_STRING:
            raise ValueError("parameter string is too long")
        return
    if isinstance(value, int):
        if abs(value).bit_length() > 128:
            raise ValueError("integer parameter is too large")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("parameter must be finite")
        return
    if isinstance(value, Mapping):
        if len(value) > MAX_PARAMETER_KEYS:
            raise ValueError("too many parameter keys")
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("parameter keys must be strings")
            _validate_json_value(item, depth + 1, budget)
        return
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_PARAMETER_ITEMS:
            raise ValueError("too many parameter items")
        for item in value:
            _validate_json_value(item, depth + 1, budget)
        return
    raise ValueError(f"unsupported parameter type: {type(value).__name__}")


def _canonical_parameters(parameters: Mapping[str, Any]) -> str:
    if not isinstance(parameters, Mapping) or not parameters:
        raise ValueError("parameters must be a non-empty mapping")
    _validate_json_value(parameters)
    value = _json_dumps(dict(parameters), allow_nan=False)
    if len(value.encode("utf-8")) > MAX_PARAMETER_BYTES:
        raise ValueError("serialized parameters are too large")
    return value


def _parameter_fingerprint(parameters_json: str) -> str:
    return _sha256_text(parameters_json)[:24]


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    if len(value) > MAX_TEXT_FIELD:
        raise ValueError(f"{field_name} is too long")
    return value


def _analysis_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    try:
        return float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{field_name} must be finite") from exc


def _evidence_payload(evidence: ValidationEvidence) -> dict[str, Any]:
    return {
        "analysis_run_id": evidence.analysis_run_id,
        "verifier_version": evidence.verifier_version,
        "verdict": evidence.verdict,
        "finite": evidence.finite,
        "has_signal": evidence.has_signal,
        "max_pressure_pa": evidence.max_pressure_pa,
        "rms_pressure_pa": evidence.rms_pressure_pa,
        "field_shape": list(evidence.field_shape),
        "summary": evidence.summary,
    }


def _evidence_artifact_hash(evidence: ValidationEvidence) -> str:
    return _sha256_text(
        _json_dumps(_evidence_payload(evidence), allow_nan=True)
    )


def _validate_evidence(evidence: Any) -> str | None:
    if not isinstance(evidence, ValidationEvidence):
        return "invalid_evidence"
    if not isinstance(evidence.finite, bool):
        return "invalid_evidence"
    if not isinstance(evidence.has_signal, bool):
        return "invalid_evidence"
    if not isinstance(evidence.verdict, str) or not evidence.verdict:
        return "invalid_evidence"
    if evidence.verifier_version not in SUPPORTED_VERIFIER_VERSIONS:
        return "invalid_evidence"
    if not isinstance(evidence.field_shape, (tuple, list)):
        return "invalid_evidence"
    if len(evidence.field_shape) > MAX_SHAPE_DIMENSIONS:
        return "invalid_evidence"
    if any(
        isinstance(item, bool)
        or not isinstance(item, int)
        or item < 0
        or item > MAX_PRESSURE_PA
        for item in evidence.field_shape
    ):
        return "invalid_evidence"
    for value, field_name in (
        (evidence.analysis_run_id, "analysis_run_id"),
        (evidence.verifier_version, "verifier_version"),
        (evidence.summary, "summary"),
    ):
        try:
            _required_text(value, field_name)
        except ValueError:
            return "invalid_evidence"
    if (
        not isinstance(evidence.artifact_sha256, str)
        or len(evidence.artifact_sha256) != 64
        or any(char not in "0123456789abcdef" for char in evidence.artifact_sha256)
    ):
        return "invalid_evidence_hash"
    try:
        expected_hash = _evidence_artifact_hash(evidence)
    except (TypeError, ValueError, OverflowError, RecursionError):
        return "invalid_evidence"
    if not secrets.compare_digest(expected_hash, evidence.artifact_sha256):
        return "invalid_evidence_hash"
    return None


def evidence_from_analysis_result(
    result: Mapping[str, Any],
    analysis_run_id: str,
    verifier_version: str,
) -> ValidationEvidence:
    """Build typed evidence from analyze_simulation_result output."""
    if not isinstance(result, Mapping):
        raise ValueError("result must be a mapping")

    run_id = _required_text(analysis_run_id, "analysis_run_id")
    verifier = _required_text(verifier_version, "verifier_version")
    if verifier not in SUPPORTED_VERIFIER_VERSIONS:
        raise ValueError("unsupported verifier_version")
    summary = _required_text(result.get("summary"), "summary")
    verdict = result.get("verdict")
    if not isinstance(verdict, str) or not verdict:
        raise ValueError("verdict must be a non-empty string")

    max_pressure = _analysis_number(result.get("max_pressure"), "max_pressure")
    rms_pressure = _analysis_number(result.get("rms_pressure"), "rms_pressure")
    raw_shape = result.get("field_shape", [])
    if not isinstance(raw_shape, (list, tuple)):
        raise ValueError("field_shape must be a sequence")
    try:
        field_shape = tuple(int(item) for item in raw_shape)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("field_shape must contain integers") from exc
    if any(item < 0 for item in field_shape):
        raise ValueError("field_shape cannot contain negative values")

    finite = math.isfinite(max_pressure) and math.isfinite(rms_pressure)
    has_signal = result.get("has_signal") is True
    evidence = ValidationEvidence(
        analysis_run_id=run_id,
        verifier_version=verifier,
        artifact_sha256="",
        verdict=verdict,
        finite=finite,
        has_signal=has_signal,
        max_pressure_pa=max_pressure,
        rms_pressure_pa=rms_pressure,
        field_shape=field_shape,
        summary=summary,
    )
    return _with_evidence_hash(evidence)


def _with_evidence_hash(evidence: ValidationEvidence) -> ValidationEvidence:
    return replace(
        evidence,
        artifact_sha256=_evidence_artifact_hash(evidence),
    )


def evaluate_quality(candidate: SkillCandidate) -> str | None:
    """Return a rejection reason, or None when every gate passes."""
    if not isinstance(candidate.task_type, str) or not candidate.task_type.strip():
        return "missing_task_type"
    if not isinstance(candidate.summary, str):
        return "invalid_summary"
    if not candidate.summary.strip():
        return "invalid_summary"
    if not isinstance(candidate.code, str) or not candidate.code.strip():
        return "missing_code"
    if len(candidate.code) > MAX_TEXT_FIELD:
        return "code_too_long"
    evidence_rejection = _validate_evidence(candidate.evidence)
    if evidence_rejection is not None:
        return evidence_rejection

    evidence = candidate.evidence
    if evidence.verdict != "normal":
        return "verdict_not_normal"

    max_pressure = _finite_number(evidence.max_pressure_pa)
    if max_pressure is None:
        return "max_pressure_not_finite"
    rms_pressure = _finite_number(evidence.rms_pressure_pa)
    if rms_pressure is None:
        return "rms_pressure_not_finite"
    if evidence.finite is not True:
        return "non_finite_field"
    if evidence.has_signal is not True:
        return "no_signal"
    if max_pressure <= 0:
        return "max_pressure_not_positive"
    if max_pressure > MAX_PRESSURE_PA:
        return "max_pressure_above_limit"
    if rms_pressure < 0:
        return "rms_pressure_negative"
    if rms_pressure > max_pressure:
        return "rms_exceeds_max"

    try:
        _canonical_parameters(candidate.parameters)
    except (TypeError, ValueError, OverflowError, RecursionError):
        return "invalid_parameters"
    return None


def _parameter_similarity(left: Any, right: Any) -> float:
    left_number = _finite_number(left)
    right_number = _finite_number(right)
    if left_number is not None and right_number is not None:
        denominator = abs(left_number) + abs(right_number)
        if denominator == 0:
            return 1.0
        return 1.0 / (1.0 + abs(left_number - right_number) / denominator)
    return 1.0 if left == right else 0.0


def _similarity_score(
    query_parameters: Mapping[str, Any],
    stored_parameters: Mapping[str, Any],
) -> float:
    query_keys = set(query_parameters)
    stored_keys = set(stored_parameters)
    common_keys = query_keys & stored_keys
    if not common_keys:
        return 0.0

    union_keys = query_keys | stored_keys
    mean_similarity = sum(
        _parameter_similarity(query_parameters[key], stored_parameters[key])
        for key in common_keys
    ) / len(common_keys)
    coverage = len(common_keys) / len(union_keys)
    return 0.6 * mean_similarity + 0.4 * coverage


def _evidence_dict(evidence: ValidationEvidence) -> dict[str, Any]:
    return {
        "analysis_run_id": evidence.analysis_run_id,
        "verifier_version": evidence.verifier_version,
        "artifact_sha256": evidence.artifact_sha256,
        "verdict": evidence.verdict,
        "finite": evidence.finite,
        "has_signal": evidence.has_signal,
        "max_pressure_pa": evidence.max_pressure_pa,
        "rms_pressure_pa": evidence.rms_pressure_pa,
        "field_shape": list(evidence.field_shape),
        "summary": evidence.summary,
    }


class SkillStore:
    """SQLite-backed prototype with immutable versions and a latest head."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with _INIT_LOCK:
            with self._connect() as connection:
                version = int(
                    connection.execute("PRAGMA user_version").fetchone()[0]
                )
                if version not in (0, SCHEMA_VERSION):
                    raise RuntimeError(
                        f"unsupported schema version: {version}"
                    )
                if version == SCHEMA_VERSION:
                    return

                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS simulation_skill_versions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_type TEXT NOT NULL
                            CHECK (
                                length(trim(task_type)) > 0
                                AND length(task_type) <= 200
                            ),
                        parameter_fingerprint TEXT NOT NULL
                            CHECK (
                                length(parameter_fingerprint) = 24
                                AND parameter_fingerprint
                                    NOT GLOB '*[^0-9a-f]*'
                            ),
                        parameters_json TEXT NOT NULL
                            CHECK (
                                json_valid(parameters_json)
                                AND json_type(parameters_json) = 'object'
                                AND length(parameters_json) <= 16384
                            ),
                        summary TEXT NOT NULL
                            CHECK (
                                length(trim(summary)) > 0
                                AND length(summary) <= 20000
                            ),
                        code TEXT NOT NULL
                            CHECK (
                                length(trim(code)) > 0
                                AND length(code) <= 20000
                            ),
                        code_sha256 TEXT NOT NULL
                            CHECK (
                                length(code_sha256) = 64
                                AND code_sha256 NOT GLOB '*[^0-9a-f]*'
                            ),
                        verdict TEXT NOT NULL CHECK (verdict = 'normal'),
                        finite INTEGER NOT NULL CHECK (finite = 1),
                        has_signal INTEGER NOT NULL CHECK (has_signal = 1),
                        max_pressure_pa REAL NOT NULL
                            CHECK (
                                max_pressure_pa > 0
                                AND max_pressure_pa <= 1000000000.0
                            ),
                        rms_pressure_pa REAL NOT NULL
                            CHECK (
                                rms_pressure_pa >= 0
                                AND rms_pressure_pa <= max_pressure_pa
                            ),
                        evidence_reference TEXT NOT NULL
                            CHECK (length(trim(evidence_reference)) > 0),
                        evidence_json TEXT NOT NULL
                            CHECK (
                                json_valid(evidence_json)
                                AND json_type(evidence_json) = 'object'
                            ),
                        evidence_sha256 TEXT NOT NULL
                            CHECK (
                                length(evidence_sha256) = 64
                                AND evidence_sha256 NOT GLOB '*[^0-9a-f]*'
                            ),
                        hit_count INTEGER NOT NULL DEFAULT 0
                            CHECK (hit_count >= 0),
                        success_count INTEGER NOT NULL DEFAULT 0
                            CHECK (
                                success_count >= 0
                                AND success_count <= hit_count
                            ),
                        created_at TEXT NOT NULL
                            CHECK (length(trim(created_at)) > 0),
                        UNIQUE (
                            task_type,
                            parameter_fingerprint,
                            code_sha256,
                            evidence_sha256
                        )
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS simulation_skill_heads (
                        task_type TEXT NOT NULL,
                        parameter_fingerprint TEXT NOT NULL,
                        version_id INTEGER NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (task_type, parameter_fingerprint),
                        FOREIGN KEY (version_id)
                            REFERENCES simulation_skill_versions(id)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS simulation_retrieval_tokens (
                        token_hash TEXT PRIMARY KEY
                            CHECK (
                                length(token_hash) = 64
                                AND token_hash NOT GLOB '*[^0-9a-f]*'
                            ),
                        skill_id INTEGER NOT NULL,
                        issued_at TEXT NOT NULL,
                        used INTEGER NOT NULL DEFAULT 0
                            CHECK (used IN (0, 1)),
                        FOREIGN KEY (skill_id)
                            REFERENCES simulation_skill_versions(id)
                            ON DELETE CASCADE
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_skill_versions_key
                    ON simulation_skill_versions (
                        task_type,
                        parameter_fingerprint,
                        id DESC
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_retrieval_tokens_skill
                    ON simulation_retrieval_tokens (skill_id)
                    """
                )
                connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM simulation_skill_heads"
            ).fetchone()
        return int(row["count"])

    def version_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM simulation_skill_versions"
            ).fetchone()
        return int(row["count"])

    def record(self, candidate: SkillCandidate) -> QualityDecision:
        rejection = evaluate_quality(candidate)
        if rejection is not None:
            return QualityDecision(accepted=False, reason=rejection)

        try:
            parameters_json = _canonical_parameters(candidate.parameters)
        except (TypeError, ValueError, OverflowError, RecursionError):
            return QualityDecision(accepted=False, reason="invalid_parameters")

        evidence = candidate.evidence
        evidence_json = _json_dumps(_evidence_dict(evidence), allow_nan=False)
        code_hash = _sha256_text(candidate.code)
        now = _utc_now()
        fingerprint = _parameter_fingerprint(parameters_json)

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO simulation_skill_versions (
                    task_type,
                    parameter_fingerprint,
                    parameters_json,
                    summary,
                    code,
                    code_sha256,
                    verdict,
                    finite,
                    has_signal,
                    max_pressure_pa,
                    rms_pressure_pa,
                    evidence_reference,
                    evidence_json,
                    evidence_sha256,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (
                    task_type,
                    parameter_fingerprint,
                    code_sha256,
                    evidence_sha256
                ) DO NOTHING
                """,
                (
                    candidate.task_type,
                    fingerprint,
                    parameters_json,
                    candidate.summary,
                    candidate.code,
                    code_hash,
                    evidence.verdict,
                    int(evidence.finite),
                    int(evidence.has_signal),
                    float(evidence.max_pressure_pa),
                    float(evidence.rms_pressure_pa),
                    evidence.analysis_run_id,
                    evidence_json,
                    evidence.artifact_sha256,
                    now,
                ),
            )
            version_row = connection.execute(
                """
                SELECT id
                FROM simulation_skill_versions
                WHERE task_type = ?
                  AND parameter_fingerprint = ?
                  AND code_sha256 = ?
                  AND evidence_sha256 = ?
                """,
                (
                    candidate.task_type,
                    fingerprint,
                    code_hash,
                    evidence.artifact_sha256,
                ),
            ).fetchone()
            if version_row is None:
                raise RuntimeError("failed to persist skill version")
            version_id = int(version_row["id"])

            connection.execute(
                """
                INSERT INTO simulation_skill_heads (
                    task_type,
                    parameter_fingerprint,
                    version_id,
                    updated_at
                )
                VALUES (?, ?, ?, ?)
                ON CONFLICT (task_type, parameter_fingerprint)
                DO UPDATE SET
                    version_id = excluded.version_id,
                    updated_at = excluded.updated_at
                WHERE excluded.version_id > simulation_skill_heads.version_id
                """,
                (candidate.task_type, fingerprint, version_id, now),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        return QualityDecision(accepted=True, reason="accepted", skill_id=version_id)

    def _row_to_result(
        self,
        row: sqlite3.Row,
        *,
        match_kind: str,
        score: float,
    ) -> dict[str, Any]:
        hit_count = int(row["hit_count"])
        success_count = int(row["success_count"])
        return {
            "skill_id": int(row["id"]),
            "task_type": row["task_type"],
            "match_kind": match_kind,
            "score": round(score, 4),
            "summary": row["summary"],
            "code": row["code"],
            "parameters": json.loads(row["parameters_json"]),
            "verdict": row["verdict"],
            "max_pressure_pa": row["max_pressure_pa"],
            "rms_pressure_pa": row["rms_pressure_pa"],
            "evidence": json.loads(row["evidence_json"]),
            "hit_count": hit_count,
            "success_count": success_count,
            "success_rate": success_count / hit_count if hit_count else 0.0,
            "updated_at": row["updated_at"],
        }

    def search(
        self,
        task_type: str,
        parameters: Mapping[str, Any],
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        if (
            not isinstance(task_type, str)
            or not task_type.strip()
            or isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= MAX_RETRIEVAL_LIMIT
        ):
            return []
        try:
            query_parameters_json = _canonical_parameters(parameters)
        except (TypeError, ValueError, OverflowError, RecursionError):
            return []

        query_fingerprint = _parameter_fingerprint(query_parameters_json)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    versions.*,
                    heads.updated_at AS updated_at
                FROM simulation_skill_heads AS heads
                JOIN simulation_skill_versions AS versions
                  ON versions.id = heads.version_id
                WHERE heads.task_type = ?
                """,
                (task_type,),
            ).fetchall()

        scored: list[tuple[float, float, float, int, str, sqlite3.Row, str]] = []
        for row in rows:
            if row["parameter_fingerprint"] == query_fingerprint:
                exact_priority = 1.0
                score = 1.0
                match_kind = "exact"
            else:
                stored_parameters = json.loads(row["parameters_json"])
                exact_priority = 0.0
                score = _similarity_score(parameters, stored_parameters)
                match_kind = "similar"
                if score < MIN_SIMILARITY:
                    continue

            hit_count = int(row["hit_count"])
            success_rate = (
                int(row["success_count"]) / hit_count if hit_count else 0.0
            )
            scored.append(
                (
                    exact_priority,
                    score,
                    success_rate,
                    hit_count,
                    row["updated_at"],
                    row,
                    match_kind,
                )
            )

        scored.sort(key=lambda item: item[:5], reverse=True)
        selected = scored[:limit]
        if not selected:
            return []

        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            results: list[dict[str, Any]] = []
            for _, score, _, _, _, row, match_kind in selected:
                token = secrets.token_urlsafe(24)
                connection.execute(
                    """
                    INSERT INTO simulation_retrieval_tokens (
                        token_hash,
                        skill_id,
                        issued_at,
                        used
                    )
                    VALUES (?, ?, ?, 0)
                    """,
                    (_sha256_text(token), int(row["id"]), _utc_now()),
                )
                connection.execute(
                    """
                    UPDATE simulation_skill_versions
                    SET hit_count = hit_count + 1
                    WHERE id = ?
                    """,
                    (int(row["id"]),),
                )
                result = self._row_to_result(
                    row,
                    match_kind=match_kind,
                    score=score,
                )
                result["hit_count"] = int(row["hit_count"]) + 1
                result["success_rate"] = (
                    int(row["success_count"]) / result["hit_count"]
                    if result["hit_count"]
                    else 0.0
                )
                result["retrieval_token"] = token
                results.append(result)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return results

    def history(
        self,
        task_type: str,
        parameters: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        try:
            parameters_json = _canonical_parameters(parameters)
        except (TypeError, ValueError, OverflowError, RecursionError):
            return []
        fingerprint = _parameter_fingerprint(parameters_json)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *, created_at AS updated_at
                FROM simulation_skill_versions
                WHERE task_type = ? AND parameter_fingerprint = ?
                ORDER BY id DESC
                """,
                (task_type, fingerprint),
            ).fetchall()
        return [
            self._row_to_result(row, match_kind="history", score=1.0)
            for row in rows
        ]

    def record_usage(
        self,
        retrieval_token: str,
        evidence: ValidationEvidence,
    ) -> dict[str, Any]:
        if not isinstance(retrieval_token, str) or not retrieval_token:
            raise KeyError("retrieval token not found")
        evidence_rejection = _validate_evidence(evidence)
        if evidence_rejection is not None:
            raise ValueError(f"invalid validation evidence: {evidence_rejection}")
        succeeded = evaluate_quality(
            SkillCandidate(
                task_type="feedback",
                parameters={"feedback_marker": 1},
                summary="Feedback validation",
                code="feedback()",
                evidence=evidence,
            )
        ) is None

        token_hash = _sha256_text(retrieval_token)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            token_row = connection.execute(
                """
                SELECT skill_id
                FROM simulation_retrieval_tokens
                WHERE token_hash = ? AND used = 0
                """,
                (token_hash,),
            ).fetchone()
            if token_row is None:
                raise KeyError("retrieval token not found or already used")
            skill_id = int(token_row["skill_id"])
            connection.execute(
                """
                UPDATE simulation_retrieval_tokens
                SET used = 1
                WHERE token_hash = ?
                """,
                (token_hash,),
            )
            if succeeded:
                connection.execute(
                    """
                    UPDATE simulation_skill_versions
                    SET success_count = success_count + 1
                    WHERE id = ?
                    """,
                    (skill_id,),
                )
            row = connection.execute(
                """
                SELECT id, hit_count, success_count
                FROM simulation_skill_versions
                WHERE id = ?
                """,
                (skill_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown skill_id: {skill_id}")
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

        hit_count = int(row["hit_count"])
        success_count = int(row["success_count"])
        return {
            "skill_id": int(row["id"]),
            "hit_count": hit_count,
            "success_count": success_count,
            "success_rate": success_count / hit_count if hit_count else 0.0,
            "succeeded": succeeded,
        }


def search_simulation_skill(
    store: SkillStore,
    task_type: str,
    parameters: Mapping[str, Any],
    limit: int = 3,
) -> dict[str, Any]:
    """Prototype adapter with an injected, server-owned store."""
    if not isinstance(store, SkillStore):
        raise TypeError("store must be a SkillStore")
    matches = store.search(task_type, parameters, limit)
    return {
        "task_type": task_type,
        "match_count": len(matches),
        "matches": matches,
    }

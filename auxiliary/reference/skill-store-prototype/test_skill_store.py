import math
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest


@pytest.fixture
def store(tmp_path: Path):
    from skill_store import SkillStore

    return SkillStore(tmp_path / "skills.db")


def analysis_result(**overrides):
    result = {
        "has_signal": True,
        "max_pressure": 1.0,
        "rms_pressure": 0.25,
        "field_shape": [16, 16],
        "verdict": "normal",
        "summary": "Peak pressure 1 Pa; verdict normal",
    }
    result.update(overrides)
    return result


def make_candidate(
    task_type: str = "plane_wave",
    parameters: dict | None = None,
    summary: str = "Validated plane-wave simulation",
    result: dict | None = None,
    run_id: str = "run-001",
    verifier_version: str = "analyze_simulation_result.v1",
    code: str = "simulate_plane_wave()",
):
    from skill_store import SkillCandidate, evidence_from_analysis_result

    evidence = evidence_from_analysis_result(
        result or analysis_result(),
        analysis_run_id=run_id,
        verifier_version=verifier_version,
    )
    return SkillCandidate(
        task_type=task_type,
        parameters=parameters
        or {
            "sound_speed_m_s": 1500.0,
            "frequency_hz": 200000.0,
            "grid_step_m": 0.0005,
            "grid_size": 256,
        },
        summary=summary,
        code=code,
        evidence=evidence,
    )


def test_evidence_adapter_hashes_real_analysis_shape():
    from skill_store import evidence_from_analysis_result

    evidence = evidence_from_analysis_result(
        analysis_result(),
        analysis_run_id="run-abc",
        verifier_version="analyze_simulation_result.v1",
    )

    assert evidence.verdict == "normal"
    assert evidence.finite is True
    assert evidence.has_signal is True
    assert len(evidence.artifact_sha256) == 64
    assert evidence.summary.startswith("Peak pressure")


def test_evidence_adapter_rejects_untrusted_metadata():
    from skill_store import evidence_from_analysis_result

    with pytest.raises(ValueError, match="analysis_run_id"):
        evidence_from_analysis_result(
            analysis_result(),
            analysis_run_id="",
            verifier_version="analyze_simulation_result.v1",
        )
    with pytest.raises(ValueError, match="verifier_version"):
        evidence_from_analysis_result(
            analysis_result(),
            analysis_run_id="run-abc",
            verifier_version="",
        )
    with pytest.raises(ValueError, match="summary"):
        evidence_from_analysis_result(
            analysis_result(summary=""),
            analysis_run_id="run-abc",
            verifier_version="analyze_simulation_result.v1",
        )


def test_rejects_non_normal_verdict(store):
    decision = store.record(make_candidate(result=analysis_result(verdict="zero_field")))

    assert decision.accepted is False
    assert decision.reason == "verdict_not_normal"
    assert store.count() == 0
    assert store.version_count() == 0


@pytest.mark.parametrize(
    ("result", "reason"),
    [
        (analysis_result(max_pressure=math.nan), "max_pressure_not_finite"),
        (
            analysis_result(
                has_signal=False,
                max_pressure=0.0,
                rms_pressure=0.0,
            ),
            "no_signal",
        ),
        (analysis_result(max_pressure=math.inf), "max_pressure_not_finite"),
        (analysis_result(max_pressure=1.0, rms_pressure=2.0), "rms_exceeds_max"),
    ],
)
def test_rejects_physically_invalid_metrics(store, result, reason):
    decision = store.record(make_candidate(result=result))

    assert decision.accepted is False
    assert decision.reason == reason
    assert store.count() == 0


def test_accepts_and_finds_exact_parameter_match(store):
    decision = store.record(make_candidate())
    assert decision.accepted is True
    assert decision.skill_id is not None

    hits = store.search(
        "plane_wave",
        {
            "sound_speed_m_s": 1500.0,
            "frequency_hz": 200000.0,
            "grid_step_m": 0.0005,
            "grid_size": 256,
        },
    )

    assert len(hits) == 1
    assert hits[0]["skill_id"] == decision.skill_id
    assert hits[0]["match_kind"] == "exact"
    assert hits[0]["score"] == 1.0
    assert hits[0]["evidence"]["analysis_run_id"] == "run-001"


def test_finds_similar_same_task_match_but_never_crosses_task_type(store):
    accepted = store.record(make_candidate())
    rejected_type = store.record(
        make_candidate(
            task_type="spherical_wave",
            parameters={
                "sound_speed_m_s": 1500.0,
                "frequency_hz": 200000.0,
                "grid_step_m": 0.0005,
                "grid_size": 256,
            },
        )
    )

    hits = store.search(
        "plane_wave",
        {
            "sound_speed_m_s": 1500.0,
            "frequency_hz": 210000.0,
            "grid_step_m": 0.0005,
            "grid_size": 256,
        },
    )
    cross_task_hits = store.search("boundary_reflection", {"grid_size": 256})

    assert accepted.accepted is True
    assert rejected_type.accepted is True
    assert len(hits) == 1
    assert hits[0]["match_kind"] == "similar"
    assert hits[0]["score"] > 0.9
    assert cross_task_hits == []


def test_rejected_failed_result_is_not_learned(store):
    decision = store.record(
        make_candidate(
            result=analysis_result(
                verdict="abnormal",
                has_signal=False,
                max_pressure=0.0,
                rms_pressure=0.0,
            )
        )
    )

    assert decision.accepted is False
    assert store.search("plane_wave", make_candidate().parameters) == []


def test_exact_match_outranks_numerically_equivalent_similar_match(store):
    exact = store.record(
        make_candidate(
            parameters={"grid_size": 100},
            summary="Exact",
            run_id="run-exact",
            code="exact()",
        )
    )
    similar = store.record(
        make_candidate(
            parameters={"grid_size": 100.0},
            summary="Numerically equivalent",
            run_id="run-similar",
            code="similar()",
        )
    )

    assert exact.skill_id is not None
    assert similar.skill_id is not None
    first_search = store.search("plane_wave", {"grid_size": 100})
    similar_hit = next(
        hit for hit in first_search if hit["skill_id"] == similar.skill_id
    )
    store.record_usage(
        similar_hit["retrieval_token"],
        make_candidate(run_id="run-feedback").evidence,
    )

    hits = store.search("plane_wave", {"grid_size": 100})

    assert [hit["summary"] for hit in hits] == ["Exact", "Numerically equivalent"]
    assert hits[0]["match_kind"] == "exact"
    assert hits[1]["match_kind"] == "similar"


def test_failed_feedback_is_retained_and_changes_success_rate(store):
    decision = store.record(make_candidate())
    assert decision.skill_id is not None

    hits = store.search("plane_wave", make_candidate().parameters)
    failed_evidence = make_candidate(
        result=analysis_result(
            verdict="abnormal",
            has_signal=False,
            max_pressure=0.0,
            rms_pressure=0.0,
        ),
        run_id="run-failed",
    ).evidence
    usage = store.record_usage(
        hits[0]["retrieval_token"],
        failed_evidence,
    )
    hits_after_feedback = store.search("plane_wave", make_candidate().parameters)

    assert usage["hit_count"] == 1
    assert usage["success_count"] == 0
    assert usage["success_rate"] == 0.0
    assert hits_after_feedback[0]["evidence"]["analysis_run_id"] == "run-001"


def test_same_evidence_contract_is_idempotent(store):
    first = store.record(make_candidate())
    second = store.record(make_candidate())

    assert first.skill_id == second.skill_id
    assert store.count() == 1
    assert store.version_count() == 1


def test_changed_code_creates_immutable_version_and_preserves_old_evidence(store):
    first = store.record(make_candidate(code="simulate_plane_wave_v1()", run_id="run-v1"))
    second = store.record(make_candidate(code="simulate_plane_wave_v2()", run_id="run-v2"))

    assert first.skill_id is not None
    assert second.skill_id is not None
    assert first.skill_id != second.skill_id
    assert store.count() == 1
    assert store.version_count() == 2

    hits = store.search("plane_wave", make_candidate().parameters)
    history = store.history("plane_wave", make_candidate().parameters)

    assert hits[0]["skill_id"] == second.skill_id
    assert hits[0]["code"] == "simulate_plane_wave_v2()"
    assert [row["evidence"]["analysis_run_id"] for row in history] == [
        "run-v2",
        "run-v1",
    ]


def test_concurrent_recording_uses_atomic_upsert(store):
    def record_once():
        from skill_store import SkillStore

        return SkillStore(store.db_path).record(make_candidate())

    with ThreadPoolExecutor(max_workers=8) as executor:
        decisions = list(executor.map(lambda _: record_once(), range(16)))

    assert all(decision.accepted for decision in decisions)
    assert len({decision.skill_id for decision in decisions}) == 1
    assert store.count() == 1
    assert store.version_count() == 1


def test_schema_rejects_invalid_rows_written_outside_repository(store):
    with sqlite3.connect(store.db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
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
                    evidence_sha256,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "plane_wave",
                    "fingerprint",
                    "{}",
                    "summary",
                    "code",
                    "a" * 64,
                    "abnormal",
                    1,
                    1,
                    1.0,
                    0.1,
                    "run",
                    "b" * 64,
                    "2026-09-23T00:00:00+00:00",
                ),
            )


def test_record_rejects_tampered_evidence_hash(store):
    candidate = replace(
        make_candidate(),
        evidence=replace(make_candidate().evidence, artifact_sha256="a" * 64),
    )

    decision = store.record(candidate)

    assert decision.accepted is False
    assert decision.reason == "invalid_evidence_hash"


def test_record_rejects_malformed_typed_evidence(store):
    candidate = replace(
        make_candidate(),
        evidence=replace(make_candidate().evidence, field_shape=None),
    )

    decision = store.record(candidate)

    assert decision.accepted is False
    assert decision.reason == "invalid_evidence"


def test_schema_rejects_malformed_json_and_blank_task(tmp_path):
    from skill_store import SkillStore

    store = SkillStore(tmp_path / "schema.db")
    with sqlite3.connect(store.db_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
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
                """,
                (
                    " ",
                    "f" * 24,
                    "not-json",
                    "summary",
                    "code",
                    "a" * 64,
                    "normal",
                    1,
                    1,
                    1.0,
                    0.1,
                    "run",
                    "not-json",
                    "b" * 64,
                    "2026-09-23T00:00:00+00:00",
                ),
            )


def test_schema_version_is_created_once_and_unsupported_version_is_rejected(tmp_path):
    import sqlite3 as sql

    from skill_store import SkillStore

    db_path = tmp_path / "versioned.db"
    with sql.connect(db_path) as connection:
        connection.execute("PRAGMA user_version=0")
    store = SkillStore(db_path)
    with sql.connect(db_path) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert version == 1
    assert {"simulation_skill_versions", "simulation_skill_heads"} <= tables

    unsupported = tmp_path / "unsupported.db"
    with sql.connect(unsupported) as connection:
        connection.execute("PRAGMA user_version=99")
    with pytest.raises(RuntimeError, match="unsupported schema version"):
        SkillStore(unsupported)


def test_usage_requires_single_use_retrieval_token(store):
    decision = store.record(make_candidate())
    hit = store.search("plane_wave", make_candidate().parameters)[0]
    token = hit["retrieval_token"]

    usage = store.record_usage(token, make_candidate(run_id="run-good").evidence)

    assert decision.accepted is True
    assert usage["success_count"] == 1
    with pytest.raises(KeyError, match="retrieval token"):
        store.record_usage(token, make_candidate(run_id="run-replay").evidence)
    with pytest.raises(KeyError, match="retrieval token"):
        store.record_usage("fabricated-token", make_candidate().evidence)


@pytest.mark.parametrize(
    "parameters",
    [
        {"huge": 10**10000},
        {"nan": math.nan},
        {"inf": math.inf},
        {1: "non-string-key"},
    ],
)
def test_invalid_parameters_return_deterministic_rejection(store, parameters):
    candidate = replace(make_candidate(), parameters=parameters)

    decision = store.record(candidate)

    assert decision.accepted is False
    assert decision.reason == "invalid_parameters"
    assert store.count() == 0


def test_non_string_text_fields_are_rejected_without_exception(store):
    candidate = replace(make_candidate(), summary=None)

    decision = store.record(candidate)

    assert decision.accepted is False
    assert decision.reason == "invalid_summary"


def test_mcp_adapter_accepts_injected_store_not_caller_controlled_path(store):
    from skill_store import search_simulation_skill

    decision = store.record(make_candidate())
    result = search_simulation_skill(
        store,
        "plane_wave",
        make_candidate().parameters,
    )

    assert decision.accepted is True
    assert result["match_count"] == 1
    assert result["matches"][0]["skill_id"] == decision.skill_id

    with pytest.raises(TypeError, match="SkillStore"):
        search_simulation_skill(
            store.db_path,
            "plane_wave",
            make_candidate().parameters,
        )


def test_search_limit_and_minimum_similarity_threshold(store):
    first = store.record(make_candidate(parameters={"grid_size": 100}))
    second = store.record(make_candidate(parameters={"grid_size": 101}))

    hits = store.search("plane_wave", {"grid_size": 100}, limit=1)
    weak = store.search("plane_wave", {"unrelated": "value"})

    assert first.accepted is True
    assert second.accepted is True
    assert len(hits) == 1
    assert weak == []


@pytest.mark.parametrize("limit", [True, 0, -1, 51, "3", None])
def test_search_rejects_invalid_limit(store, limit):
    store.record(make_candidate())

    assert store.search("plane_wave", make_candidate().parameters, limit) == []

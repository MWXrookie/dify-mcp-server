import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.skill_store import SkillStore, normalize_parameters, skill_fingerprint


def candidate(store: SkillStore, suffix: str = "") -> str:
    return store.create_candidate(
        scenario_type="point_source_2d",
        state_text="2D homogeneous point source",
        normalized_params={"frequency_hz": 500000, "dx_m": 0.00025},
        code_template=f"print('skill{suffix}')",
        postconditions={"has_signal": True},
        physics_evidence={"check_id": "numeric_valid", "passed": True},
        source_run_id=f"run-{suffix or 'one'}",
        validator_version="physics_gate.v1",
        quality_level="Q2",
    )


def test_migration_is_idempotent_and_creates_required_tables(tmp_path) -> None:
    store = SkillStore(tmp_path / "skills.db")
    store.migrate()
    store.migrate()
    db = sqlite3.connect(store.path)
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"simulation_skills", "skill_versions", "skill_events", "skill_retrievals", "schema_migrations"} <= tables


def test_candidate_is_evidence_bound_and_never_auto_activates(tmp_path) -> None:
    store = SkillStore(tmp_path / "skills.db")
    skill_id = candidate(store)
    stored = store.get_skill(skill_id)
    assert stored["status"] == "candidate"
    assert stored["quality_level"] == "Q2"
    with pytest.raises(ValueError, match="Q2"):
        store.create_candidate(scenario_type="x", state_text="x", normalized_params={}, code_template="x", postconditions={}, physics_evidence={}, source_run_id="run", validator_version="v", quality_level="Q1")


def test_concurrent_creation_and_backup_recovery(tmp_path) -> None:
    store = SkillStore(tmp_path / "skills.db")
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(lambda i: candidate(store, str(i)), range(8)))
    assert len(set(ids)) == 1
    backup = tmp_path / "backup.db"
    store.backup_to(backup)
    db = sqlite3.connect(backup)
    assert db.execute("SELECT COUNT(*) FROM simulation_skills").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM skill_versions").fetchone()[0] == 8


def test_normalization_and_fingerprint_make_equivalent_units_identical() -> None:
    mhz = normalize_parameters({"frequency_mhz": 0.5, "dx_mm": 0.25, "domain_N": [128, 128]})
    hz = normalize_parameters({"frequency_hz": 500000, "dx_m": 0.00025, "grid_size": [128, 128]})
    assert mhz == hz
    assert skill_fingerprint("point_source_2d", mhz) == skill_fingerprint("point_source_2d", hz)
    with pytest.raises(ValueError, match="unit-ambiguous"):
        normalize_parameters({"frequency": 0.5})


def test_same_fingerprint_updates_statistics_and_new_code_versions(tmp_path) -> None:
    store = SkillStore(tmp_path / "skills.db")
    first = candidate(store, "a")
    assert candidate(store, "a") == first
    assert candidate(store, "b") == first
    db = sqlite3.connect(store.path)
    assert db.execute("SELECT success_count FROM simulation_skills WHERE skill_id = ?", (first,)).fetchone()[0] == 3
    assert db.execute("SELECT COUNT(*) FROM skill_versions WHERE skill_id = ?", (first,)).fetchone()[0] == 2

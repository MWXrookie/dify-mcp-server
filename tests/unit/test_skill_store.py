import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.skill_store import SkillStore


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
    assert len(set(ids)) == 8
    backup = tmp_path / "backup.db"
    store.backup_to(backup)
    db = sqlite3.connect(backup)
    assert db.execute("SELECT COUNT(*) FROM simulation_skills").fetchone()[0] == 8

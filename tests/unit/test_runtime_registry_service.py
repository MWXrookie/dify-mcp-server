import json
import sqlite3
import pytest
from app import runtime_registry_service as service
from tests.unit.test_runtime_approval_contract import package


@pytest.fixture
def fixed(tmp_path, monkeypatch):
    manifest, data = package(tmp_path)
    data["approval_id"] = service.APPROVAL_ID
    data["scope"] = "production"
    manifest.write_text(json.dumps(data))
    monkeypatch.setattr(service, "DATABASE", tmp_path / "registry.db")
    monkeypatch.setattr(service, "PACKAGE_ROOT", tmp_path)
    monkeypatch.setattr(service.config, "PORTAL_ADMIN_TOKEN", "test-only-token-" * 3)
    return manifest, data


def observed(data):
    return [data[k] for k in ("runtime_sha256", "image_id", "recipe_sha256", "validator_sha256")]


@pytest.mark.parametrize("token", ["", "wrong", None, True])
def test_unauthorized_no_db_or_write(fixed, token):
    with pytest.raises(PermissionError): service.register_candidate(token, "test")
    assert not service.DATABASE.exists()


def test_fixed_lifecycle_retirement_no_cache(fixed):
    _, data = fixed
    token = service.config.PORTAL_ADMIN_TOKEN
    service.register_candidate(token, "fixture")
    assert not service.inspect_eligibility(*observed(data))["contract_eligible"]
    service.change_status(token, 1, "approved", "fixture review")
    result = service.inspect_eligibility(*observed(data))
    assert result["contract_eligible"] and not result["runtime_approved"] and not result["trusted_run"]
    service.change_status(token, 2, "retired", "fixture withdrawal")
    assert not service.inspect_eligibility(*observed(data))["contract_eligible"]
    with sqlite3.connect(service.DATABASE) as c:
        actors = c.execute("SELECT DISTINCT actor FROM runtime_audit").fetchall()
        assert actors == [("portal-admin",)]


@pytest.mark.parametrize("index", range(4))
def test_drift_rejected(fixed, index):
    _, data = fixed
    token = service.config.PORTAL_ADMIN_TOKEN
    service.register_candidate(token, "test")
    service.change_status(token, 1, "approved", "test")
    values = observed(data)
    values[index] = "drift"
    assert not service.inspect_eligibility(*values)["contract_eligible"]


def test_package_changed_and_retire_without_file(fixed):
    manifest, data = fixed
    token = service.config.PORTAL_ADMIN_TOKEN
    service.register_candidate(token, "test")
    data["runtime_sha256"] = "f" * 64
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError): service.change_status(token, 1, "approved", "test")
    manifest.unlink()
    service.change_status(token, 1, "retired", "withdraw missing evidence")
    assert not service.inspect_eligibility(*observed(data))["contract_eligible"]


def test_empty_server_token_rejected(fixed, monkeypatch):
    monkeypatch.setattr(service.config, "PORTAL_ADMIN_TOKEN", "")
    with pytest.raises(PermissionError): service.register_candidate("", "test")


def test_missing_registry_does_not_create(fixed):
    _, data = fixed
    assert not service.inspect_eligibility(*observed(data))["contract_eligible"]
    assert not service.DATABASE.exists()

"""Internal fixed-path approval service. Not registered as HTTP/MCP API.

Shared portal-admin credentials identify a role, not an individual human.
Eligibility remains a prerequisite and never grants runtime or physics trust.
"""
from pathlib import Path
import secrets
import sqlite3

from app import config
from scripts.validation import runtime_registry as registry
from scripts.validation.runtime_approval_contract import check_package

DATABASE = Path("/app/data/runtime_registry.db")
PACKAGE_ROOT = Path("/app/data/runtime-approvals/val1-plane-wave-v2")
APPROVAL_ID = "val1-plane-wave-v2"


def _authorize(token):
    expected = config.PORTAL_ADMIN_TOKEN
    if (not isinstance(expected, str) or len(expected) < 32
            or not isinstance(token, str)
            or not secrets.compare_digest(token.encode(), expected.encode())):
        raise PermissionError("runtime_registry_admin_required")


def _package():
    checked = check_package(PACKAGE_ROOT / "manifest.json", PACKAGE_ROOT)
    if not checked["package_valid"] or checked.get("approval_id") != APPROVAL_ID:
        raise ValueError("invalid_fixed_approval_package")
    return checked


def register_candidate(token, reason):
    _authorize(token)
    _package()
    registry.initialize(DATABASE)
    return registry.register(DATABASE, PACKAGE_ROOT / "manifest.json", PACKAGE_ROOT,
                             "portal-admin", reason)


def change_status(token, expected_revision, target, reason):
    _authorize(token)
    if target == "approved":
        package = _package()
        with sqlite3.connect(DATABASE.resolve().as_uri() + "?mode=ro", uri=True, timeout=2) as db:
            row = db.execute("SELECT manifest_sha256 FROM runtime_packages WHERE approval_id=?", (APPROVAL_ID,)).fetchone()
        if row is None or row[0] != package["manifest_sha256"]:
            raise ValueError("registered_package_changed")
    # Retirement remains possible even if the evidence package disappeared.
    return registry.transition(DATABASE, APPROVAL_ID, expected_revision, target,
                               "portal-admin", reason)


def inspect_eligibility(runtime_sha256, image_id, recipe_sha256, validator_sha256):
    result = {"contract_eligible": False, "runtime_approved": False,
              "trusted_run": False, "reason": "missing_or_invalid_registry"}
    try:
        package = _package()
        with sqlite3.connect(DATABASE.resolve().as_uri() + "?mode=ro", uri=True, timeout=2) as db:
            db.execute("BEGIN")
            row = db.execute("SELECT manifest_sha256,scope,status,revision FROM runtime_packages WHERE approval_id=?", (APPROVAL_ID,)).fetchone()
        if row is None or row[2] != "approved":
            result["reason"] = "not_currently_approved"
            return result
        if row[0] != package["manifest_sha256"] or row[1] != "production":
            result["reason"] = "package_or_scope_mismatch"
            return result
        if any(package[key] != value for key, value in (
                ("runtime_sha256", runtime_sha256), ("image_id", image_id),
                ("recipe_sha256", recipe_sha256), ("validator_sha256", validator_sha256))):
            result["reason"] = "observed_contract_mismatch"
            return result
        result.update(contract_eligible=True, revision=row[3],
                      approval_id=APPROVAL_ID, manifest_sha256=row[0],
                      reason="trusted_observation_binding_pending")
    except (OSError, sqlite3.Error, ValueError, TypeError):
        pass
    return result

"""Internal fixed VAL-1 dispatch. No caller code, parameters, or grade input.

Not a public MCP tool and not automatic skill learning. The isolated runtime
contract and numeric evidence are prerequisites, not production approval.
"""
import hashlib
import uuid

from app import dashboard, execution
from scripts.validation import plane_wave_run_binding as binding


def run_controlled_plane_wave():
    """Execute only the pinned 30s recipe through the existing executor path."""
    code = (binding.DIRECTORY / "recipes/val1_plane_wave_v2.py").read_text().strip()
    validator = (binding.DIRECTORY / "plane_wave_evidence.py").read_bytes()
    if (binding.digest(code) != binding.RECIPE_SHA256
            or hashlib.sha256(validator).hexdigest() != binding.VALIDATOR_SHA256
            or execution._clean_code(code) != code):
        raise ValueError("unreviewed_controlled_recipe_or_validator")
    run_id = str(uuid.uuid4())
    result = execution._execute_code(code, 30)
    dashboard.record_execution(
        tool_name="run_controlled_plane_wave.v1", code=code,
        exit_code=result.get("exit_code"), timed_out=result.get("timed_out", False),
        duration_ms=result.get("duration_ms"), stdout=result.get("stdout", ""),
        stderr=result.get("stderr", ""), run_id=run_id,
        execution_evidence=result.get("execution_evidence"))
    # Re-read server records, not the returned matched/grade flags.
    checked = binding.inspect_run(dashboard.DB_PATH, run_id)
    return {"run_id": run_id, "validation": checked}

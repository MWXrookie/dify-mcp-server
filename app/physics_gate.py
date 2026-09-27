"""Deterministic evidence levels for simulation results.

This is deliberately conservative: it establishes Q0/Q1/Q2 evidence without
claiming that an arbitrary generated acoustic field has passed physics.  The
scenario-specific Q3/Q4 checks are added alongside validated benchmarks.
"""

from __future__ import annotations

import json
from typing import Any


VALID_LEVELS = ("Q0", "Q1", "Q2", "Q3", "Q4")


def _check(check_id: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"check_id": check_id, "passed": passed, "detail": detail}


def assess_quality(
    *,
    exit_code: int | None,
    timed_out: bool,
    analysis: dict[str, Any],
    params_json: str = "{}",
) -> dict[str, Any]:
    """Return a structured, intentionally non-overclaiming evidence result."""
    checks: list[dict[str, Any]] = []
    executed = exit_code is not None
    checks.append(_check("execution_recorded", executed, "execution result is present"))
    if not executed:
        return {"quality_level": "Q0", "physics_checks": checks}

    finite = analysis.get("verdict") == "normal"
    nonzero = bool(analysis.get("has_signal")) and float(analysis.get("max_pressure") or 0) > 0
    succeeded = exit_code == 0 and not timed_out
    checks.extend([
        _check("execution_succeeded", succeeded, "exit_code is 0 and execution did not time out"),
        _check("finite_nonzero_field", finite and nonzero, "analysis found a finite, non-zero field"),
    ])
    if not (succeeded and finite and nonzero):
        return {"quality_level": "Q0", "physics_checks": checks}

    level = "Q1"
    try:
        params = json.loads(params_json or "{}")
    except (TypeError, json.JSONDecodeError):
        params = None
    params_ok = isinstance(params, dict) and bool(params)
    checks.append(_check("parameters_supplied", params_ok, "structured simulation parameters were supplied"))
    if params_ok:
        # Keep this independent of MCP registration, and avoid importing tools.
        required = ("sound_speed", "source_frequency", "domain_N", "domain_dx")
        required_ok = all(params.get(key) not in (None, "") for key in required)
        checks.append(_check("parameters_complete", required_ok, "minimum physical parameters are present"))
        if required_ok:
            try:
                speed = float(params["sound_speed"])
                frequency = float(params["source_frequency"])
                dx_values = params["domain_dx"] if isinstance(params["domain_dx"], list) else [params["domain_dx"]]
                grid_sizes = params["domain_N"] if isinstance(params["domain_N"], list) else [params["domain_N"]]
                cfl = float(params.get("cfl", 0.3))
                pml_size = int(params.get("pml_size", 0))
                physically_acceptable = (
                    speed > 0 and frequency > 0 and 0 < cfl <= 0.3
                    and all(0 < float(dx) <= speed / frequency / 4 for dx in dx_values)
                )
                positions = [params.get("source_index"), params.get("sensor_index")]
                supplied_positions = [position for position in positions if position is not None]
                pml_ok = True
                for position in supplied_positions:
                    if not isinstance(position, list) or len(position) != len(grid_sizes):
                        pml_ok = False
                        break
                    pml_ok = pml_ok and all(pml_size <= int(index) < int(size) - pml_size
                                            for index, size in zip(position, grid_sizes))
            except (TypeError, ValueError):
                physically_acceptable = False
                pml_ok = False
            checks.append(_check("parameter_constraints", physically_acceptable,
                                 "Nyquist and CFL constraints pass the deterministic baseline"))
            checks.append(_check("pml_geometry", pml_ok,
                                 "supplied source/sensor indices are outside PML; absent geometry is deferred"))
            if physically_acceptable and pml_ok:
                level = "Q2"

    return {"quality_level": level, "physics_checks": checks}

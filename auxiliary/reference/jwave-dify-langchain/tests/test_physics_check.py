"""方案一：参数物理预检的单元测试。"""
from __future__ import annotations

import json
from pathlib import Path

from jwave_flow.config import Settings
from jwave_flow.physics import check_params, extract_scalars

# 实测「参数提取」节点真实输出（DeepSeek，注意：没有任何 dx 字段）
REAL_PARAMS = """
{
  "dimension": 2,
  "grid_size": [64, 64],
  "medium": {"sound_speed": 1500.0},
  "source": {"type": "point", "frequency": 5000000.0},
  "simulation_time": 2e-05,
  "output_field": "pressure",
  "jwave": {"simulate_function": "simulate_wave_propagation", "sensors": null, "postprocess": "none"}
}
"""


def _settings(**kw):
    return Settings.from_env(**kw)


def test_reads_nested_real_world_params():
    s = extract_scalars(REAL_PARAMS)
    assert s["sound_speed"] == 1500.0        # nested under "medium"
    assert s["frequency"] == 5e6             # nested under "source"
    assert s["t_end"] == 2e-5                # "simulation_time"
    assert s["grid_size"] == [64, 64]


def test_real_params_pass_with_a_dx_constraint():
    r = check_params(REAL_PARAMS, _settings(min_points_per_wavelength=6))
    assert r.ok, [i.message for i in r.errors]
    # 没有 dx -> 反算上限并注入约束，而不是误报
    assert r.constraints and "dx ≤" in r.constraints[0]
    assert abs(float(r.constraints[0].split("dx ≤ ")[1].split(" m")[0]) - 1500 / (5e6 * 6)) < 1e-12


def test_under_resolved_grid_is_flagged():
    params = json.dumps(
        {"sound_speed": 1500.0, "frequency": 5e6, "simulation_time": 2e-5, "dx": 1e-4}
    )
    r = check_params(params, _settings())
    codes = [i.code for i in r.issues]
    assert "W_UNDER_RESOLVED" in codes          # 3 points per wavelength < 6
    assert r.ok                                  # 只是告警，不拦截


def test_well_resolved_grid_is_clean():
    params = json.dumps(
        {"sound_speed": 1500.0, "frequency": 2e6, "simulation_time": 50e-6, "dx": 1e-4}
    )
    r = check_params(params, _settings())
    assert r.ok and not r.issues, [i.message for i in r.issues]


def test_errors_block_codegen():
    r = check_params("{}", _settings())
    codes = {i.code for i in r.errors}
    assert {"E_NO_SOUND_SPEED", "E_NO_FREQUENCY"} <= codes
    assert not r.ok


def test_pml_thicker_than_half_domain_is_an_error():
    params = json.dumps({"sound_speed": 1500, "frequency": 1e6, "grid_size": [32, 32], "pml_size": 20})
    r = check_params(params, _settings())
    assert "E_PML_TOO_THICK" in {i.code for i in r.errors}


def test_source_inside_pml_is_flagged():
    params = json.dumps(
        {"sound_speed": 1500, "frequency": 1e6, "grid_size": [64, 64], "pml_size": 20,
         "positions": [[5, 32]]}
    )
    r = check_params(params, _settings())
    assert "W_SOURCE_IN_PML" in {i.code for i in r.issues}


def test_garbage_input_does_not_crash():
    for bad in ["", "not json", "[1,2,3]", "null"]:
        r = check_params(bad, _settings())
        assert not r.ok          # 解析不出声速/频率 -> error

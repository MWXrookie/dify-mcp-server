"""方案二 / 方案三 的单元级契约测试。"""
from __future__ import annotations

import json

from jwave_flow.config import Settings
from jwave_flow.semantic import MARKER, check_semantics, parse_selfcheck
from jwave_flow.static_check import check_code


def _codes(code: str) -> set[str]:
    return {i.rule for i in check_code(code).issues}


# --------------------------- 方案二：命中 --------------------------- #
def test_catches_tone_burst_dt():
    assert "R1_TONE_BURST_DT" in _codes("sig = tone_burst(time_axis.dt, 5e6, 3)\n")


def test_catches_double_pressure_conversion():
    code = (
        "rho = jw.simulate_wave_propagation(medium, time_axis, sources=sources)\n"
        "p = jw.pressure_from_density(rho, medium)\n"
    )
    assert "R2_DOUBLE_PRESSURE" in _codes(code)


def test_catches_float_positions():
    assert "R3_FLOAT_POSITIONS" in _codes("positions = (jnp.array([64.0]), jnp.array([64.0]))\n")


def test_catches_list_signals_and_positions():
    """真实踩坑：Sources 的 signals/positions 传成 list -> TypeError。"""
    codes = _codes(
        "src = Sources([(64, 64)], [tone_burst(1/dt, 5e6, 1)], dt, domain)\n"
    )
    assert {"R9_SIGNALS_LIST", "R10_POSITIONS_LIST"} <= codes


def test_catches_list_signals_passed_as_keyword():
    codes = _codes("src = Sources(positions=p, signals=[sig], dt=dt, domain=d)\n")
    assert "R9_SIGNALS_LIST" in codes


def test_correct_sources_call_is_not_flagged():
    """知识库里的正确写法不能被误报。"""
    good = (
        "positions = (jnp.array([64]), jnp.array([64]))\n"
        "signals = jnp.expand_dims(signal_1d, 0)\n"
        "sources = Sources(positions, signals, dt, domain)\n"
    )
    assert check_code(good).ok, [i.render() for i in check_code(good).issues]


def test_catches_sources_keywords():
    assert "R4_SOURCES_KEYWORDS" in _codes("s = Sources(positions=p, signals=s, dt=dt, domain=d)\n")


def test_catches_jw_np_and_top_level_utils():
    codes = _codes("x = jw.np.array([1])\njw.show_field(f)\n")
    assert {"R5_JW_NP", "R8_TOPLEVEL_UTILS"} <= codes


def test_catches_time_axis_t_and_from_array():
    codes = _codes("t = time_axis.t\nf = FourierSeries.from_array(d, domain)\n")
    assert {"R6_TIME_AXIS_T", "R7_FOURIER_FROM_ARRAY"} <= codes


def test_syntax_error_is_reported_not_raised():
    r = check_code("def broken(:\n")
    assert not r.ok and r.parse_error


# ------------------------ 方案二：零误报 ------------------------ #
def test_correct_code_is_clean():
    good = (
        "import jax.numpy as jnp\n"
        "dt = time_axis.dt\n"
        "sig = tone_burst(1 / dt, 5e6, 3)\n"
        "positions = (jnp.array([64]), jnp.array([64]))\n"
        "sources = Sources(positions, signals, dt, domain)\n"
        "p = jw.simulate_wave_propagation(medium, time_axis, sources=sources)\n"
        "jw.utils.show_field(p[-1], 'final')\n"
    )
    assert check_code(good).ok, [i.render() for i in check_code(good).issues]


# --------------------------- 方案三 --------------------------- #
def _line(payload: dict) -> str:
    return f"some log\n{MARKER}{json.dumps(payload)}\n"


def _settings(**kw):
    return Settings.from_env(**kw)


def test_selfcheck_parsed_from_noisy_stdout():
    data = parse_selfcheck(_line({"finite": True, "abs_max": 1.0, "shape": [1]}))
    assert data["abs_max"] == 1.0


def test_semantic_ok_for_healthy_field():
    r = check_semantics(
        _line({"finite": True, "abs_max": 5016.6, "shape": [1001, 64, 64, 1], "f0": 5e6}),
        _settings(),
        expected={"frequency": 5e6},
    )
    assert r.ok, r.issues


def test_semantic_flags_missing_selfcheck():
    r = check_semantics("all good\n", _settings())
    assert not r.ok and "找不到自检行" in r.issues[0]


def test_semantic_flags_nan_and_zero_and_divergence():
    base = {"shape": [4, 4, 4, 1]}
    assert not check_semantics(_line({**base, "finite": False, "abs_max": 1.0}), _settings()).ok
    assert not check_semantics(_line({**base, "finite": True, "abs_max": 0.0}), _settings()).ok
    assert not check_semantics(_line({**base, "finite": True, "abs_max": 1e30}), _settings()).ok


def test_semantic_flags_frequency_mismatch():
    r = check_semantics(
        _line({"finite": True, "abs_max": 1.0, "shape": [4], "f0": 2e6}),
        _settings(),
        expected={"frequency": 5e6},
    )
    assert any("与需求" in i for i in r.issues)


def test_selfcheck_can_be_optional():
    r = check_semantics("no marker here\n", _settings(require_selfcheck=False))
    assert r.ok

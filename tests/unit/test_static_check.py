from app.static_check import check_code


def test_valid_code_passes() -> None:
    report = check_code(
        """
import jax.numpy as jnp
from jwave.geometry import Domain, Medium, TimeAxis

domain = Domain((32, 32), (1.0, 1.0))
medium = Medium(domain=domain, sound_speed=1500.0)
time_axis = TimeAxis.from_medium(medium, cfl=0.3)
positions = (jnp.array([16]), jnp.array([16]))
"""
    )

    assert report.ok
    assert report.parse_error is None
    assert report.issues == []


def test_tone_burst_rejects_dt_as_first_argument() -> None:
    report = check_code("signal = tone_burst(time_axis.dt, 1e6, 5)")

    assert not report.ok
    assert [issue.rule for issue in report.issues] == ["R1_TONE_BURST_DT"]


def test_fourier_series_from_array_is_rejected() -> None:
    report = check_code("field = FourierSeries.from_array(data, domain)")

    assert not report.ok
    assert "R7_FOURIER_FROM_ARRAY" in {issue.rule for issue in report.issues}


def test_syntax_error_is_reported_without_raising() -> None:
    report = check_code("def broken(:")

    assert not report.ok
    assert report.parse_error
    assert report.issues == []

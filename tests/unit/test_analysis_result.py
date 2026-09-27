import base64
import json

from app.analysis import _analyze_impl, _extract_sensor


def _stdout_with_field_and_sensor() -> str:
    return "\n".join(
        [
            "__ACOU_SENSOR_START__",
            json.dumps({
                "time": [0.0, 1e-6, 2e-6],
                "pressure": [0.0, 0.25, -0.5],
                "sensor_index": [84, 64],
                "sensor_position_m": [0.021, 0.016],
            }),
            "__ACOU_SENSOR_END__",
            "__ACOU_FIELD_START__",
            json.dumps({
                "shape": [2, 2],
                "kind": "field",
                "max_pressure": 0.5,
                "data": [[0.0, 0.2], [0.3, 0.5]],
            }),
            "__ACOU_FIELD_END__",
        ]
    )


def test_sensor_time_series_drives_waveform() -> None:
    stdout = _stdout_with_field_and_sensor()
    sensor = _extract_sensor(stdout)
    assert sensor is not None
    assert sensor["sensor_index"] == [84, 64]

    result = _analyze_impl(stdout, exit_code=0)
    assert result["verdict"] == "normal"
    assert result["waveform_kind"] == "sensor_time"
    assert result["sensor_samples"] == 3
    assert result["sensor_peak_pressure"] == 0.5
    assert base64.b64decode(result["waveform_png_base64"]).startswith(b"\x89PNG")


def test_legacy_sensor_markers_remain_supported() -> None:
    stdout = _stdout_with_field_and_sensor().replace("__ACOU_SENSOR", "__SENSOR_DATA")
    assert _extract_sensor(stdout)["pressure"] == [0.0, 0.25, -0.5]

"""Apply the auditable field/sensor output contract to the Dify code-generation node.

Usage: python3 scripts/workflow/_apply_result_contract.py graph.json > patched.json
"""

import json
import sys

CODE_GEN = "1783991079665"
MARKER = "## 结果输出契约（必须遵守）"

CONTRACT = r'''

## 结果输出契约（必须遵守）
- `Sources.positions` 是整数网格索引，不是米制坐标。中心点示例：
  `positions = (jnp.array([64], dtype=jnp.int32), jnp.array([64], dtype=jnp.int32))`。
- 不要用 matplotlib、`imshow`、`plot` 或 `savefig` 自己作图。网关统一根据下述数据生成图像，避免初始帧黑图和中文字体告警。
- 稳态/峰值声压场必须取完整时间序列的逐点最大绝对值：
  `field = jnp.max(jnp.abs(p.params), axis=0)[..., 0]`。
  禁止使用 `p.params[0]`、`pressure[0, ...]` 或 t=0 帧作热力图；也不要只用某个任意末帧冒充稳态场。
- 按已有 `__ACOU_FIELD_START__` / `__ACOU_FIELD_END__` 模板输出二维 field JSON。
- 需求包含点传感器时，距离先换算为整数网格偏移，例如 `offset = int(round(distance_m / dx))`；
  从完整压力序列读取 `sensor_pressure = p.params[:, sensor_x, sensor_y, 0]`，并额外输出：
  `__ACOU_SENSOR_START__`
  `{"time": [...], "pressure": [...], "sensor_index": [x, y], "sensor_position_m": [x_m, y_m]}`
  `__ACOU_SENSOR_END__`
  单传感器的 `time` 与 `pressure` 必须是一维等长数组。网关会据此生成真正的时域声压曲线。
'''


def main() -> None:
    graph = json.load(open(sys.argv[1], encoding="utf-8"))
    found = False
    for node in graph.get("nodes", []):
        if node.get("id") != CODE_GEN:
            continue
        for message in node.get("data", {}).get("prompt_template", []):
            if message.get("role") != "user":
                continue
            text = message.get("text", "")
            text = text.replace("pressure = p.params[0]", "pressure = p.params")
            if MARKER not in text:
                text = text.rstrip() + CONTRACT
            message["text"] = text
            found = True
    if not found:
        raise SystemExit(f"code-generation node {CODE_GEN} not found")
    print(json.dumps(graph, ensure_ascii=False))


if __name__ == "__main__":
    main()

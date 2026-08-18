"""结果分析模块（T-007 analyze_simulation_result 的落点）。

当前为占位模块：T-007 落地时在此实现
- 压力场热力图 / 波形图生成（executor 内 matplotlib 已就绪，3.11.1）
- 物理量摘要（max_pressure / rms_pressure / field_shape / has_signal）
- verdict 判定（normal / zero_field / abnormal），判定口径对标
  docs/VALIDATION_BASELINE.md（VAL-1 验证基准集：振幅守恒、1/√r 衰减、阻抗公式）

保持本模块与 tools.py 分离：tools 管"执行"，analysis 管"读懂结果"。
"""


def register(mcp) -> None:
    """向 FastMCP 实例注册本模块工具（T-007 落地时在此挂载）。"""
    # T-007: @mcp.tool analyze_simulation_result(...)
    pass

# jwave 仿真常见问题排查（troubleshooting）

> 面向 LLM 代码生成与自动纠错：按症状定位根因并给修复。
> 数据来源：50 次回归失败分类 + VAL-1 踩坑 + 3D/衰减扩展实测 + 历史 BUG 记录。
> 修改记录：2026-08-18 新建。

### 症状 1 · 压力场全零（最高频故障）

| 可能原因 | 判断方法 | 修复 |
|---------|---------|------|
| Sources 坐标是浮点数 | 检查 `positions` 是否 `jnp.array([64.0])` | 改整数 `jnp.array([64])` |
| signals 是 list/tuple | 检查 `signals` 类型 | `jnp.expand_dims(sig_1d, 0)` 转 2D array |
| Sources 用了关键字参数 | 看调用是否有 `=` | 改 4 位置参数 `Sources(positions, signals, dt, domain)` |
| 环形/椭圆半径超域 | R0 ≥ N/2 − pml_size | 减小半径或增大网格/区域 |
| 初始场放进 PML | p0 覆盖到边缘 | 初始场限在物理区内 |
| 探针放进 PML | 探针位置 ≥ N/2 − pml_size | 移到物理区内（见物理规则） |

### 症状 2 · 幅度异常偏小/衰减太快

| 可能原因 | 判断 | 修复 |
|---------|------|------|
| 探针在 PML 吸收层 | 位置 ≥ N/2 − pml_size | 移到物理区内（实测吸收 16×） |
| dx 太粗（色散） | dx > λ/4 | 减小 dx（每波长 ≥8 点） |
| t_end 太短 | 波未到探针 | 增大 t_end（t_end ≈ 距离/c） |
| 3D N 太大 OOM 截断 | 看 stderr | N ≤ 72 或缩短 t_end |

### 症状 3 · 衰减没效果

| 可能原因 | 判断 | 修复 |
|---------|------|------|
| 用了时域 simulate_wave_propagation | 检查求解器 | **时域忽略 attenuation**，改频域 `helmholtz_solver` |
| 没设 attenuation | Medium 缺参数 | `Medium(..., attenuation=alpha_db)` |

### 症状 4 · 代码执行报错（SyntaxError / TypeError）

| 错误 | 根因 | 修复 |
|------|------|------|
| SyntaxError | 输出被 markdown ``` 包裹 | 代码生成不要包裹 |
| TypeError: list/tuple | signals 非 2D array | `jnp.expand_dims(sig, 0)` |
| AttributeError: 'TimeAxis' has no 't' | 用了 `time_axis.t` | 改 `time_axis.to_array()` |
| AttributeError: no 'shape' | 用了 `p0.shape` | 改 `p0.params.shape` |
| plum NotFoundLookupError | helmholtz_solver 传了裸数组 | 包成 `jw.FourierSeries(...)` |
| TypeError: unexpected keyword | Sources 用关键字参数 | 改 4 位置参数 |

### 症状 5 · LLM 编造不存在的 API

| 编造写法 | 正确写法 |
|---------|---------|
| `p0.data` | `p0.params` |
| `time_axis.time` | `time_axis.to_array()` |
| `FourierSeries.from_array(x, domain)` | `FourierSeries(x, domain)` |
| `initial_pressure=` 参数 | `p0=` 关键字 |
| `jw.Sensors(positions=[...])` 采样 | 直接取全场 `p[t, x, y, 0]` |

### 症状 6 · 检索/embedding 偶发失败

| 症状 | 根因 | 处理 |
|------|------|------|
| retrieve 报 RemoteDisconnected | tongyi embedding API 抖动 | 重试即可（非代码问题） |
| 索引状态 error | 同上（embedding 时段性故障） | 等恢复后重新触发索引 |

### 症状 7 · 结果物理上可疑（但不报错）

| 可疑现象 | 检查 | 参考 |
|---------|------|------|
| 2D 点源幅度不按 1/√r | 探针距离、物理区 | 几何扩散表（物理规则） |
| 3D 幅度不按 1/r | N、探针、PML | 同上 |
| 界面反射系数异常 | 阻抗公式 Z=ρc | VAL-1 用例 3 |
| 全零但 exit_code=0 | 最大压力 = 0 | 见症状 1 |

### 排查顺序建议（自动纠错用）

1. 看 exit_code：非 0 → 看 stderr 最后一行的错误类型（症状 4/5）
2. exit_code=0 但全零 → 症状 1（先查 Sources 坐标/signals/关键字）
3. 幅度异常 → 症状 2（先查 PML 物理区）
4. 衰减无效 → 症状 3（先查是否时域）
5. 都正常但仍失败 → 重试（embedding 抖动，症状 6）

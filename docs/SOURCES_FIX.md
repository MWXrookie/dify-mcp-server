# jwave 0.2.1 Sources 点源输出全零问题根因分析

## 问题描述

使用 `jwave.geometry.Sources` 配置点源时，仿真输出压力场全为零 (`max_pressure = 0.0`)，
但使用 `p0` 初始压力方式（FourierSeries）时压力场正常（~600 Pa）。

## 根因分析

**根本原因：`Sources.positions` 必须传入整数类型（int32）的 JAX 数组，不能是浮点数类型。**

### 技术细节

`Sources.on_grid(n)` 方法的实现如下（来自 `jwave/geometry.py` 第 438-448 行）：

```python
def on_grid(self, n):
    src = jnp.zeros(self.domain.N)
    if len(self.signals) == 0:
        return src

    idx = n.astype(jnp.int32)
    signals = self.signals[:, idx]
    src = src.at[self.positions].add(signals)   # <-- 关键行
    return jnp.expand_dims(src, -1)
```

关键在 `src.at[self.positions].add(signals)` 这一行。JAX 的 `.at[]` 索引操作要求索引必须是**整数类型**（int32 或 int64）。
如果 `self.positions` 是浮点数数组（如 `jnp.array([64.0])`），JAX 会在运行时抛出：

```
TypeError: Indexer must have integer or boolean type, got indexer with type float32
at position 0, indexer value [64.]
```

### 为什么会全零？

jwave 的 `simulate_wave_propagation` 函数使用 `jax.lax.scan` 进行时间步进。在 JIT 编译模式下，`sources.on_grid(n)` 内部的 `TypeError` 不会被直接抛出，而是被 JAX 的 trace 机制吞没，导致 `mass_src_field` 始终为 0，最终压力场全为零。

## 修复方式

### 正确用法：使用整数坐标

```python
import jax.numpy as jnp
from jwave.geometry import Sources, Domain

domain = Domain((128, 128), (0.001, 0.001))

# WRONG: float positions (会导致全零)
positions = (jnp.array([64.0]), jnp.array([64.0]))

# CORRECT: integer positions
positions = (jnp.array([64]), jnp.array([64]))
```

### 完整示例

```python
import jax.numpy as jnp
from jwave import FourierSeries
from jwave.geometry import Domain, Medium, Sources, TimeAxis
from jwave.acoustics import simulate_wave_propagation

N = (128, 128)
domain = Domain(N, (0.001, 0.001))
medium = Medium(domain=domain, sound_speed=1500.0)
time_axis = TimeAxis.from_medium(medium, cfl=0.3)

Nt = int(time_axis.Nt)
signal = jnp.sin(jnp.linspace(0, 4 * jnp.pi, Nt))
signal = signal / jnp.max(jnp.abs(signal))

# 关键：使用整数坐标
cx, cy = N[0] // 2, N[1] // 2  # 64, 64 (Python int -> jnp 推断为 int32)
positions = (jnp.array([cx]), jnp.array([cy]))
signals = jnp.expand_dims(signal, 0)
sources = Sources(positions, signals, time_axis.dt, domain)

result = simulate_wave_propagation(medium, time_axis, sources=sources)
print(f"max pressure: {jnp.max(result.params)}")  # 非零输出
```

## 验证结果

| positions 类型 | dtype | 结果 |
|---------------|-------|------|
| `jnp.array([64.0])` | float32 | max_pressure = 0.0 (TypeError 被 JIT 吞没) |
| `jnp.array([64])` | int32 | max_pressure = 0.096 Pa (正常) |

## jwave 上游 Bug

`Sources.__init__` 方法未对 `positions` 做类型校验，允许用户传入浮点数但会在 `on_grid` 中静默失败。

建议上游修复：
- 在 `Sources.__init__` 中对 positions 做 `jnp.asarray(p, dtype=jnp.int32)` 强制转换
- 或在 docstring 中明确注明 positions 必须是整数数组

## 测试环境

- jwave 版本: 0.2.1
- 执行环境: Docker 容器 jwave-executor

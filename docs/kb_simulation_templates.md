# jwave 仿真代码模板库（可直接抄用）

> 本文件收录 6 套**沙箱实测可运行**的 jwave 0.2.1 仿真模板，覆盖常见声学仿真需求。
> 每套模板独立成节（`###`），可直接复制改参数使用。
> 修改记录：2026-08-18 新建（内容来自 50 次回归 + VAL-1 验证 + 3D/衰减扩展实测）。

### 模板 1 · 2D 点声源传播（最常用）

适用：点源激励、均匀介质、声场传播可视化。已验证可运行（回归 50 次基准）。

```python
import jax.numpy as jnp
import jwave as jw
from jaxdf import FourierSeries
from jwave.acoustics.time_varying import TimeWavePropagationSettings

S = TimeWavePropagationSettings(smooth_initial=False)

N, dx = 128, 0.1e-3                      # 网格点数、间距（dx ≤ λ/4）
domain = jw.Domain((N, N), (dx, dx))
medium = jw.Medium(domain, sound_speed=1500.0, density=1000.0, pml_size=20)
time_axis = jw.TimeAxis.from_medium(medium, cfl=0.1, t_end=40e-6)

c = N // 2
sig = jw.signal_processing.tone_burst(1.0 / time_axis.dt, 2e6, 3)   # 2 MHz 3 周期
signals = jnp.expand_dims(sig, 0)                                    # (1, Nt)
sources = jw.Sources((jnp.array([c]), jnp.array([c])), signals, time_axis.dt, domain)

p = jw.simulate_wave_propagation(medium, time_axis, sources=sources, settings=S).params
maxp = float(jnp.max(jnp.abs(p)))          # 最大压力（Pa）
```

改参数：`N/dx` 调分辨率，`2e6` 调频率，`t_end` 调仿真时长，`sound_speed/density` 调介质。

### 模板 2 · p0 高斯初始压力

适用：初始压力分布（非点源）场景，如脉冲源、压力包。已验证（p0 场景 4/4 通过）。

```python
import jax.numpy as jnp
import jwave as jw
from jaxdf import FourierSeries
from jwave.acoustics.time_varying import TimeWavePropagationSettings

S = TimeWavePropagationSettings(smooth_initial=False)
N, dx = 192, 0.1e-3
domain = jw.Domain((N, N), (dx, dx))
medium = jw.Medium(domain, sound_speed=1500.0, density=1000.0, pml_size=20)
time_axis = jw.TimeAxis.from_medium(medium, cfl=0.1, t_end=40e-6)

x = jnp.linspace(0, N * dx, N)
XX, YY = jnp.meshgrid(x, x, indexing="ij")          # 必须 indexing='ij'
cx = cy = N // 2
sigma = 0.4e-3                                       # 高斯半宽（m）
p0_grid = 800.0 * jnp.exp(-((XX - cx * dx) ** 2 + (YY - cy * dx) ** 2) / (2 * sigma ** 2))
p0 = FourierSeries(p0_grid, domain)

p = jw.simulate_wave_propagation(medium, time_axis, p0=p0, settings=S).params
maxp = float(jnp.max(jnp.abs(p)))
```

改参数：`800.0` 峰值 Pa、`sigma` 宽度、`cx/cy` 位置（用 `cx*dx` 换算物理坐标）。

### 模板 3 · p0 环形 / 椭圆初始压力

适用：环形激励、椭圆聚焦源。⚠️ 环形半径必须 < 物理区半径（N/2 − pml_size）。

```python
import jax.numpy as jnp
import jwave as jw
from jaxdf import FourierSeries
from jwave.acoustics.time_varying import TimeWavePropagationSettings

S = TimeWavePropagationSettings(smooth_initial=False)
N, dx = 200, 0.1e-3
domain = jw.Domain((N, N), (dx, dx))
medium = jw.Medium(domain, sound_speed=1500.0, density=1000.0, pml_size=20)
time_axis = jw.TimeAxis.from_medium(medium, cfl=0.1, t_end=40e-6)

x = jnp.linspace(0, N * dx, N)
XX, YY = jnp.meshgrid(x, x, indexing="ij")
cx = cy = N // 2
r = jnp.sqrt((XX - cx * dx) ** 2 + (YY - cy * dx) ** 2)

# 环形: R0 环半径, sigma 环宽
R0, sigma = 1.5e-3, 0.2e-3
p0_grid = 400.0 * jnp.exp(-((r - R0) ** 2) / (2 * sigma ** 2))

# 椭圆: a/b 长短半轴
# p0_grid = 900.0 * jnp.exp(-(((XX-cx*dx)/a)**2 + ((YY-cy*dx)/b)**2) / 2)

p0 = FourierSeries(p0_grid, domain)
p = jw.simulate_wave_propagation(medium, time_axis, p0=p0, settings=S).params
maxp = float(jnp.max(jnp.abs(p)))
```

### 模板 4 · 异质介质（空间变化声速）

适用：囊肿、分层、组织异质。声速用与域同形的数组。

```python
import jax.numpy as jnp
import jwave as jw
from jaxdf import FourierSeries
from jwave.acoustics.time_varying import TimeWavePropagationSettings

S = TimeWavePropagationSettings(smooth_initial=False)
N, dx = 200, 0.1e-3
domain = jw.Domain((N, N), (dx, dx))
time_axis = jw.TimeAxis.from_medium(
    jw.Medium(domain, sound_speed=1540.0, density=1000.0, pml_size=20),
    cfl=0.1, t_end=50e-6,
)

x = jnp.linspace(0, N * dx, N)
XX, YY = jnp.meshgrid(x, x, indexing="ij")
c_map = jnp.full((N, N), 1540.0)
r = jnp.sqrt((XX - N // 2 * dx) ** 2 + (YY - N // 2 * dx) ** 2)
c_map = jnp.where(r < 1.25e-3, 1420.0, c_map)     # 直径 2.5mm 低声速囊肿

medium = jw.Medium(domain, sound_speed=c_map, density=1000.0, pml_size=20)
sig = jw.signal_processing.tone_burst(1.0 / time_axis.dt, 2e6, 3)
signals = jnp.expand_dims(sig, 0)
sources = jw.Sources((jnp.array([N // 4]), jnp.array([N // 2])), signals, time_axis.dt, domain)

p = jw.simulate_wave_propagation(medium, time_axis, sources=sources, settings=S).params
maxp = float(jnp.max(jnp.abs(p)))
```

改参数：`c_map` 中 `1420.0`/`1.25e-3` 换囊肿声速/半径；支持多层 `jnp.where` 叠加。

### 模板 5 · 3D 球面波传播（P1 新增）

适用：三维声场、立体传播。⚠️ 3D 内存红线：N ≤ 72（N³×Nt×4B ≤ ~2GB）。

```python
import jax.numpy as jnp
import jwave as jw
from jaxdf import FourierSeries
from jwave.acoustics.time_varying import TimeWavePropagationSettings

S = TimeWavePropagationSettings(smooth_initial=False)
N, dx = 48, 0.5e-3                             # 3D 用 N≤72；dx 用 0.5mm 控制内存
domain = jw.Domain((N, N, N), (dx, dx, dx))
medium = jw.Medium(domain, sound_speed=1500.0, density=1000.0, pml_size=8)
time_axis = jw.TimeAxis.from_medium(medium, cfl=0.1, t_end=20e-6)

c = N // 2
sig = jw.signal_processing.tone_burst(1.0 / time_axis.dt, 300e3, 3)   # 3D 用较低频
signals = jnp.expand_dims(sig, 0)
positions = (jnp.array([c]), jnp.array([c]), jnp.array([c]))          # 3D 三坐标
sources = jw.Sources(positions, signals, time_axis.dt, domain)

p = jw.simulate_wave_propagation(medium, time_axis, sources=sources, settings=S).params
maxp = float(jnp.max(jnp.abs(p)))              # p.shape = (Nt, N, N, N, 1)
```

3D 高斯球 p0（替代点源，接上面模板 5 的 domain/time_axis/变量使用）：
```python
x = jnp.linspace(0, N * dx, N)
XX, YY, ZZ = jnp.meshgrid(x, x, x, indexing="ij")
sigma = 2 * dx
p0_grid = jnp.exp(-((XX - c * dx) ** 2 + (YY - c * dx) ** 2 + (ZZ - c * dx) ** 2) / (2 * sigma ** 2))
p0 = FourierSeries(p0_grid, domain)
p = jw.simulate_wave_propagation(medium, time_axis, p0=p0, settings=S).params
```

### 模板 6 · 频域 Helmholtz 介质衰减（P1 新增）

适用：介质吸收/衰减仿真。⚠️ 时域忽略 attenuation，必须走频域。

```python
import jax.numpy as jnp
import jwave as jw
from jwave.acoustics import helmholtz_solver, db2neper

N, dx = 160, 0.5e-3
domain = jw.Domain((N, N), (dx, dx))
f0, c0, alpha_db = 1e6, 1500.0, 1.0            # 1 MHz, 衰减 1 dB (幂律 y=2)
omega = 2 * jnp.pi * f0
medium = jw.Medium(domain, sound_speed=c0, density=1000.0,
                   attenuation=alpha_db, pml_size=20)

c = N // 2
src = jw.FourierSeries(jnp.zeros((N, N), dtype=jnp.complex64).at[c, c].set(1.0), domain)
u = helmholtz_solver(medium, omega, src, method="gmres")
p = jnp.asarray(u.on_grid).reshape(N, N)       # 复场，取模 jnp.abs(p)
maxp = float(jnp.max(jnp.abs(p)))
```

理论参考：`Im(k) = omega**2 * db2neper(alpha_db, 2.0)`（neper/m），
振幅沿 r 按 `exp(-Im(k)*r)` 衰减，2D 再乘 `1/sqrt(r)` 圆柱扩散。

### 模板速查表

| 场景 | 模板 | 关键参数 | 注意 |
|------|------|---------|------|
| 点源传播 | 1 | N/dx/f0/t_end | Sources 4 位置参数、整数坐标 |
| 高斯 p0 | 2 | 峰值/σ/位置 | indexing='ij' |
| 环形/椭圆 p0 | 3 | R0/a/b | 半径 < N/2−pml_size |
| 异质介质 | 4 | c_map | 声速数组平滑过渡 |
| 3D 传播 | 5 | N≤72 | 内存红线 |
| 介质衰减 | 6 | alpha_db/f0 | 必须频域 helmholtz_solver |

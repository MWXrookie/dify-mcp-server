# jwave 声学仿真知识库（优化版）

### 快速上手 · 时域仿真最小模板（2D 点源）

```python
import jax.numpy as jnp
import jwave as jw
from jaxdf import FourierSeries
from jwave.acoustics.time_varying import TimeWavePropagationSettings

S = TimeWavePropagationSettings(smooth_initial=False)  # 关闭初值平滑，保真

N = 128                      # 网格点数（每波长 ≥ 8 点，见"物理规则"）
dx = 0.1e-3                  # 网格间距 m
domain = jw.Domain((N, N), (dx, dx))
medium = jw.Medium(domain, sound_speed=1500.0, density=1000.0, pml_size=20)
time_axis = jw.TimeAxis.from_medium(medium, cfl=0.1, t_end=40e-6)

c = N // 2
positions = (jnp.array([c]), jnp.array([c]))           # 整数坐标！
sig = jw.signal_processing.tone_burst(1.0 / time_axis.dt, 2e6, 3)
signals = jnp.expand_dims(sig, 0)                      # 2D (1, Nt)
sources = jw.Sources(positions, signals, time_axis.dt, domain)  # 4 位置参数

p = jw.simulate_wave_propagation(medium, time_axis, sources=sources, settings=S).params
# p.shape = (Nt, Nx, Ny, 1)，取点用 p[t_idx, x_idx, y_idx, 0]
maxp = float(jnp.max(jnp.abs(p)))
```

### Medium 类

`Medium` 定义介质物理属性：声速、密度、衰减、PML 厚度。几乎所有求解器都要传入。

**Import**: `from jwave import Medium`（或 `from jwave.geometry import Medium`）

| 属性/方法 | 说明 |
|-----------|------|
| `sound_speed` / `density` | 标量或 Field（异质介质用 FourierSeries 数组） |
| `attenuation` | 衰减系数（dB，幂律 y=2）；**仅频域 helmholtz_solver 生效，时域忽略** |
| `pml_size` | PML 层数（网格）；2D/3D 建议 8-20 |

```python
domain = jw.Domain((128, 128), (0.1e-3, 0.1e-3))
medium = jw.Medium(domain, sound_speed=1500.0, density=1000.0, pml_size=20)
```

**物理区注意**：PML 在各向边缘各占 pml_size 网格，物理区半径 = N/2 − pml_size（网格）。
探针/初始场/环形半径必须小于此值，否则被 PML 吸收（压力全零或幅度失真）。

### Domain 类

`Domain` 定义计算域尺寸与网格间距，维度 = 网格维度（2D 或 3D）。

**Import**: `from jwave import Domain`

```python
# 2D
domain = jw.Domain((Nx, Ny), (dx, dy))
# 3D（P1 扩展）：dx 可标量或列表
domain = jw.Domain((N, N, N), (dx, dx, dx))
```

**3D 内存红线**：全场 float32 = N³ × Nt × 4B。executor 上限 4GB：
N=72 约 1.1GB 安全；N=96 约 2.7GB 接近上限；N=128 超限。
建议 3D 时 N ≤ 72，或缩短 t_end。

### TimeAxis 类

`TimeAxis` 定义时间跨度与步长，由介质 + CFL 自动计算。

**Import**: `from jwave import TimeAxis`

```python
time_axis = jw.TimeAxis.from_medium(medium, cfl=0.1, t_end=40e-6)
t = time_axis.to_array()     # 时间数组（注意：没有 .t 属性！）
dt = time_axis.dt
Nt = time_axis.Nt            # 时间步数
```

CFL=0.1 细时间采样可保证峰值测量精度（VAL-1 实测口径）。

### Sources 类（点源）

**Import**: `from jwave import Sources`

**⚠️ 已验证的 3 条铁律（违反会静默出错 → 压力场全零）**：
1. **4 个位置参数**，不能用关键字：`Sources(positions, signals, dt, domain)`
2. **positions 必须是整数坐标**：`(jnp.array([64]), jnp.array([64]))`
   —— 浮点坐标在 JIT 中被吞没，`src.at[pos].add()` 静默失败 → 全零！
3. **signals 必须是 2D jnp array**：`jnp.expand_dims(sig_1d, 0)` → shape (num_sources, Nt)
   —— list/tuple 会 TypeError

```python
positions = (jnp.array([64]), jnp.array([64]))     # 2D 点源
# 3D: positions = (jnp.array([64]), jnp.array([64]), jnp.array([64]))
sig = jw.signal_processing.tone_burst(1.0 / dt, 2e6, 3)
signals = jnp.expand_dims(sig, 0)
sources = jw.Sources(positions, signals, dt, domain)
```

### p0 初始压力（高斯/环形/椭圆）

用 `p0` 关键字传初始压力场（`FourierSeries`），**不存在 `initial_pressure=` 参数**。

```python
import jax.numpy as jnp
from jaxdf import FourierSeries

x = jnp.linspace(0, Nx * dx, Nx); y = jnp.linspace(0, Ny * dx, Ny)
XX, YY = jnp.meshgrid(x, y, indexing="ij")   # 必须 indexing='ij'

# 高斯（cx, cy = 中心网格坐标；sigma 标准宽 m）
p0_grid = A * jnp.exp(-((XX - cx * dx) ** 2 + (YY - cy * dx) ** 2) / (2 * sigma ** 2))

# 环形（R0 环半径，须 < 物理区半径 N/2 - pml_size）
r = jnp.sqrt((XX - cx * dx) ** 2 + (YY - cy * dx) ** 2)
p0_grid = A * jnp.exp(-((r - R0) ** 2) / (2 * sigma ** 2))

# 椭圆（a、b 长短半轴）
p0_grid = A * jnp.exp(-(((XX - cx * dx) / a) ** 2 + ((YY - cy * dx) / b) ** 2) / 2)

p0 = FourierSeries(p0_grid, domain)
p = jw.simulate_wave_propagation(medium, time_axis, p0=p0, settings=S).params
```

3D 高斯球：`XX, YY, ZZ = jnp.meshgrid(x, y, z, indexing="ij")`，
`p0_grid = A * exp(-((XX-cx*dx)**2 + (YY-cy*dx)**2 + (ZZ-cz*dx)**2) / (2*sigma**2))`。

### simulate_wave_propagation 函数（时域主入口）

**Import**: `from jwave import simulate_wave_propagation`

```python
p = jw.simulate_wave_propagation(
    medium, time_axis,
    sources=sources,      # 或 p0=p0（二选一）
    settings=S,           # TimeWavePropagationSettings(smooth_initial=False)
).params
# p.shape = (Nt, Nx, Ny, 1) 2D；(Nt, Nx, Ny, Nz, 1) 3D
```

要点：
- `smooth_initial=False`：默认 True 会对 p0 做 Blackman 低通滤波，破坏解析对照
- 返回全场时 `params` 轴序 = (Nt, Nx, Ny, [Nz,] 1)，axis0=x、axis1=y（PML 在边缘）
- `sensors` 参数位置约定有歧义，**推荐直接取全场按索引取点**
- 时域求解器**忽略** `Medium.attenuation`（衰减要用频域 helmholtz_solver）

### tone_burst 信号（最常用激励）

**Import**: `from jwave.signal_processing import tone_burst`

```python
sig = jw.signal_processing.tone_burst(1.0 / dt, f0, 3)  # (采样率, 频率Hz, 周期数)
signals = jnp.expand_dims(sig, 0)  # 补齐为 2D (1, Nt)
```

- `num_cycles=3` 常用（平衡时/频分辨率）；宽带场景 1-2；窄带 5-10
- 用 `sources` 时 signals 必须补齐到 Nt 长度（越界索引静默出错）

### helmholtz_solver 函数（频域，含介质衰减）

**Import**: `from jwave.acoustics import helmholtz_solver, db2neper`

```python
omega = 2 * jnp.pi * f0
medium = jw.Medium(domain, sound_speed=c0, density=1000.0,
                   attenuation=alpha_db, pml_size=20)  # alpha_db 单位 dB，幂律 y=2
src = jw.FourierSeries(jnp.zeros((N, N), dtype=jnp.complex64).at[c, c].set(1.0), domain)
u = helmholtz_solver(medium, omega, src, method="gmres")
p = jnp.asarray(u.on_grid).reshape(N, N)   # 复压力场，取模 jnp.abs(p)
```

要点：
- **source 必须是 FourierSeries**（不能传裸数组）
- 衰减理论：`Im(k) = omega**2 * db2neper(alpha_db, 2.0)`（neper/m），
  振幅沿 r 按 `exp(-Im(k)*r)` 衰减（2D 再乘圆柱扩散 1/sqrt(r)）
- `method='gmres'` 稳定优先；收敛慢可试 `'bicgstab'`

### 异质介质（空间变化声速/密度）

`Medium` 的 sound_speed / density 可传与域同形的数组（Field）：

```python
c_map = jnp.full((N, N), 1540.0)
# 圆形囊肿：内部 1420
r = jnp.sqrt((XX - cx * dx) ** 2 + (YY - cy * dx) ** 2)
c_map = jnp.where(r < R_cyst, 1420.0, c_map)
medium = jw.Medium(domain, sound_speed=c_map, density=1000.0, pml_size=20)
```

**注意**：Field 形式的声速/密度会影响求解器分支（走 FourierSeries 版本），
异质场边界要平滑过渡（避免阶梯跳变引入伪影），点源仍用 `Sources`。

### 禁止 API 黑名单（LLM 常编造，必须避免）

| 错误写法 | 正确写法 |
|---------|---------|
| `p0.shape` | `p0.params.shape` |
| `p0.data` | `p0.params` |
| `time_axis.t` / `time_axis.time` | `time_axis.to_array()` |
| `FourierSeries.from_array(data, domain)` | `FourierSeries(data, domain)` |
| `Sources(domain=..., source=...)` | `Sources(positions, signals, dt, domain)` |
| `signals=[sig]`（list） | `jnp.expand_dims(sig, 0)` |
| `positions=[(64,64)]`（list of tuples） | `(jnp.array([64]), jnp.array([64]))` |
| `positions=(jnp.array([64.0]), ...)` | 整数坐标 `jnp.array([64])` —— 浮点→全零！ |
| `initial_pressure=` 参数 | `p0=` 关键字 |
| `jw.Sensors` 传 positions 采样 | 直接取全场 `p[t, x, y, 0]` |

### 物理规则速查（验证基准 VAL-1 实测）

- **Nyquist**：dx ≤ λ/4（每波长 ≥ 8 点），λ = c/f。例：2MHz 水中 λ=0.75mm，dx ≤ 0.19mm
- **CFL**：cfl ≤ 0.3（建议 0.1 保证峰值采样精度）
- **PML**：pml_size 建议 10-20；物理区半径 = N/2 − pml_size，探针/初始场须在物理区内
- **传播距离匹配**：t_end × c ≈ 域尺寸量级；t_end 太短看不到波传播，太长波被 PML 吸收
- **3D 内存**：N³ × Nt × 4B ≤ ~2GB（executor 4GB 上限），建议 N ≤ 72
- **衰减**：时域忽略 attenuation；频域 helmholtz_solver 才生效，Im(k)=ω²·db2neper(α,2)
- **几何扩散**：2D 点源 1/√r，3D 点源 1/r（验证误差 <0.1%）

### 常见问题（troubleshooting）

| 症状 | 原因 | 修法 |
|------|------|------|
| 压力场全零 | Sources 坐标浮点 / signals 非2D / 环形半径超域被 PML 吸收 | 整数坐标；expand_dims；半径 < N/2 − pml_size |
| 幅度异常偏小 | 探针放进 PML 吸收层 | 探针须在物理区（半径 N/2 − pml_size 内） |
| 衰减没效果 | 用了时域 simulate_wave_propagation | 改频域 helmholtz_solver + Medium(attenuation=...) |
| 代码执行 SyntaxError | 输出被 markdown 包裹 | 代码生成不要 ``` 包裹 |
| embedding 检索偶发失败 | tongyi API 抖动 | 重试即可（非代码问题） |
| 3D 内存不足 OOM | N 太大 | N ≤ 72 或缩短 t_end |

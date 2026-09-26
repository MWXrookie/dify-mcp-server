# jwave 仿真物理规则（数值与物理红线）

> 面向 LLM 代码生成：避免生成"数值上能跑但物理上错误"的仿真。
> 全部规则来自 VAL-1 验证基准（5 用例误差 <1% 的实测结论）与踩坑记录。
> 修改记录：2026-08-18 新建（含 3D/衰减扩展实测）。

### 网格与稳定性规则

1. **Nyquist 条件**：每波长至少 8 个网格点（dx ≤ λ/4）。
   - λ = sound_speed / frequency
   - 违反后果：色散失真、伪影、结果不可信
2. **CFL 条件**：cfl ≤ 0.3（推荐 0.1）。
   - cfl 过大 → 数值不稳定（发散）
   - cfl=0.1 保证峰值测量采样精度（VAL-1 口径）
3. **网格尺寸**：N ∈ [32, 1024]；FFT 友好尺寸（最小质因数 ≤7，如 128/192/200/224/256）。
4. **3D 内存**：全场 float32 = N³ × Nt × 4B；executor 4GB 上限 → N ≤ 72 安全。

### PML 边界规则（重要踩坑）

1. **物理区半径 = N/2 − pml_size（网格）**。
   - PML 在各向边缘各占 pml_size 网格，是吸收层，**不是物理区域**。
2. **探针/初始场/环形半径必须 < 物理区半径**。
   - 踩坑实证：N=56/pml=8 时物理区仅 10mm；把探针放 18mm 处 → 振幅被吸收 16×，
     1/r 衰减验证误差 94.5% → 修正后 0.009%。
3. pml_size 建议 10~20（2D）、8~10（3D 内存受限）。

### 激励规则

1. **Sources 点源**：4 位置参数 `Sources(positions, signals, dt, domain)`；
   positions 整数坐标；signals 2D array (num_sources, Nt)。
   - 浮点坐标 → JIT 静默吞没 → 压力场全零！
2. **p0 初始压力**：`p0=` 关键字传 FourierSeries；`smooth_initial=False`。
   - 默认 smooth_initial=True 会 Blackman 低通滤波，破坏解析对照。
3. **signals 补齐**：tone_burst 只有 ~150 采样，用 sources 时必须补齐到 Nt（越界静默出错）。

### 衰减规则（P1 新增，重要）

1. **时域 simulate_wave_propagation 忽略 Medium.attenuation**（源码确认）。
   - 想看到衰减效果必须走频域 `helmholtz_solver`。
2. **频域衰减**：`Im(k) = omega**2 * db2neper(alpha_db, 2.0)`（neper/m）。
   - 振幅沿传播距离 r：`exp(-Im(k)*r)`。
   - 2D 再加圆柱扩散 `1/sqrt(r)`；3D 加球面扩散 `1/r`。
3. **衰减单位**：dB，幂律 y=2（k-Wave 约定），经 db2neper 换算为 neper。

### 几何扩散验证（VAL-1 实测）

| 维度 | 点源远场规律 | 验证误差 |
|------|-------------|---------|
| 2D | 振幅 ∝ 1/√r（圆柱波） | 0.80% |
| 3D | 振幅 ∝ 1/r（球面波） | 0.009% |
| 均匀介质平面波 | 振幅守恒（A(x2)/A(x1)=1） | 0.0002% |
| 界面 R/T | 声阻抗公式（Z=ρc） | 0.003% |

### 结果可信度检查清单（生成代码后自查）

- [ ] dx ≤ λ/4（每波长 ≥8 点）
- [ ] cfl ≤ 0.3（用 0.1）
- [ ] 探针/初始场在物理区内（半径 N/2 − pml_size）
- [ ] 点源坐标是整数
- [ ] signals 是 2D array 且长度 = Nt
- [ ] 3D 时 N ≤ 72
- [ ] 含衰减需求时用 helmholtz_solver（非时域）
- [ ] smooth_initial=False

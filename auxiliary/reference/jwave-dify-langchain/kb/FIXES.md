# 知识库修改记录 (kb/jwave_kb_organized.md)

原文件已备份为 **`kb/jwave_kb_organized.md.bak`**（与用户原始
原始知识库逐字节相同；如需在作者环境复核，可设置 `JWAVE_ORIGINAL_KB`）。

修改由 `tools/fix_kb.py` 生成，**可完全回滚**：

```bash
python tools/fix_kb.py --check     # 只报告，不写入
python tools/fix_kb.py             # 重新应用（幂等）
python tools/fix_kb.py --revert    # 从 .bak 还原
```

## 为什么要改

原知识库是按「较老/略有差异」的 jwave 版本写的。经与环境中实际安装的
**`jwave 0.2.1` + `jax 0.10.0`** 逐条比对，有下列写法在本环境**不存在**，
会让生成出来的脚本必然报错：

| 原写法 | 实际正确写法 | 说明 |
|--------|--------------|------|
| `jw.np.array` / `jw.np.abs` / `jw.np.pi` / `jw.np.expand_dims` | `jnp.*`（`import jax.numpy as jnp`） | `jwave` 顶层没有 `np` 属性 |
| `jw.show_field(...)` | `jw.utils.show_field(...)` | 该函数在 `jwave.utils`，非顶层导出 |
| `jw.display_complex_field(...)` | `jw.utils.display_complex_field(...)` | 同上 |
| `jw.TimeHarmonicSource(domain, [(64,64)], [1.0], omega=omega)` | `jw.TimeHarmonicSource.from_point_sources(domain, x=[64], y=[64], value=[1.0], omega=omega)` | 真实签名为 `TimeHarmonicSource(amplitude, omega, domain)`，示例调用方式会 `TypeError` |
| 直接把自己的 `TimeHarmonicSource` 传给 `helmholtz_solver` | 先构造 **OnGrid** 源：`FourierSeries(数组, domain)` 再传入 | `helmholtz_solver(medium, omega, source: OnGrid)` 只接受 `OnGrid` |
| `jw.utils.display_complex_field(field, title='...')` | `jw.utils.display_complex_field(field)` | 该函数签名里没有 `title` 参数 |

> 注意：知识库里「函数说明表」中列出的 `Import: from jwave.utils import show_field`
> 等本来就**是对的**，只是示例代码没跟上——本次修改只是让示例与文档自洽。

## 具体改动清单（共 24 处）

| # | 数量 | 改动 |
|---|------|------|
| 1 | 6 | `jw.np.*` → `jnp.*` |
| 2 | 2 | `jw.show_field` → `jw.utils.show_field` |
| 3 | 2 | `jw.display_complex_field` → `jw.utils.display_complex_field` |
| 4 | 8 | 在使用 `jnp.` 但未 import 的 python 代码块中补 `import jax.numpy as jnp` |
| 5 | 1 | `TimeHarmonicSource` 使用示例改用 `from_point_sources(...)` |
| 6 | 1 | 「频域仿真全流程」示例改用 `FourierSeries(...)` 构造 OnGrid 源 |
| 7 | 2 | 去掉 `display_complex_field` 不支持的 `title=` 参数 |
| 8 | 1 | 澄清 `simulate_wave_propagation` 的**返回值**：默认（不传 `sensors`）返回的就是**压力场 `p`**，无需再次 `pressure_from_density` |
| 9 | 1 | 澄清 `tone_burst` 第一个参数是**采样频率 `1/dt`**，不是 `dt` |

## 真实试运行后补充的 2 处（第 8、9 条）

用真实 DeepSeek 模型跑通一次全流程后发现：第 5 轮才收敛，且最终「成功」的代码里有两处
**不报错但语义不对**的写法，正是知识库表述不够醒目导致的：

```python
rho = simulate_wave_propagation(medium, time_axis, sources=sources)
pressure = pressure_from_density(rho, medium)      # ❌ 默认返回的就是压力场，这是二次转换
source_signal = tone_burst(time_axis.dt, f0, 3)    # ❌ 第一个参数是采样频率，应为 1/dt
```

> 说明：循环的退出条件是「`stderr` 为空」，即**只保证能跑通、不报错**，并不校验物理正确性
> （与原 Dify 工作流完全一致）。所以这两条澄清能减少无谓迭代，但不能替代正确性校验。

## 验证

修改后已实测通过：

* `jwave 0.2.1` 顶层 API 审计：**0 个不存在的 `jw.*` 引用**
* 知识库内 15 个 python 代码块：**0 个语法错误**
* 「典型工作流 — 时域仿真全流程」示例：**实跑通过**（CPU 后端，耗时约 10s）
* 「典型工作流 — 频域仿真全流程」示例：**实跑通过**（CPU 后端，GMRES 求解）

> 运行生成的 jwave 代码时请设置 `JAX_PLATFORMS=cpu`：本机默认走 CUDA 会段错误
> （工作流已通过 `EXEC_ENV` 默认注入该变量）。

# 10 条 Dify 工作流自然语言声学测试

> 执行时间: 2026-08-09 04:46:15

## 汇总

| 指标 | 值 |
|------|-----|
| 总数 | 10 |
| 成功 | 10 |
| 失败 | 0 |
| 成功率 | 100.0% |

## 明细

| # | 场景 | 结果 | exit | 重试 | 最大压力 | 耗时 |
|---|------|------|------|------|---------|------|
| 1 | 基础点源 | ✅ | 0 | 1 | 0.496991 | 16.049s |
| 2 | 高斯p0 | ✅ | 0 | 1 | 0.305236 | 67.006s |
| 3 | 异质囊肿 | ✅ | 0 | 1 | 0.414201 | 50.793s |
| 4 | 传感器阵列 | ✅ | 0 | 1 | 0.305236 | 19.404s |
| 5 | 参数不合理 | ✅ | 0 | 1 | 0.494875 | 15.355s |
| 6 | 低频长波 | ✅ | 0 | 2 | 0.23108 | 20.179s |
| 7 | 高分辨率 | ✅ | 0 | 2 | 0.248941 | 40.443s |
| 8 | 骨样异质 | ✅ | 0 | 2 | 0.474725 | 114.458s |
| 9 | 边界靠近 | ✅ | 0 | 1 | 0.37727 | 17.257s |
| 10 | 修正重试 | ✅ | 0 | 2 | 770.71344 | 43.045s |

## 缓存前后

- before: {"total_entries": 0, "total_hits": 0, "total_successes": 0, "overall_hit_rate": 0.0, "top_entries": []}
- after: {"total_entries": 2, "total_hits": 3, "total_successes": 3, "overall_hit_rate": 100.0, "top_entries": [{"signature": "TypeError|general|--------------------", "hint": "import jax\nimport jax.numpy as jnp\nfrom jwave import FourierSeries\nfrom jwave.geometry import Domain, Medium, TimeAxis, Sources\nfrom jwave.acoustics import simulate_wave_propagation\n\n# Simulation parameters\nNx, Ny = 256, 256\ndx = 0.02 / Nx\nsound_speed = 1540.0\ndensity = 1050.0\ncfl = 0.3\nt_end = 1.3e-5  # time for wave to cross 2 cm domain at background speed\nfreq = 2e6  # 2 MHz ultrasound frequency\n\n# Domain and medium\ndomain = Domain(N=(Nx, Ny), dx=(dx, dx))\nmedium = Medium(domain=domain, sound", "hits": 2, "confidence": 1.0}, {"signature": "TypeError|general|raise _invalid_shape_error(shape, context)", "hint": "import jax\nimport jax.numpy as jnp\nfrom jwave import FourierSeries\nfrom jwave.geometry import Domain, Medium, TimeAxis, Sources\nfrom jwave.acoustics import simulate_wave_propagation\n\n# 定义仿真参数\nsound_speed = 1500.0\ndensity = 1000.0\nsource_frequency = 2000000.0\nNx, Ny = 128, 128\ndx = 0.0001\nt_end = 5e-6\ncfl = 0.3\n\n# 创建域和介质\ndomain = Domain(N=(Nx, Ny), dx=(dx, dx))\nmedium = Medium(domain=domain, sound_speed=sound_speed, density=density)\n\n# 创建时间轴\ntime_axis = TimeAxis.from_medium(medium, cfl=cfl, t_end", "hits": 1, "confidence": 1.0}]}
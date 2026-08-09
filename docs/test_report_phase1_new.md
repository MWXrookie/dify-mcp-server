# 阶段一 · T-006 新题 50 次端到端回归测试报告

> 测试时间: 2026-08-09 05:33:53 | 输入方式: Dify 工作流自然语言声学问题

## 总体结果

| 指标 | 值 |
|------|-----|
| 总测试数 | 50 |
| 成功 | 48 |
| 失败 | 2 |
| **成功率** | **96.0%** |
| 门禁标准 | ≥ 90% |
| 门禁结果 | ✅ 通过 |

## 按类别统计

| 类别 | 成功/总数 | 成功率 | 平均耗时 | 平均重试次数 |
|------|-----------|--------|----------|-------------|
| 2D均质点源 | 10/10 | 100% | 3049 ms | 1.00 |
| 2D均质初始压力 | 8/10 | 80% | 3306 ms | 2.90 |
| 2D异质介质 | 10/10 | 100% | 4003 ms | 1.30 |
| 传感器记录 | 10/10 | 100% | 3376 ms | 1.70 |
| 边界情况 | 10/10 | 100% | 2962 ms | 1.00 |

## 全部测试明细

| # | 类别 | Prompt (截断) | 结果 | 最大压力 | 耗时 | 重试 | 备注 |
|---|------|-------------|------|---------|------|------|------|
| 1 | 2D均质点源 | 在均匀水介质中模拟1.2 MHz点声源从计算域中心向外传播，声速1500 m/s，密... | ✅ | 0.3392 | 2742ms | 1 |  |
| 2 | 2D均质点源 | 做一个软组织中点声源传播仿真：声源频率2.4 MHz，声速1540 m/s，网格19... | ✅ | 0.4158 | 3036ms | 1 |  |
| 3 | 2D均质点源 | 二维均匀介质声波传播：中心点声源频率800 kHz，声速1480 m/s，网格128... | ✅ | 0.4261 | 2764ms | 1 |  |
| 4 | 2D均质点源 | 请仿真一个3 MHz点声源在水中传播，计算区域0.8cm x 0.8cm，网格224... | ✅ | 0.3838 | 3172ms | 1 |  |
| 5 | 2D均质点源 | 在1.5cm正方形区域中放置一个中心点声源，频率1.6 MHz，介质均匀声速1520... | ✅ | 0.4393 | 2946ms | 1 |  |
| 6 | 2D均质点源 | 模拟一个2.8 MHz的超声点源在均匀软组织中传播，声速1540 m/s，密度105... | ✅ | 0.4296 | 4044ms | 1 |  |
| 7 | 2D均质点源 | 均匀介质声场测试：点声源位于区域中心，频率1 MHz，声速1500 m/s，网格96... | ✅ | 0.3761 | 2614ms | 1 |  |
| 8 | 2D均质点源 | 请生成中心点声源的二维传播结果：频率2 MHz，声速1490 m/s，网格220x2... | ✅ | 0.3659 | 3324ms | 1 |  |
| 9 | 2D均质点源 | 水中点源仿真，频率1.75 MHz，区域1.4cm x 1.4cm，网格200x20... | ✅ | 0.4170 | 3108ms | 1 |  |
| 10 | 2D均质点源 | 做一个快速基准仿真：均匀介质，中心点声源2.2 MHz，网格144x144，区域1c... | ✅ | 0.4847 | 2739ms | 1 |  |
| 11 | 2D均质初始压力 | 模拟圆形高斯初始压力p0在均匀水介质中的传播，峰值800 Pa，标准宽度0.4mm，... | ✅ | 694.3859 | 3170ms | 2 |  |
| 12 | 2D均质初始压力 | 用初始压力场作为声源：中心高斯压力峰值1200 Pa，半宽0.7mm，软组织声速15... | ✅ | 720.0000 | 3148ms | 1 |  |
| 13 | 2D均质初始压力 | 仿真一个偏离中心1mm的高斯p0初始压力脉冲，峰值600 Pa，半宽0.5mm，均匀... | ✅ | 97.4414 | 3233ms | 5 |  |
| 14 | 2D均质初始压力 | 二维p0声波传播：两个圆形高斯初始压力分别位于左右两侧，峰值500 Pa和700 P... | ✅ | 687.2679 | 3876ms | 2 |  |
| 15 | 2D均质初始压力 | 请模拟初始压力分布传播，p0为中心椭圆高斯，峰值900 Pa，长轴0.9mm短轴0.... | ✅ | 863.8523 | 3604ms | 2 |  |
| 16 | 2D均质初始压力 | 均匀介质中初始压力环形分布传播：环半径1.5mm，峰值400 Pa，声速1540 m... | ❌ | 0.0000 | 3396ms | 1 | ZERO_PRESSURE |
| 17 | 2D均质初始压力 | 模拟一个较弱的高斯初始压力脉冲，峰值250 Pa，半宽1mm，声速1500 m/s，... | ❌ | N/A | 2175ms | 8 | TypeError: simulate_wave_propagation() got an unexpected keyword argument 'initi |
| 18 | 2D均质初始压力 | p0初始条件测试：中心高斯峰值1500 Pa，半宽0.35mm，均匀介质声速1520... | ✅ | 1482.2086 | 3965ms | 3 |  |
| 19 | 2D均质初始压力 | 请仿真三个位于同一直线上的高斯初始压力点，峰值均为300 Pa，间距1mm，声速15... | ✅ | 48.2663 | 3420ms | 2 |  |
| 20 | 2D均质初始压力 | 模拟初始压力由一个宽高斯包络构成的声波传播，峰值1000 Pa，半宽1.2mm，网格... | ✅ | 868.2457 | 3068ms | 3 |  |
| 21 | 2D异质介质 | 模拟点声源穿过一个低声速圆形囊肿：背景声速1540 m/s，囊肿直径2.5mm且声速... | ✅ | 0.4444 | 3215ms | 1 |  |
| 22 | 2D异质介质 | 异质介质仿真：中心有一个3mm直径高声速包块，声速1800 m/s，背景1500 m... | ✅ | 0.4256 | 3653ms | 1 |  |
| 23 | 2D异质介质 | 模拟声波经过上下两层组织，上层声速1480 m/s，下层声速1650 m/s，点声源... | ✅ | 0.4008 | 3210ms | 2 |  |
| 24 | 2D异质介质 | 组织中有两个低声速囊肿，直径分别1.5mm和2mm，声速1450 m/s，背景154... | ✅ | 0.4538 | 5286ms | 1 |  |
| 25 | 2D异质介质 | 骨样区域散射仿真：右侧有一个矩形高声速区域2800 m/s，背景软组织1540 m/... | ✅ | 0.3588 | 3816ms | 1 |  |
| 26 | 2D异质介质 | 模拟一个椭圆形脂肪样低声速区域，长轴4mm短轴2mm，声速1400 m/s，背景15... | ✅ | 0.4959 | 7518ms | 1 |  |
| 27 | 2D异质介质 | 随机斑点异质介质：背景声速1500 m/s，叠加小幅空间扰动约±3%，中心点声源1.... | ✅ | 0.3302 | 3377ms | 1 |  |
| 28 | 2D异质介质 | 模拟声波从水进入软组织界面：左半区1500 m/s，右半区1540 m/s，点声源2... | ✅ | 0.4193 | 3037ms | 2 |  |
| 29 | 2D异质介质 | 含有三个小圆形高声速散射体的介质，散射体声速1700 m/s，背景1500 m/s，... | ✅ | 0.4536 | 3614ms | 1 |  |
| 30 | 2D异质介质 | 在中心圆形区域内声速逐渐从1450过渡到1600 m/s，背景1540 m/s，点声... | ✅ | 0.4176 | 3308ms | 2 |  |
| 31 | 传感器记录 | 模拟中心2 MHz点声源传播，并在右侧1mm、2mm、3mm三个位置放置传感器记录压... | ✅ | 0.3761 | 3103ms | 1 |  |
| 32 | 传感器记录 | 在均匀软组织中做传感器阵列仿真：中心1.5 MHz点声源，四个传感器位于上下左右各2... | ✅ | 0.3331 | 3161ms | 2 |  |
| 33 | 传感器记录 | 模拟一个2.2 MHz点声源，并在半径2.5mm圆周上放置6个传感器，记录各传感器峰... | ✅ | N/A | 3355ms | 1 |  |
| 34 | 传感器记录 | 线阵接收测试：点源频率1 MHz，在x轴正方向每隔0.8mm放置5个传感器，声速14... | ✅ | 0.2637 | 3093ms | 1 |  |
| 35 | 传感器记录 | 请仿真四角传感器检测中心点源，点源频率2.5 MHz，声速1500 m/s，网格19... | ✅ | 0.4354 | 3144ms | 1 |  |
| 36 | 传感器记录 | 传感器记录p0传播：中心高斯初始压力峰值700 Pa，半宽0.6mm，在距离中心2m... | ✅ | 692.2164 | 3682ms | 3 |  |
| 37 | 传感器记录 | 模拟点声源在含低声速囊肿介质中的传播，并在囊肿前后各放一个传感器比较波形，点源1.8... | ✅ | 0.4495 | 4555ms | 1 |  |
| 38 | 传感器记录 | 8通道接收阵列测试：中心2 MHz点声源，8个传感器沿一条水平线均匀分布，声速150... | ✅ | 0.3838 | 3198ms | 1 |  |
| 39 | 传感器记录 | 在区域左侧放置1.5 MHz点源，右侧竖直方向放置5个传感器形成线阵，均匀介质声速1... | ✅ | 0.4409 | 3528ms | 2 |  |
| 40 | 传感器记录 | 模拟近场传感器：点源2 MHz，传感器距离声源0.5mm、1mm、1.5mm，声速1... | ✅ | 0.3638 | 2944ms | 4 |  |
| 41 | 边界情况 | 低频大波长测试：200 kHz点声源在5cm x 5cm区域中传播，声速1500 m... | ✅ | 0.2612 | 2888ms | 1 |  |
| 42 | 边界情况 | 小网格快速测试：64x64网格，区域8mm x 8mm，中心1 MHz点声源，声速1... | ✅ | 0.4230 | 2483ms | 1 |  |
| 43 | 边界情况 | 短时传播测试：2 MHz点声源，网格200x200，区域1cm，声速1500 m/s... | ✅ | 0.3638 | 2634ms | 1 |  |
| 44 | 边界情况 | 长时间传播测试：800 kHz点声源，区域2cm x 2cm，网格160x160，声... | ✅ | 0.3567 | 2868ms | 1 |  |
| 45 | 边界情况 | 高频分辨率挑战：4 MHz点声源，区域1cm x 1cm，网格256x256，声速1... | ✅ | 0.4970 | 3744ms | 1 |  |
| 46 | 边界情况 | 超小区域测试：区域3mm x 3mm，网格192x192，中心3 MHz点声源，声速... | ✅ | 0.2117 | 3054ms | 1 |  |
| 47 | 边界情况 | 靠近边界的点声源：点源距离左边界0.8mm，频率1.5 MHz，网格200x200，... | ✅ | 0.2973 | 3090ms | 1 |  |
| 48 | 边界情况 | 大区域中等网格：区域4cm x 4cm，网格192x192，点源频率700 kHz，... | ✅ | 0.4762 | 3096ms | 1 |  |
| 49 | 边界情况 | 故意设置较粗网格：点源频率3 MHz，网格80x80，区域1cm x 1cm，声速1... | ✅ | 0.9227 | 2583ms | 1 |  |
| 50 | 边界情况 | 高声速介质边界测试：均匀介质声速2200 m/s，点源1.5 MHz，网格200x2... | ✅ | 0.3018 | 3178ms | 1 |  |

## 失败分析

### #16 2D均质初始压力

- **Prompt**: 均匀介质中初始压力环形分布传播：环半径1.5mm，峰值400 Pa，声速1540 m/s，网格200x200，区域1.2cm，模拟4微秒。
- **Workflow Status**: succeeded
- **Exit Code**: 0
- **Reason**: ZERO_PRESSURE
- **Stdout**: 压力场形状: (343, 200, 200, 1)
最大压力: 0.000000
最小压力: 0.000000

- **Stderr**: N/A

### #17 2D均质初始压力

- **Prompt**: 模拟一个较弱的高斯初始压力脉冲，峰值250 Pa，半宽1mm，声速1500 m/s，密度1000 kg/m^3，网格128x128，区域1cm，仿真3微秒。
- **Workflow Status**: succeeded
- **Exit Code**: 1
- **Reason**: TypeError: simulate_wave_propagation() got an unexpected keyword argument 'initial_pressure'
- **Stdout**: N/A
- **Stderr**: Traceback (most recent call last):
  File "/tmp/mcp-run-spcin7is/main.py", line 41, in <module>
    p = simulate_wave_propagation(medium, time_axis, initial_pressure=initial_pressure_series)
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/jwave/lib/python3.12/site-packages/plum/_function.py", line 395, in __call__
    return _convert(method(*args, **kw), return_type)
                    ^^^^^^^^^^^^^^^^^^^
  File "/opt/jwave/lib/python3

## 纠错经验缓存前后

- 测试前: `{"total_entries": 2, "total_hits": 3, "total_successes": 3, "overall_hit_rate": 100.0, "top_entries": [{"signature": "TypeError|general|--------------------", "hint": "import jax\nimport jax.numpy as jnp\nfrom jwave import FourierSeries\nfrom jwave.geometry import Domain, Medium, TimeAxis, Sources\nfrom jwave.acoustics import simulate_wave_propagation\n\n# Simulation parameters\nNx, Ny = 256, 256\ndx = 0.02 / Nx\nsound_speed = 1540.0\ndensity = 1050.0\ncfl = 0.3\nt_end = 1.3e-5  # time for wave to cross 2 cm domain at background speed\nfreq = 2e6  # 2 MHz ultrasound frequency\n\n# Domain and medium\ndomain = Domain(N=(Nx, Ny), dx=(dx, dx))\nmedium = Medium(domain=domain, sound", "hits": 2, "confidence": 1.0}, {"signature": "TypeError|general|raise _invalid_shape_error(shape, context)", "hint": "import jax\nimport jax.numpy as jnp\nfrom jwave import FourierSeries\nfrom jwave.geometry import Domain, Medium, TimeAxis, Sources\nfrom jwave.acoustics import simulate_wave_propagation\n\n# 定义仿真参数\nsound_speed = 1500.0\ndensity = 1000.0\nsource_frequency = 2000000.0\nNx, Ny = 128, 128\ndx = 0.0001\nt_end = 5e-6\ncfl = 0.3\n\n# 创建域和介质\ndomain = Domain(N=(Nx, Ny), dx=(dx, dx))\nmedium = Medium(domain=domain, sound_speed=sound_speed, density=density)\n\n# 创建时间轴\ntime_axis = TimeAxis.from_medium(medium, cfl=cfl, t_end", "hits": 1, "confidence": 1.0}]}`
- 测试后: `{"total_entries": 8, "total_hits": 18, "total_successes": 17, "overall_hit_rate": 94.4, "top_entries": [{"signature": "TypeError|general|--------------------", "hint": "import jax\nimport jax.numpy as jnp\nimport numpy as np\nfrom jwave import FourierSeries\nfrom jwave.geometry import Domain, Medium, TimeAxis, Sources\nfrom jwave.acoustics import simulate_wave_propagation\n\n# Simulation parameters\nsound_speed = 1540.0\ndensity = 1050.0\nsource_frequency = 1.5e6\ndomain_size = 0.015  # 1.5 cm\nNx = Ny = 200\ndx = domain_size / Nx\n\n# Create domain and medium\ndomain = Domain(N=(Nx, Ny), dx=(dx, dx))\nmedium = Medium(domain=domain, sound_speed=sound_speed, density=density)\n\n# ", "hits": 8, "confidence": 1.0}, {"signature": "TypeError|general|^^^^^^^^^^^^^^^^^^^^^^^^^", "hint": "import jax\nimport jax.numpy as jnp\nfrom jwave import FourierSeries\nfrom jwave.geometry import Domain, Medium, TimeAxis, Sources\nfrom jwave.acoustics import simulate_wave_propagation\n\n# Domain setup\nNx, Ny = 180, 180\ndx = 0.012 / 180  # 1.2cm / 180\ndomain = Domain(N=(Nx, Ny), dx=(dx, dx))\n\n# Medium (soft tissue)\nmedium = Medium(domain=domain, sound_speed=1540.0, density=1050.0)\n\n# Time axis\ntime_axis = TimeAxis.from_medium(medium, cfl=0.3, t_end=5e-6)\nt = time_axis.to_array()\n\n# Initial pressure:", "hits": 4, "confidence": 0.75}, {"signature": "TypeError|general|raise _invalid_shape_error(shape, context)", "hint": "import jax\nimport jax.numpy as jnp\nfrom jwave import FourierSeries\nfrom jwave.geometry import Domain, Medium, TimeAxis, Sources\nfrom jwave.acoustics import simulate_wave_propagation\n\n# 定义仿真参数\nsound_speed = 1500.0\ndensity = 1000.0\nsource_frequency = 2000000.0\nNx, Ny = 128, 128\ndx = 0.0001\nt_end = 5e-6\ncfl = 0.3\n\n# 创建域和介质\ndomain = Domain(N=(Nx, Ny), dx=(dx, dx))\nmedium = Medium(domain=domain, sound_speed=sound_speed, density=density)\n\n# 创建时间轴\ntime_axis = TimeAxis.from_medium(medium, cfl=cfl, t_end", "hits": 1, "confidence": 1.0}, {"signature": "ImportError|general|from jwave.acoustics.time_varying import _compute_wave_propagation", "hint": "import jax\nimport jax.numpy as jnp\nfrom jwave import FourierSeries\nfrom jwave.geometry import Domain, Medium, TimeAxis\nfrom jwave.acoustics import simulate_wave_propagation\n\n# Domain setup\nNx = Ny = 192\ndx = 0.015 / 192  # 1.5 cm / 192\ndomain = Domain(N=(Nx, Ny), dx=(dx, dx))\n\n# Medium properties (water)\nsound_speed = 1500.0\ndensity = 1000.0\nmedium = Medium(domain=domain, sound_speed=sound_speed, density=density)\n\n# Time axis\ncfl = 0.3\nt_end = 1e-5\ntime_axis = TimeAxis.from_medium(medium, cfl=cf", "hits": 1, "confidence": 1.0}, {"signature": "ValueError|general|raise ValueError(f\"Cannot broadcast to shape with fewer dimensions: {arr_shape=}", "hint": "import jax\nimport jax.numpy as jnp\nfrom jwave import FourierSeries\nfrom jwave.geometry import Domain, Medium, TimeAxis\nfrom jwave.acoustics import simulate_wave_propagation\n\n# 仿真参数\nsound_speed = 1500.0\ndensity = 1000.0\ndomain_N = (192, 192)\ndx = 0.012 / 192  # 1.2cm = 0.012m\nt_end = 4e-6\ncfl = 0.3\n\n# 创建域和介质\ndomain = Domain(N=domain_N, dx=(dx, dx))\nmedium = Medium(domain=domain, sound_speed=sound_speed, density=density)\n\n# 时间轴\ntime_axis = TimeAxis.from_medium(medium, cfl=cfl, t_end=t_end)\nt = tim", "hits": 1, "confidence": 1.0}]}`

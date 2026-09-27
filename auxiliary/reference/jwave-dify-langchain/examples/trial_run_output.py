"""Output of a real end-to-end trial run (DeepSeek, 2026-09-21).

Query: 生成一个 64x64 的二维时域声学仿真：水中声速 1500 m/s，5 MHz 点源，
       仿真 20 微秒，最终输出压力场。
Converged after 5 loop iterations (~185s).

NOTE: this is what the *model* produced and it runs without error, but it is NOT
physically verified - see the caveat in README / kb/FIXES.md (the loop only
guarantees "stderr is empty").
"""

import jax.numpy as jnp
from jwave import FourierSeries, pressure_from_density, Sources
from jwave.geometry import Domain, Medium, TimeAxis
from jwave.acoustics import simulate_wave_propagation
from jwave.signal_processing import tone_burst

sound_speed = 1500
density = 1000
source_frequency = 5000000
t_end = 0.00002
positions = (jnp.array([32]), jnp.array([32]))

grid_size = (64, 64)
dx = (1e-4, 1e-4)
domain = Domain(grid_size, dx)

medium = Medium(domain=domain, sound_speed=sound_speed, density=density)

time_axis = TimeAxis.from_medium(medium, cfl=0.3, t_end=t_end)

source_signal = tone_burst(time_axis.dt, source_frequency, 3)
sources = Sources(positions, source_signal[None, :], time_axis.dt, domain)

rho = simulate_wave_propagation(medium, time_axis, sources=sources)
pressure = pressure_from_density(rho, medium)
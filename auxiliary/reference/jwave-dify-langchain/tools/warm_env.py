#!/usr/bin/env python
"""Warm up the execution environment (matplotlib font cache + jax import).

Why: the workflow's loop condition is "stderr is empty".  The *first* time
matplotlib builds its font cache it prints

    Matplotlib is building the font cache; this may take a moment.

to stderr, which would look like a failure and trigger an unnecessary repair
round.  Running this once per machine removes that first-run blip.

    python tools/warm_env.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jwave_flow.config import Settings  # noqa: E402
from jwave_flow.executor import get_executor  # noqa: E402

WARMUP = """
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.figure()
plt.savefig("warmup.png")
plt.close("all")
import jax, jax.numpy as jnp
jnp.zeros((2, 2))
print("warmup ok:", jax.devices()[0])
"""


def main() -> int:
    settings = Settings.from_env(verbose=False)
    ex = get_executor(settings)
    try:
        result = ex.run(WARMUP)
    finally:
        ex.close()
    print(f"backend: {result.backend} | ok: {result.ok} | {result.execution_time:.1f}s")
    print("stdout:", result.stdout.strip())
    if result.stderr.strip():
        print("stderr:", result.stderr.strip())
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

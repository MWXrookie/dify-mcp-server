FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    MPLCONFIGDIR=/tmp/mpl \
    LD_LIBRARY_PATH=/opt/jwave/lib \
    PATH=/opt/jwave/bin:/usr/bin:/bin:/usr/sbin:/sbin

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libgomp1 \
        wget \
        libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

RUN wget -q https://repo.anaconda.com/miniconda/Miniconda3-py311_24.9.2-0-Linux-x86_64.sh -O /tmp/miniconda.sh \
    && bash /tmp/miniconda.sh -b -p /opt/jwave \
    && rm /tmp/miniconda.sh

# JAX via conda-forge (has matching jax+jaxlib, unlike PyPI)
RUN /opt/jwave/bin/conda install -y -c conda-forge \
        jax=0.4.35 \
        numpy=1.26 \
        scipy=1.14 \
        matplotlib=3.9 \
    && /opt/jwave/bin/conda clean -afy

# jwave via pip --no-deps (JAX already provided by conda above)
RUN /opt/jwave/bin/pip install --no-cache-dir --no-deps jwave==0.2.1

# Remaining pure-Python deps
RUN /opt/jwave/bin/pip install --no-cache-dir \
    jaxdf==0.2.8 \
    equinox==0.11.11 \
    jaxtyping==0.2.37 \
    plum-dispatch==2.9.0 \
    beartype \
    wadler-lindig \
    rich

RUN useradd --create-home --uid 10001 appuser
WORKDIR /app
COPY executor.py /app/executor.py
USER 10001:10001
CMD ["/opt/jwave/bin/python", "/app/executor.py"]

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    MPLCONFIGDIR=/tmp/mpl \
    LD_LIBRARY_PATH=/opt/jwave/lib

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 appuser

WORKDIR /app
COPY jwave-env.tar.gz /tmp/jwave-env.tar.gz
RUN mkdir -p /opt/jwave \
    && tar -xzf /tmp/jwave-env.tar.gz -C /opt/jwave \
    && /opt/jwave/bin/python /opt/jwave/bin/conda-unpack \
    && rm /tmp/jwave-env.tar.gz
COPY executor.py /app/executor.py
USER 10001:10001
CMD ["/opt/jwave/bin/python", "/app/executor.py"]

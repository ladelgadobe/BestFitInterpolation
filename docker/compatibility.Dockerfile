# Scientific system packages are installed into the official QGIS interpreter.
ARG QGIS_IMAGE
FROM ${QGIS_IMAGE}
USER root
ENV DEBIAN_FRONTEND=noninteractive PYTHONOPTIMIZE=0 PYTHONUNBUFFERED=1 QT_QPA_PLATFORM=offscreen
# Archived QGIS 3.30/3.32 images include a retired NodeSource repository.
# Node is unused by these Python tests; keep the QGIS and distribution repositories intact.
RUN rm -f /etc/apt/sources.list.d/nodesource.list /etc/apt/sources.list.d/nodesource.sources \
    && apt-get update && apt-get install --no-install-recommends -y \
    python3-numpy python3-scipy python3-pandas python3-sklearn \
    python3-matplotlib python3-gdal python3-pip xvfb \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
ENTRYPOINT []
CMD ["python3", "/workspace/scripts/run_qgis_tests.py", "--help"]

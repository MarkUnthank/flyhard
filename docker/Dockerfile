# syntax=docker/dockerfile:1
FROM runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404@sha256:4d1721e62b56d345c83b4fd6090664be6daf9312caab5b2e76f23d8231941851

ENV DEBIAN_FRONTEND=noninteractive \
    MUJOCO_GL=egl PYOPENGL_PLATFORM=egl \
    PYVISTA_OFF_SCREEN=true VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow \
    NVIDIA_DRIVER_CAPABILITIES=all \
    FLYHARD_CARLA_ROOT=/opt/carla \
    FLYHARD_MAX_RUNTIME_SECONDS=3600 \
    PYTHONPATH=/workspace/flyhard/src \
    PATH=/opt/flyhard-env/bin:${PATH}

RUN apt-get update && apt-get install -y --no-install-recommends \
      libegl1 libgl1 libopengl0 libgles2 libvulkan1 vulkan-tools \
      mesa-utils xvfb rsync ffmpeg git ca-certificates curl tini \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv --system-site-packages /opt/flyhard-env

# Keep the large simulator in its own immutable, cacheable layer.
RUN curl --fail --location --retry 3 --user-agent 'Mozilla/5.0 Flyhard/0.1' \
      https://downloads.carlasim.com/Linux/CARLA_0.9.16.tar.gz -o /tmp/carla.tar.gz \
    && printf '%s  %s\n' 09e3ebb28df17962f0c997e66f4b914ad5ea6f1d6a6dbbf13c9f87eb38346d57 /tmp/carla.tar.gz | sha256sum --check \
    && mkdir -p /opt/carla \
    && tar --no-same-owner -xzf /tmp/carla.tar.gz -C /opt/carla \
    && rm /tmp/carla.tar.gz \
    && test -x /opt/carla/CarlaUE4.sh \
    && id ubuntu

COPY pyproject.toml /opt/flyhard/pyproject.toml
COPY requirements/ /opt/flyhard/requirements/
COPY docker/install_environment.py /opt/flyhard/docker/install_environment.py
RUN python /opt/flyhard/docker/install_environment.py

COPY src/ /opt/flyhard/src/
COPY scripts/ /opt/flyhard/scripts/
COPY tests/ /opt/flyhard/tests/
COPY assets/fonts/ /opt/flyhard/assets/fonts/
COPY docker/ /opt/flyhard/docker/
COPY LICENSE THIRD_PARTY.md README.md /opt/flyhard/
# Keep changing source provenance out of the expensive dependency cache keys.
ARG SOURCE_REVISION=unknown
ENV FLYHARD_SOURCE_REVISION=${SOURCE_REVISION}
RUN python -m pip install --no-deps --no-cache-dir -e /opt/flyhard \
    && PYTHONPATH=/opt/flyhard/src python -m pytest -q /opt/flyhard/tests \
    && PYTHONPATH=/opt/flyhard/src python -c 'from flyhard.cockpit import WheelRig; r=WheelRig(support_hand=True); assert r.model.nbody == 54' \
    && python -m pip freeze > /opt/flyhard/environment.lock.txt \
    && python /opt/flyhard/docker/build_receipt.py

LABEL org.opencontainers.image.source="https://github.com/MarkUnthank/flyhard" \
      org.opencontainers.image.description="Flyhard: CARLA 0.9.16, PyTorch CUDA, NeuroMechFly, MuJoCo and CNS rendering" \
      org.opencontainers.image.revision=${SOURCE_REVISION}

WORKDIR /workspace/flyhard
EXPOSE 22
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/opt/flyhard-env/bin/python", "/opt/flyhard/docker/start.py"]

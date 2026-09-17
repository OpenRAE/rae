# Optional connected development environment. The artifact lock owns the base
# digest; this native Dockerfile owns its packages, account, and environment.
# Signed Ubuntu repositories supply current native packages. Rebuilds are not
# byte-reproducible and do not qualify additional host architectures.
# The lifecycle separately verifies locked uv, Python, and CLI payloads.
# Proof isolation and a container daemon are intentionally not supplied.
FROM --platform=linux/amd64 docker.io/library/ubuntu@sha256:a61567bd31828687156d735ea8eb01ba4e37636e225dd6a48ba94136a70d9d61
RUN set -eu; \
    export DEBIAN_FRONTEND=noninteractive; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        bash-completion \
        ca-certificates \
        coreutils \
        curl \
        gh \
        git \
        gnupg \
        jq \
        less \
        make \
        nano \
        openssh-client \
        procps \
        python3 \
        python3-jsonschema \
        python3-packaging \
        python3-yaml \
    ; \
    apt-get clean; \
    find /var/lib/apt/lists -mindepth 1 -delete

# A non-root development account owns the caches and never the mounted source.
# The base ships a stock account at 1000; replacing it keeps the
# development user aligned with the typical host owner of a bind-mounted
# checkout, and dev-container clients remap it to the host owner otherwise.
RUN set -eu; \
    userdel --remove ubuntu; \
    groupadd --gid 1000 raes; \
    useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash raes; \
    install -d -o raes -g raes /home/raes/.cache /home/raes/.cache/uv

# The locked uv client and CPython live in the cache volume once the lifecycle
# setup has verified them; uv never downloads an unreviewed interpreter.
ENV UV_CACHE_DIR=/home/raes/.cache/uv \
    XDG_CACHE_HOME=/home/raes/.cache \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=/home/raes/.cache/raes-bootstrap/python/current/bin/python3 \
    PATH=/home/raes/.cache/raes-bootstrap/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    EDITOR=nano \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

USER raes

# Reviewed RAES development container.
#
# This file owns no version, digest, package, or platform fact. Every literal
# below is derived from the reviewed `container-ubuntu-24.04-*` host profiles in
# implementations/tooling/profiles/development-profiles.json and from
# implementations/tooling/artifacts.lock.json; the drift gate in
# tools/tooling_artifact_policy_container.py refuses any literal here that
# disagrees with that authority, so edit the authority, never this file.
#
# The image supplies host prerequisites and maintainer conveniences only. The
# dev-container lifecycle runs `tools.devcontainer_setup`, which acquires the
# locked uv, CPython, and generic CLI payloads through the repository's own
# verified installers, so no payload, checkout, credential, or reusable cache is
# baked into a layer. Isabelle proof execution is unsupported here
# (`proof_support: unsupported`); use the native proof host profile.

# The package snapshot is served only over HTTPS and the pinned base carries no
# CA bundle. This throwaway stage obtains one from the base image's own signed
# archive purely as TLS transport trust; none of its bytes reach the image.
FROM docker.io/library/ubuntu@sha256:224a1869083a311ef3f13648a154ba79832fbef6364d31493642ca03082da254 AS transport-trust
RUN set -eu; \
    case "$(dpkg --print-architecture)" in amd64|arm64) ;; *) echo "no reviewed development container profile for this architecture" >&2; exit 1 ;; esac; \
    export DEBIAN_FRONTEND=noninteractive; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates

# Every installed package comes from the immutable reviewed snapshot and is
# authenticated by the Ubuntu archive keyring inside the digest-pinned base.
FROM docker.io/library/ubuntu@sha256:224a1869083a311ef3f13648a154ba79832fbef6364d31493642ca03082da254
RUN --mount=type=bind,from=transport-trust,source=/etc/ssl/certs/ca-certificates.crt,target=/run/raes-transport-ca.crt \
    set -eu; \
    export DEBIAN_FRONTEND=noninteractive; \
    apt-get -o APT::Snapshot=20260912T000000Z -o Acquire::https::CAInfo=/run/raes-transport-ca.crt update; \
    apt-get -o APT::Snapshot=20260912T000000Z -o Acquire::https::CAInfo=/run/raes-transport-ca.crt install -y --no-install-recommends \
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
# The reviewed base ships a stock account at 1000; replacing it keeps the
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

# Development container

The repository ships an optional connected development container with locked
Python/uv, frozen project and tooling environments, CLI tools and git hooks.
The bootstrap workflow exercises an x86_64 Docker build and repeated lifecycle
setup. Each start route below is labelled verified or unverified. The verified
entry points section records the host, client versions and results behind those
labels. A route is never labelled verified because a client can read
`devcontainer.json`.

The container is optional. Native setup, described in
[Contribute to RAES](../../CONTRIBUTING.md), stays fully supported.

## Open the repository in the container

Pick one:

- **Dev Containers CLI (verified):** `devcontainer up --workspace-folder .`,
  then `devcontainer exec --workspace-folder . bash`.
- **Docker without a dev-container client (verified):** see the section on
  running Docker or Podman directly.
- **VS Code (unverified):** install the Dev Containers extension, open the
  repository, and choose **Reopen in Container**. The extension reads the same
  `devcontainer.json`, and its interpreter and formatter paths resolve inside
  the built container. Nobody has exercised the editor route itself.
- **GitHub Codespaces (unverified):** on the repository page choose **Code**,
  then **Codespaces**, then **Create codespace**. The configuration asks for a
  4-core, 16 GB machine.

The first open builds the image and runs the repository setup. Setup prints each
step and finishes with `Ready.`:

1. confirms the reviewed container profile for the platform;
2. downloads and verifies the locked uv and CPython against the artifact lock;
3. syncs `implementations/python` and `implementations/tooling/python` from
   their `uv.lock` files;
4. downloads, verifies, and runs Conftest, Gitleaks, OSV-Scanner, and Vale;
5. installs the repository's file-hygiene and secrets pre-commit hook.

Reopening the container runs nothing again. Rebuilding it reruns setup against
the cache volume; duration depends on the host and available inputs. If setup fails, the message names the step
and the reason, and the container stays usable for investigation.

## Start working

Every terminal already has `uv`, `python`, `nox`, `pre-commit`, and `ruff` on
its path, alongside `git`, `gh`, `ssh`, `gpg`, `make`, `jq`, `less`, and `nano`.

```shell
nox -l                      # list every check
nox -s verify-changed       # optional change-aware local gate
nox -s tests                # unit tests
make policy                 # repository policy
```

Committing runs file-scoped hygiene and secrets checks, as on a native setup.
There is no configured pre-push hook. CI/CD runs the full validation and test
suites before merge.

## Git, signing, and GitHub

Ordinary Git use works in the verified routes. Reading history, staging files
and committing all run against the mounted checkout.

- **Dev Containers CLI and plain Docker (verified):** the container carries no
  Git identity of its own. Set `user.name` and `user.email` in the checkout
  before you commit, or let your client supply them.
- **VS Code (unverified):** the extension is documented to copy your Git
  identity into the container and to forward your SSH agent, credential helper
  and GPG agent. This repository has not exercised that path, so treat signing
  and SSH remotes as untested here.
- **Codespaces (unverified):** Codespaces is documented to authenticate Git and
  sign commits itself. This repository has not exercised that path.
- **GitHub CLI:** run `gh auth login` once. The container stores no token.

No authentication or signing matrix is claimed. The verified routes record only
what they observed.

## Supported platforms

The container is a **Linux x86_64 (`linux/amd64`)** image, qualified by a clean
native build in continuous integration. Every build stage pins the reviewed
`linux/amd64` base manifest, so any client builds the same image.

Native arm64 support and client/emulation behavior are not newly qualified by
this change. A native arm64 variant needs a reviewed image/interpreter tuple
and actual build/setup tests, **not** an immutable-package-snapshot service.
The current image remains linux/amd64. Native arm64, client emulation,
Codespaces and rootless Podman stay unverified until a run is recorded.

## Verified entry points

These results come from a single host on one day. They record what ran. They
are not a support matrix, and they do not qualify another client or platform.

- Source revision `803257b2`.
- Host: Ubuntu 24.04.4 LTS, `x86_64`, kernel 6.8.0-117.
- Container runtime: Docker 29.5.0. Client: Dev Containers CLI 0.89.0.

| Route | Result |
| --- | --- |
| `devcontainer up`, then `devcontainer exec` | Setup printed the five steps and finished `Ready. Git hooks: installed.` |
| `docker build` and `docker run`, as shown below | Setup finished `Ready. Git hooks: installed.` |
| VS Code, Codespaces, Apple Silicon emulation, rootless Podman | Not exercised. The host had no editor client, no display and no Podman. |

Inside the container the checkout was writable and owned by `raes` at uid 1000.
`uv`, `python`, `nox`, `pre-commit`, `ruff`, `git`, `gh`, `ssh`, `gpg`, `make`,
`jq`, `less` and `nano` were all on the path. The run recorded Python 3.14.7,
uv 0.12.4, ruff 0.15.9, nox 2026.4.10, git 2.43.0 and gh 2.45.0. It also
recorded Conftest 0.68.0, Gitleaks 8.30.1, OSV-Scanner 2.4.0 and Vale 3.15.2.
The interpreter and formatter paths that `devcontainer.json` gives an editor
all resolved.

A clean commit passed the installed hook. A commit that broke file hygiene was
repaired by the hook and stopped, as it does natively. The container held no
Docker or Podman client, no daemon socket and no `sudo`.

`nox -s verify-changed` ran in the container against a documentation change and
passed every selected lane in about seven minutes. That included the policy,
lint, contracts, test and docs lanes. Starting the container a second time ran
no setup steps again, as this page describes.

## What is in the image

- Ubuntu 24.04, pinned by its `linux/amd64` manifest digest.
- Native packages from the base image's signed Ubuntu repositories, authenticated
  by the Ubuntu archive keyring: the bootstrap prerequisites (`git`, `curl`, `gh`,
  `python3` with `jsonschema`, `packaging`, and `yaml`, CA certificates) and
  maintainer tools (`openssh-client`, `gnupg`, `less`, `nano`, `make`, `jq`,
  `procps`, `bash-completion`).
- A non-root `raes` account with no `sudo`.

The image contains no checkout, credentials, tokens, SSH material, virtual
environment, or payload cache. uv, CPython, and the CLI tools are downloaded
into the cache volume by the repository's verified installers, and uv is
forbidden from downloading any interpreter the lock did not admit.

The artifact lock owns the base digest and verified bootstrap payloads.
`.devcontainer/Dockerfile` owns native packages, account setup and environment;
`devcontainer.json` owns the client configuration. Focused checks keep the
locked platform/digest, non-root user and restricted runtime boundary. They do
not duplicate the whole Dockerfile as a policy language. Signed moving native
repositories mean image rebuilds are not byte-reproducible.

## Caches and rebuilds

The cache volume at `/home/raes/.cache` holds the uv cache and the verified
clients. It survives container rebuilds. It is never trusted: every setup
re-verifies each cached archive against the lock, downloads anything missing or
altered, and swaps in freshly installed clients only when every step succeeds.
To repeat setup at any time, run:

```shell
/usr/bin/python3 -m tools.devcontainer_setup
```

The project virtual environments live in the checkout, as they do natively.
Their console scripts record absolute paths, so a checkout mounted at a second
path carries scripts that cannot start. Setup detects a relocated environment
and rebuilds it, because `uv sync` alone reports it as already locked. Even so,
don't share one checkout between the container and a native setup: each would
rebuild the other's environment for its own platform. Use a separate clone for
each.

## Use Docker or Podman without a dev-container client

From the repository root:

```shell
docker build --tag raes-development .devcontainer
docker run --rm -it --volume "$PWD:/workspaces/rae" --workdir /workspaces/rae \
  --volume raes-development-cache:/home/raes/.cache raes-development
```

Then, inside the container, run setup once and put the tool environment on the
path of each new shell:

```shell
/usr/bin/python3 -m tools.devcontainer_setup
export PATH="$PWD/implementations/tooling/python/.venv/bin:$PATH"
```

Plain Docker doesn't remap user IDs, so the checkout must be owned by uid 1000.
The Docker route above is verified. Rootless Podman is unverified: add
`--userns=keep-id:uid=1000,gid=1000` to `podman run` if you try it.

Git worktrees whose `.git` file points outside the mounted directory can't be
used from the container. Setup still reaches `Ready.`, but it reports the hook
step as skipped, and Git reports a missing repository. Mount a plain clone
instead.

## Limitations

**No proof support.** The container profiles declare
`proof_support: unsupported`. Bubblewrap needs namespace privileges that an
unprivileged container does not grant, so `nox -s participant-opacity-proof`
stops with `bubblewrap is required to enforce offline proof replay` and never
skips the proof or relaxes its isolation. The full `nox -s verify` gate includes
that lane and fails in the container for the same reason; use `verify-changed`
while working and let continuous integration, or a native Linux x86_64 proof
host, run the full gate.

**No container daemon.** The image supplies development tools, not a Docker or
Podman daemon, and mounts no daemon socket. The optional
`nox -s integration_docker` lane remains a host-capability test.

**Not a production runtime.** The image exists to develop and verify the
repository.

## Update the image

Update the reviewed base index/platform digest in `artifacts.lock.json` and its
Dockerfile projection together. Update packages and account setup directly in
the Dockerfile, and client settings in `devcontainer.json`. No qualification
record hash needs renewal. Let the path-filtered/manual `development-image`
job build from an empty cache and exercise setup twice, ordinary checks and
the expected proof-capability refusal. Changes to supported entry points or
architectures need their own actual verification evidence.

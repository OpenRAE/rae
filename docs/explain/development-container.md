# Development container

The repository ships a ready-to-use development container. Open the repository
in it and, after a few minutes of automatic setup, you have everything a RAES
maintainer needs: the locked Python and uv, both project environments, the
repository's CLI tools, git hooks, and an editor already pointed at the right
interpreter and formatter. There are no setup commands to run.

The container is optional. Native setup, described in
[Contribute to RAES](../../CONTRIBUTING.md), stays fully supported.

## Open the repository in the container

Pick one:

- **VS Code:** install the Dev Containers extension, open the repository, and
  choose **Reopen in Container**.
- **GitHub Codespaces:** on the repository page choose **Code**, then
  **Codespaces**, then **Create codespace**. The configuration asks for a
  4-core, 16 GB machine.
- **Dev Containers CLI:** `devcontainer up --workspace-folder .`, then
  `devcontainer exec --workspace-folder . bash`.

The first open builds the image and runs the repository setup. Setup prints each
step and finishes with `Ready.`:

1. confirms the reviewed container profile for the platform;
2. downloads and verifies the locked uv and CPython against the artifact lock;
3. syncs `implementations/python` and `implementations/tooling/python` from
   their `uv.lock` files;
4. downloads, verifies, and runs Conftest, Gitleaks, OSV-Scanner, and Vale;
5. installs the repository's file-hygiene and secrets pre-commit hook.

Reopening the container runs nothing again. Rebuilding it reruns setup against
the cache volume in about a minute. If setup fails, the message names the step
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

- **VS Code** copies your git identity into the container and forwards your SSH
  agent, git credential helper, and GPG agent. SSH remotes and signed commits
  work when they work on your host; load your SSH key into the host's agent
  first.
- **Codespaces** authenticates git and signs commits itself when GPG
  verification is enabled for your account.
- **GitHub CLI:** run `gh auth login` once. The container stores no token.

## Supported platforms

The container is a **Linux x86_64 (`linux/amd64`)** image, qualified by a clean
native build in continuous integration. Every build stage pins the reviewed
`linux/amd64` base manifest, so any client builds the same image.

On **Apple silicon** and other arm64 hosts, Docker Desktop runs that same image
under emulation (Rosetta or QEMU), with no extra configuration. Expect builds and test
runs to be slower than native. A native arm64 image isn't offered because Ubuntu
publishes immutable package snapshots only for x86_64; building arm64 from the
moving ports archive would give up reproducible images. An arm64 variant can be
added as its own reviewed host profile once an immutable package source
exists.

## What is in the image

- Ubuntu 24.04, pinned by its `linux/amd64` manifest digest.
- Native packages from one immutable Ubuntu snapshot, authenticated by the
  Ubuntu archive keyring: the bootstrap prerequisites (`git`, `curl`, `gh`,
  `python3` with `jsonschema`, `packaging`, and `yaml`, CA certificates) and
  maintainer tools (`openssh-client`, `gnupg`, `less`, `nano`, `make`, `jq`,
  `procps`, `bash-completion`).
- A non-root `raes` account with no `sudo`.

The image contains no checkout, credentials, tokens, SSH material, virtual
environment, or payload cache. uv, CPython, and the CLI tools are downloaded
into the cache volume by the repository's verified installers, and uv is
forbidden from downloading any interpreter the lock did not admit.

Every version, digest, package, and architecture comes from
[`development-profiles.json`](../../implementations/tooling/profiles/development-profiles.json)
and [`artifacts.lock.json`](../../implementations/tooling/artifacts.lock.json)
through the `container-ubuntu-24.04-x86_64` host profile.
`tools/tooling_artifact_policy_container.py` and
`tools/tooling_artifact_policy_devcontainer.py` refuse any Dockerfile or
`devcontainer.json` value that disagrees with them, and refuse host-side
commands, extra environment, host mounts, and added container capabilities.

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
Don't share one checkout between the container and a native setup: each would
rebuild the other's `.venv` for its own platform. Use a separate clone for
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
With rootless Podman, add `--userns=keep-id:uid=1000,gid=1000` to `podman run`
instead. Git worktrees whose `.git` file points outside the mounted directory
can't be used from the container; setup skips hook installation for them.

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

The image follows its authorities, so an update is a reviewed change to them:

1. Change the base index digest and `linux/amd64` manifest in
   `artifacts.lock.json`, or the `native_repository_snapshot`, prerequisite
   packages, or `development_package_ids` in the container host profile. Pick a
   snapshot no older than the base image, or apt can't install packages that
   depend on its newer libraries.
2. Render the expected values with
   `python3 -m tools.devcontainer_image --host-profile-id container-ubuntu-24.04-x86_64`
   and apply them to `.devcontainer/Dockerfile`.
3. Regenerate the qualification records' `policy_sha256`.
4. Let the `development-image` job of the bootstrap qualification workflow
   build from an empty cache and exercise the lifecycle.

`make policy` refuses the change whenever the image and its authorities
disagree.

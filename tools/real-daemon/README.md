# libvirt backend — real-daemon smoke test

The hermetic `nox verify` graph exercises the libvirt/QEMU backend
(`raes_backend_libvirt`) through in-process fakes — it deliberately does **not**
require a real `libvirtd`, QEMU/KVM, or privileged host access (see the issue
#604 preflight note). This directory is the out-of-band counterpart: it runs the
backend against a **real libvirt daemon** so we can periodically confirm the
reconciliation/teardown behaviour actually works on real infrastructure.

## What it checks

`libvirt_smoke.py` drives `LibvirtDeploymentDriver` and `LibvirtProvisioner`
against `qemu:///system` and asserts, on real domains / networks / nwfilters:

- libvirt raises `VIR_ERR_NO_DOMAIN` (42) / `VIR_ERR_NO_NETWORK` (43) on missing
  lookups, and the driver's hardcoded codes match the installed `libvirt` module;
- CREATE realizes an active network + a running domain;
- UPDATE re-converges in place (no duplicate);
- teardown removes real objects with **no orphans**, and is idempotent
  (repeat teardown + never-realized teardown are clean no-ops);
- teardown of an already-inactive domain succeeds (`VIR_ERR_OPERATION_INVALID`
  on stop is benign);
- teardown refuses a foreign object at the same name (ownership fail-closed);
- nwfilters are owner-stamped on realize and undefined on teardown;
- a partial CREATE (define ok, start fails) is rolled back — no orphan;
- the provisioner CREATE → teardown → idempotent re-teardown path;
- a real cirros guest boots with a cloud-init seed ISO, then tears down cleanly.

The domain XML uses `<domain type="qemu">` (TCG software emulation), so **no
bare-metal or nested virtualization is required** — any x86 host with libvirt +
qemu + genisoimage works.

## Run it on AWS (ephemeral, self-cleaning)

```sh
SSH_INGRESS_CIDR=203.0.113.4/32 AWS_PROFILE=aws-dev AWS_REGION=us-east-1 \
  tools/real-daemon/run_aws_smoke.sh
```

`SSH_INGRESS_CIDR` is required: declare the reviewed CIDR allowed to reach the
instance on tcp/22 (there is no external checkip auto-detect). The reviewed base
image and native-package snapshot are pinned in `tools/tool_versions.py`
(`LIVE_RUNNER_UBUNTU_IMAGE_NAME`, `LIVE_RUNNER_NATIVE_SNAPSHOT`); the script
resolves them for your region rather than floating a "newest" AMI. It first
stages the admitted input closure locally through the tooling policy gate
(`tools/real-daemon/live_runner_inputs.py`): the pinned CirrOS guest disk
(`cirros-guest-disk` in `implementations/tooling/artifacts.lock.json`), the
locked `uv` client, the declared `cpython-3.14` interpreter, and the
`libvirt-python` build wheelhouse (sdist + pinned setuptools/wheel) are
downloaded once and verified against their reviewed digests. It then resolves the
reviewed Canonical image by exact name + owner, provisions a `c5.2xlarge`
instance whose APT is pinned to the immutable `snapshot.ubuntu.com` archive, pins
the instance host key from the authenticated AWS console output
(`StrictHostKeyChecking=yes`), transfers only Git-tracked source, **pre-seeds and
re-verifies** the inputs, installs `uv` and the validated `cpython-3.14`
interpreter from the pre-seeded payloads (no pipe-to-shell), runs
`uv sync --frozen` on that interpreter, installs `libvirt-python` **offline** from
the wheelhouse (`--offline --no-index --find-links --require-hashes`), runs the
smoke test against a scoped per-run directory under the libvirt images tree,
prints the `SUMMARY: N/N passed` line, and tears down the instance + security
group + key pair on exit. The host keeps its default security driver — no
`security_driver = "none"` and no root QEMU user/group. Pass `--keep` to leave
the instance up for manual inspection (remember to terminate it later).

Exit code is non-zero if any check fails; a setup timeout is a failure, not a
silently ignored step.

## Run it on any libvirt host

Copy `libvirt_smoke.py` next to an installed `raes_backend_libvirt` (with
`libvirt-python` available) on a host with libvirt/qemu/genisoimage. Place the
admitted CirrOS guest disk and run artefacts in a scoped directory **under the
libvirt images tree** so the daemon can reach them under its default security
driver, then point the harness at them:

```sh
RUN_DIR=/var/lib/libvirt/images/raes-run/$(id -un)-$$
sudo install -d -m 0711 -o "$(id -un)" -g "$(id -un)" "$RUN_DIR"
install -m 0644 cirros-0.6.2-x86_64-disk.img "$RUN_DIR/cirros.img"
RAES_LIBVIRT_RUN_DIR="$RUN_DIR" \
  RAES_CIRROS_IMAGE="$RUN_DIR/cirros.img" \
  RAES_CIRROS_SHA256=07e44a73e54c94d988028515403c1ed762055e01b83a767edf3c2b387f78ce00 \
  RAES_CIRROS_SIZE=21430272 \
  python real_daemon_smoke.py   # or: python libvirt_smoke.py
```

The harness re-verifies the image against `RAES_CIRROS_SHA256`/`RAES_CIRROS_SIZE`
before booting it and renders the guest disk overlay and cloud-init seed inside
`RAES_LIBVIRT_RUN_DIR`, so no `security_driver = "none"` or root QEMU
user/group override is needed. Keeping the run directory under
`/var/lib/libvirt/images` lets libvirt dynamically label the disk/seed under the
default AppArmor confinement.

## Guest-certified realization proof (ASR-519, issue #715)

`libvirt_smoke.py` proves substrate reconciliation/teardown at the *daemon* level.
The **guest-certified** proof goes one layer deeper: it boots a guest-observing
appliance through the production apply path and reads concern facts back **from
inside the guest** (resource allocation, network addressing, file content, and
service state), freshness-bound to a per-run challenge, then verifies teardown.
Domain existence alone never satisfies it.

The generated appliance requires a **static x86_64 BusyBox** named `busybox` on
the command's `PATH` (on Ubuntu, install `busybox-static`) and a readable kernel
at the configured/default kernel path. The driver validates both before opening
libvirt. It encodes `newc` itself, so no host `cpio` executable is required.

The reproducible operator/self-hosted command is:

```sh
# Against a real libvirt/QEMU daemon (qemu:///system). Boots the appliance,
# certifies from inside the guest, writes a machine-readable evidence artifact,
# and returns non-zero on any failed stage.
raes libvirt techvault guest-certify \
  --scenario examples/scenarios/techvault-guest-certified.sdl.yaml \
  --project-dir . --run-id guest-proof-1 --yes
```

It emits the `raes.libvirt.scenario-evidence-run/v1` artifact under
`runs/<run-id>/scenario-evidence/libvirt-scenario-evidence-run.json`. The artifact
is validated (source separation, binding, redaction) **before** it is written, so
it contains no host paths, connection URIs, raw domain UUIDs, XML, or secrets; the
guest report is bound to a redacted control-plane operation reference, the fresh
challenge, the selected envelope/configuration + appliance digests, and a
`sha256:` native correlation. The report preserves the exact guest-observed
memory MiB value and separately discloses the configured one-sided memory
tolerance (16 MiB by default). The equivalent gate also runs as an opt-in pytest:

```sh
RAES_REAL_LIBVIRT_URI=qemu:///system \
  uv run pytest -m integration \
  implementations/python/tests/test_libvirt_backend_guest_certified_real_libvirt.py
```

Both are skipped by the default hermetic `nox verify` graph, which never requires
libvirt, QEMU/KVM, privileges, a host image, network access, or credentials — the
guest-certified proof is an explicit separate gate. The AWS guest-certification
script (`run_aws_guest_certify.sh`) keeps the host's default security driver and
renders the appliance boot artifacts and guest fact channel inside a scoped
per-run directory under `/var/lib/libvirt/images` so the confined daemon can
reach them without any `security_driver`/`qemu.conf` override. Because the guest
appliance boots the host kernel (`/boot/vmlinuz-*`, root-readable only), the
evidence run is invoked with a fixed argument vector under `sudo` — not a
`sudo bash -lc` login shell — while QEMU stays confined by the default driver.

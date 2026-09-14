#!/usr/bin/env bash
# Provision an ephemeral AWS EC2 host with a real libvirt/QEMU daemon, run the
# guest-certified realization proof (ASR-519, issue #715) against it through the
# production apply path, pull back the redaction-safe machine-readable evidence
# artifact, then tear everything down. This is the guest-observed counterpart to
# run_aws_smoke.sh (which proves daemon-level reconciliation with a cirros disk).
#
# Input governance (issue #1222, inventory row I13): the live-runner inputs are
# execution-bound to their reviewed authorities. The base image is Canonical's
# exact published image NAME (serial), resolved by owner + exact name; the native
# packages install from a pinned snapshot.ubuntu.com archive timestamp; the
# declared cpython-3.14 interpreter, the uv client and the offline libvirt-python
# build closure are selected/verified locally and pre-seeded. libvirt-python
# installs fully offline. The appliance is built from a static busybox initramfs
# and the host kernel (no CirrOS). The instance host key is pinned from the
# authenticated AWS console output (StrictHostKeyChecking=yes); only Git-tracked
# files are transferred. AWS provisioning/API behaviour stays an external service
# boundary; the host keeps its default security driver (no security_driver="none",
# no root QEMU user/group), the evidence run is invoked with a fixed argument
# vector (no `sudo bash -lc`, no python -c interpolation), and a run's evidence is
# pulled before teardown.
#
# Usage:
#   SSH_INGRESS_CIDR=203.0.113.4/32 AWS_PROFILE=proof AWS_REGION=us-east-2 \
#     tools/real-daemon/run_aws_guest_certify.sh [--keep]
#
#   SSH_INGRESS_CIDR   REQUIRED reviewed CIDR allowed to reach the instance on tcp/22.
#   RUN_ID             optional safe run-id label (default guest-<utc>-<pid>).
#   --keep             leave the instance/security group/key pair up for manual poking.
#
# On success the emitted evidence JSON is copied to
#   tools/real-daemon/evidence/guest-certified-<run-id>.json
# The instance uses TCG (software emulation); no bare-metal/nested-virt needed.
set -euo pipefail

PROFILE="${AWS_PROFILE:-proof}"
REGION="${AWS_REGION:-us-east-2}"
INSTANCE_TYPE="${INSTANCE_TYPE:-c5.2xlarge}"
SSH_INGRESS_CIDR="${SSH_INGRESS_CIDR:-}"
RUN_ID="${RUN_ID:-guest-$(date -u +%Y%m%d%H%M%S)-$$}"
KEEP=0
[[ "${1:-}" == "--keep" ]] && KEEP=1

if [[ -z "$SSH_INGRESS_CIDR" ]]; then
  echo "error: set SSH_INGRESS_CIDR to the reviewed CIDR permitted to reach the instance on tcp/22" >&2
  exit 2
fi
if ! printf '%s' "$RUN_ID" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$'; then
  echo "error: RUN_ID is not a safe run-id label" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
NAME="raes-guest-certify-$RUN_ID"
STAGE="$REPO_ROOT/.cache/raes-sdl/live-runner-stage/$RUN_ID"
WORK="$(mktemp -d)"
chmod 700 "$WORK"
KEY="$WORK/$NAME.pem"
KNOWN_HOSTS="$WORK/known_hosts"
RUN_DIR="/var/lib/libvirt/images/raes-run/$RUN_ID"
AWS=(aws --profile "$PROFILE" --region "$REGION")

created_iid=""
created_sg=""
created_key=0
IP=""

cleanup() {
  if [[ "$KEEP" == "1" ]]; then
    echo "--keep: leaving instance ${created_iid:-?} (${IP:-?}), security group ${created_sg:-?} and key pair $NAME up; terminate them manually." >&2
    return
  fi
  echo "=== teardown (owned resources only) ==="
  [[ -n "$created_iid" ]] && "${AWS[@]}" ec2 terminate-instances --instance-ids "$created_iid" >/dev/null 2>&1 || true
  [[ -n "$created_iid" ]] && "${AWS[@]}" ec2 wait instance-terminated --instance-ids "$created_iid" 2>/dev/null || true
  [[ -n "$created_sg" ]] && "${AWS[@]}" ec2 delete-security-group --group-id "$created_sg" >/dev/null 2>&1 || true
  [[ "$created_key" == "1" ]] && "${AWS[@]}" ec2 delete-key-pair --key-name "$NAME" >/dev/null 2>&1 || true
  rm -rf "$WORK" "$STAGE"
  echo "torn down."
}
trap cleanup EXIT

pin_host_key() {
  local out keys
  for _ in $(seq 1 40); do
    out=$("${AWS[@]}" ec2 get-console-output --instance-id "$created_iid" --latest --output text 2>/dev/null || true)
    keys=$(printf '%s\n' "$out" | awk '/BEGIN SSH HOST KEY KEYS/{f=1;next}/END SSH HOST KEY KEYS/{f=0}f')
    if [[ -n "$keys" ]]; then
      printf '%s\n' "$keys" | while read -r ktype kval _; do
        [[ -n "$ktype" && -n "$kval" ]] && printf '%s %s %s\n' "$IP" "$ktype" "$kval" >> "$KNOWN_HOSTS"
      done
      [[ -s "$KNOWN_HOSTS" ]] && return 0
    fi
    sleep 15
  done
  return 1
}

echo "=== stage admitted live-runner inputs (governed acquisition + local verification) ==="
rm -rf "$STAGE"
uv run --project implementations/tooling/python --frozen \
  python "$REPO_ROOT/tools/real-daemon/live_runner_inputs.py" --stage-dir "$STAGE" --no-cirros >/dev/null
MANIFEST="$STAGE/live-runner-inputs-manifest.json"
[[ -f "$MANIFEST" ]] || { echo "error: input staging did not produce a manifest" >&2; exit 1; }
read_nested() { local section="$1" key="$2"; python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]][sys.argv[3]])' "$MANIFEST" "$section" "$key"; }
read_top() { local key="$1"; python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$MANIFEST" "$key"; }
UV_ARCHIVE="$STAGE/$(read_nested uv staged_path)"
CPYTHON_ARCHIVE="$STAGE/$(read_nested cpython staged_path)"
IMAGE_OWNER="$(read_nested base_image owner)"
IMAGE_NAME="$(read_nested base_image name)"
NATIVE_SNAPSHOT="$(read_top native_repository_snapshot)"
[[ -f "$UV_ARCHIVE" && -f "$CPYTHON_ARCHIVE" && -d "$STAGE/wheelhouse" ]] || { echo "error: staged inputs are incomplete" >&2; exit 1; }

echo "=== identity ==="; "${AWS[@]}" sts get-caller-identity --query Account --output text

echo "=== resolve reviewed image by exact Canonical name + owner ==="
AMI=$("${AWS[@]}" ec2 describe-images --owners "$IMAGE_OWNER" \
  --filters "Name=name,Values=$IMAGE_NAME" "Name=architecture,Values=x86_64" "Name=state,Values=available" \
  --query 'Images[0].ImageId' --output text)
[[ -n "$AMI" && "$AMI" != "None" ]] || { echo "error: reviewed image '$IMAGE_NAME' (owner $IMAGE_OWNER) not found in $REGION" >&2; exit 1; }
echo "resolved AMI: $AMI ($IMAGE_NAME, owner $IMAGE_OWNER)"

VPC=$("${AWS[@]}" ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
SUBNET=$("${AWS[@]}" ec2 describe-subnets --filters Name=default-for-az,Values=true --query 'Subnets[0].SubnetId' --output text)

"${AWS[@]}" ec2 create-key-pair --key-name "$NAME" --query KeyMaterial --output text > "$KEY"
created_key=1
chmod 600 "$KEY"

created_sg=$("${AWS[@]}" ec2 create-security-group --group-name "$NAME-sg" \
  --description "raes guest-certify proof ($RUN_ID)" --vpc-id "$VPC" --query GroupId --output text)
"${AWS[@]}" ec2 authorize-security-group-ingress --group-id "$created_sg" --protocol tcp --port 22 --cidr "$SSH_INGRESS_CIDR" >/dev/null

# userdata pins APT to an immutable snapshot.ubuntu.com timestamp and installs
# ONLY the reviewed native package set (incl. static busybox + cpio for the
# guest-observing appliance), then prepares a scoped, libvirt-accessible run
# root. No downloads of tools, no pipe-to-shell, no host-security downgrade.
cat > "$WORK/userdata.sh" <<UD
#!/bin/bash
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive
cat > /etc/apt/sources.list.d/ubuntu.sources <<SOURCES
Types: deb
URIs: https://snapshot.ubuntu.com/ubuntu/$NATIVE_SNAPSHOT
Suites: noble noble-updates
Components: main restricted universe multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
Check-Valid-Until: no
SOURCES
apt-get update -y
apt-get install -y qemu-system-x86 qemu-utils libvirt-daemon-system libvirt-clients libvirt-dev genisoimage python3-dev pkg-config build-essential rsync busybox-static cpio
systemctl enable --now libvirtd
usermod -aG libvirt,kvm ubuntu
install -d -m 0711 -o root -g root /var/lib/libvirt/images/raes-run
touch /var/lib/cloud/userdata-done
UD

created_iid=$("${AWS[@]}" ec2 run-instances --image-id "$AMI" --instance-type "$INSTANCE_TYPE" \
  --key-name "$NAME" --security-group-ids "$created_sg" --subnet-id "$SUBNET" --associate-public-ip-address \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=30,VolumeType=gp3}' \
  --user-data "file://$WORK/userdata.sh" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" \
  --query 'Instances[0].InstanceId' --output text)
echo "instance: $created_iid"
"${AWS[@]}" ec2 wait instance-running --instance-ids "$created_iid"
IP=$("${AWS[@]}" ec2 describe-instances --instance-ids "$created_iid" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
echo "public ip: $IP"

echo "=== pin instance host key from authenticated console output ==="
pin_host_key || { echo "error: could not obtain the instance host key from console output" >&2; exit 1; }
SSHOPT=(-i "$KEY" -o ConnectTimeout=15 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$KNOWN_HOSTS")

echo "=== wait for userdata (bounded; timeout fails) ==="
ready=0
for _ in $(seq 1 40); do
  ssh "${SSHOPT[@]}" ubuntu@"$IP" "test -f /var/lib/cloud/userdata-done" 2>/dev/null && { ready=1; break; }
  sleep 10
done
[[ "$ready" == "1" ]] || { echo "error: instance setup did not complete within the budget" >&2; exit 1; }

echo "=== deploy tracked source bundle (revision-bound, tracked files only) ==="
REVISION=$(git -C "$REPO_ROOT" rev-parse HEAD)
ssh "${SSHOPT[@]}" ubuntu@"$IP" "mkdir -p ~/raes ~/stage ~/uvbin ~/cpython"
(cd "$REPO_ROOT" && git ls-files -z -- implementations/python contracts examples README.md THIRD_PARTY_NOTICES.md .ground-control.yaml tools/real-daemon \
  | tar --null --no-recursion -T - -cf -) | ssh "${SSHOPT[@]}" ubuntu@"$IP" "tar -x -C ~/raes"
echo "deployed tracked source (HEAD $REVISION plus staged working-tree edits; no untracked/ignored files)"

echo "=== pre-seed verified inputs ==="
scp "${SSHOPT[@]}" "$UV_ARCHIVE" ubuntu@"$IP":/home/ubuntu/stage/uv.tar.gz
scp "${SSHOPT[@]}" "$CPYTHON_ARCHIVE" ubuntu@"$IP":/home/ubuntu/stage/cpython.tar.gz
scp -r "${SSHOPT[@]}" "$STAGE/wheelhouse" ubuntu@"$IP":/home/ubuntu/stage/wheelhouse

echo "=== install pinned uv + declared cpython interpreter + frozen sync + offline libvirt-python ==="
ssh "${SSHOPT[@]}" ubuntu@"$IP" "set -euo pipefail
  tar -xzf ~/stage/uv.tar.gz -C ~/uvbin --strip-components=1
  UV=\$(find ~/uvbin -type f -name uv | head -n1)
  [ -n \"\$UV\" ] || { echo 'error: pre-seeded uv binary not found' >&2; exit 1; }
  tar -xzf ~/stage/cpython.tar.gz -C ~/cpython
  PY=~/cpython/python/bin/python3
  [ -x \"\$PY\" ] || { echo 'error: pre-seeded cpython interpreter not found' >&2; exit 1; }
  \"\$PY\" --version | grep -q 'Python 3.14' || { echo 'error: pre-seeded interpreter is not the declared cpython-3.14' >&2; exit 1; }
  cd ~/raes/implementations/python
  \"\$UV\" sync --frozen --python \"\$PY\"
  \"\$UV\" pip install --python .venv/bin/python --offline --no-index --find-links ~/stage/wheelhouse --require-hashes --requirement ~/raes/tools/real-daemon/live-runner-python.txt
  echo venv-ready"

echo "=== run guest-certified proof (scoped run dir, fixed-argv runner) ==="
# The evidence run reads the host kernel (/boot/vmlinuz-*, root-only) and drives
# qemu:///system, so it runs privileged via a fixed argument vector — not a
# `sudo bash -lc` shell. QEMU stays confined by the default security driver. The
# runner status is captured without immediate exit so a failed run's evidence is
# still pulled back before teardown.
ssh "${SSHOPT[@]}" ubuntu@"$IP" "sudo install -d -m 0711 -o root -g root '$RUN_DIR'"
set +e
ssh "${SSHOPT[@]}" ubuntu@"$IP" "cd ~/raes/implementations/python && sudo -n env \
  RAES_GUEST_RUN_ID='$RUN_ID' \
  RAES_GUEST_SCENARIO=/home/ubuntu/raes/examples/scenarios/techvault-guest-certified.sdl.yaml \
  RAES_GUEST_PROJECT_DIR='$RUN_DIR' \
  RAES_GUEST_CONNECTION_URI=qemu:///system \
  .venv/bin/python /home/ubuntu/raes/tools/real-daemon/guest_certify_run.py"
run_status=$?
set -e

echo "=== pull evidence artifact (before teardown, even on failure) ==="
ssh "${SSHOPT[@]}" ubuntu@"$IP" "sudo chown -R ubuntu '$RUN_DIR/runs/$RUN_ID/scenario-evidence' 2>/dev/null || true"
mkdir -p "$REPO_ROOT/tools/real-daemon/evidence"
copy_status=0
if scp "${SSHOPT[@]}" ubuntu@"$IP":"$RUN_DIR/runs/$RUN_ID/scenario-evidence/libvirt-scenario-evidence-run.json" \
  "$REPO_ROOT/tools/real-daemon/evidence/guest-certified-$RUN_ID.json" 2>/dev/null; then
  echo "pulled: tools/real-daemon/evidence/guest-certified-$RUN_ID.json"
else
  copy_status=1
  echo "warning: evidence artifact could not be pulled" >&2
fi

# A failed certification always wins. But a *successful* run whose required
# evidence was not persisted locally must not report success either.
if [[ "$run_status" -ne 0 ]]; then
  exit "$run_status"
fi
exit "$copy_status"

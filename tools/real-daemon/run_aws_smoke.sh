#!/usr/bin/env bash
# Provision an ephemeral AWS EC2 host with a real libvirt/QEMU daemon, run the
# libvirt-backend real-daemon smoke test (tools/real-daemon/libvirt_smoke.py)
# against it, then tear everything down. Use this to periodically confirm the
# libvirt reconciliation/teardown backend actually works against real libvirtd
# (the hermetic `nox verify` graph deliberately uses in-process fakes).
#
# Input governance (issue #1222, inventory row I13): the live-runner inputs are
# execution-bound to their reviewed authorities. The base image is Canonical's
# exact published image NAME (serial), resolved to the region's AMI id by owner +
# exact name (never "newest"); the native packages install from a pinned
# snapshot.ubuntu.com archive timestamp (reproducible versions); the declared
# cpython-3.14 interpreter, the uv client, the CirrOS guest disk and the offline
# libvirt-python build closure are selected/verified locally
# (tools/real-daemon/live_runner_inputs.py), pre-seeded and re-verified on the
# host. There is no pipe-to-shell bootstrap, no ignored download, and
# libvirt-python installs fully offline from the pre-seeded wheelhouse. The
# instance host key is pinned from the authenticated AWS console output
# (StrictHostKeyChecking=yes). Only Git-tracked files are transferred. AWS
# provisioning/API behaviour stays an external service boundary; the host runs
# under its default security driver (no security_driver="none", no root QEMU
# user/group).
#
# Usage:
#   SSH_INGRESS_CIDR=203.0.113.4/32 AWS_PROFILE=aws-dev AWS_REGION=us-east-1 \
#     tools/real-daemon/run_aws_smoke.sh [--keep]
#
#   SSH_INGRESS_CIDR   REQUIRED reviewed CIDR allowed to reach the instance on tcp/22.
#   --keep             leave the instance/security group/key pair up for manual poking.
#
# Requirements on the caller's box: aws CLI (authenticated), ssh, scp, git, tar
# and uv (to run the governed local staging). The instance uses TCG (software
# emulation), so no bare-metal/nested-virt is needed.
set -euo pipefail

PROFILE="${AWS_PROFILE:-aws-dev}"
REGION="${AWS_REGION:-us-east-1}"
INSTANCE_TYPE="${INSTANCE_TYPE:-c5.2xlarge}"
SSH_INGRESS_CIDR="${SSH_INGRESS_CIDR:-}"
KEEP=0
[ "${1:-}" = "--keep" ] && KEEP=1

if [ -z "$SSH_INGRESS_CIDR" ]; then
  echo "error: set SSH_INGRESS_CIDR to the reviewed CIDR permitted to reach the instance on tcp/22" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUN_ID="smoke-$(date -u +%Y%m%d%H%M%S)-$$"
NAME="raes-libvirt-test-$RUN_ID"
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
  if [ "$KEEP" = "1" ]; then
    echo "--keep: leaving instance ${created_iid:-?} (${IP:-?}), security group ${created_sg:-?} and key pair $NAME up; terminate them manually." >&2
    return
  fi
  echo "=== teardown (owned resources only) ==="
  [ -n "$created_iid" ] && "${AWS[@]}" ec2 terminate-instances --instance-ids "$created_iid" >/dev/null 2>&1 || true
  [ -n "$created_iid" ] && "${AWS[@]}" ec2 wait instance-terminated --instance-ids "$created_iid" 2>/dev/null || true
  [ -n "$created_sg" ] && "${AWS[@]}" ec2 delete-security-group --group-id "$created_sg" >/dev/null 2>&1 || true
  [ "$created_key" = "1" ] && "${AWS[@]}" ec2 delete-key-pair --key-name "$NAME" >/dev/null 2>&1 || true
  rm -rf "$WORK" "$STAGE"
  echo "torn down."
}
trap cleanup EXIT

pin_host_key() {
  local out keys
  for _ in $(seq 1 40); do
    out=$("${AWS[@]}" ec2 get-console-output --instance-id "$created_iid" --latest --output text 2>/dev/null || true)
    keys=$(printf '%s\n' "$out" | awk '/BEGIN SSH HOST KEY KEYS/{f=1;next}/END SSH HOST KEY KEYS/{f=0}f')
    if [ -n "$keys" ]; then
      printf '%s\n' "$keys" | while read -r ktype kval _; do
        [ -n "$ktype" ] && [ -n "$kval" ] && printf '%s %s %s\n' "$IP" "$ktype" "$kval" >> "$KNOWN_HOSTS"
      done
      [ -s "$KNOWN_HOSTS" ] && return 0
    fi
    sleep 15
  done
  return 1
}

echo "=== stage admitted live-runner inputs (governed acquisition + local verification) ==="
rm -rf "$STAGE"
uv run --project implementations/tooling/python --frozen \
  python "$REPO_ROOT/tools/real-daemon/live_runner_inputs.py" --stage-dir "$STAGE" >/dev/null
MANIFEST="$STAGE/live-runner-inputs-manifest.json"
[ -f "$MANIFEST" ] || { echo "error: input staging did not produce a manifest" >&2; exit 1; }
read_nested() { python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]][sys.argv[3]])' "$MANIFEST" "$1" "$2"; }
read_top() { python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$MANIFEST" "$1"; }
CIRROS_SHA256="$(read_nested cirros_guest_disk sha256)"
CIRROS_SIZE="$(read_nested cirros_guest_disk size)"
UV_ARCHIVE="$STAGE/$(read_nested uv staged_path)"
CPYTHON_ARCHIVE="$STAGE/$(read_nested cpython staged_path)"
IMAGE_OWNER="$(read_nested base_image owner)"
IMAGE_NAME="$(read_nested base_image name)"
NATIVE_SNAPSHOT="$(read_top native_repository_snapshot)"
[ -f "$STAGE/cirros.img" ] && [ -f "$UV_ARCHIVE" ] && [ -f "$CPYTHON_ARCHIVE" ] && [ -d "$STAGE/wheelhouse" ] || { echo "error: staged inputs are incomplete" >&2; exit 1; }

echo "=== identity ==="; "${AWS[@]}" sts get-caller-identity --query Account --output text

echo "=== resolve reviewed image by exact Canonical name + owner ==="
AMI=$("${AWS[@]}" ec2 describe-images --owners "$IMAGE_OWNER" \
  --filters "Name=name,Values=$IMAGE_NAME" "Name=architecture,Values=x86_64" "Name=state,Values=available" \
  --query 'Images[0].ImageId' --output text)
[ -n "$AMI" ] && [ "$AMI" != "None" ] || { echo "error: reviewed image '$IMAGE_NAME' (owner $IMAGE_OWNER) not found in $REGION" >&2; exit 1; }
echo "resolved AMI: $AMI ($IMAGE_NAME, owner $IMAGE_OWNER)"

VPC=$("${AWS[@]}" ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
SUBNET=$("${AWS[@]}" ec2 describe-subnets --filters Name=default-for-az,Values=true --query 'Subnets[0].SubnetId' --output text)

"${AWS[@]}" ec2 create-key-pair --key-name "$NAME" --query KeyMaterial --output text > "$KEY"
created_key=1
chmod 600 "$KEY"

created_sg=$("${AWS[@]}" ec2 create-security-group --group-name "$NAME-sg" \
  --description "raes libvirt real-daemon smoke ($RUN_ID)" --vpc-id "$VPC" --query GroupId --output text)
"${AWS[@]}" ec2 authorize-security-group-ingress --group-id "$created_sg" --protocol tcp --port 22 --cidr "$SSH_INGRESS_CIDR" >/dev/null

# userdata pins the APT archive to an immutable snapshot.ubuntu.com timestamp so
# the reviewed native package set installs at reproducible versions, then
# installs ONLY that reviewed set and prepares a scoped, libvirt-accessible run
# root. No downloads of tools, no pipe-to-shell, no host-security downgrade
# (default AppArmor/QEMU confinement stays enabled).
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
apt-get install -y qemu-system-x86 qemu-utils libvirt-daemon-system libvirt-clients libvirt-dev genisoimage python3-dev pkg-config build-essential rsync
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
[ "$ready" = "1" ] || { echo "error: instance setup did not complete within the budget" >&2; exit 1; }

echo "=== deploy tracked source bundle (revision-bound, tracked files only) ==="
# Transfer only Git-tracked regular files (the set the policy gate admits) as a
# revision-bound bundle, excluding untracked/ignored files (.env, .pypirc,
# caches) so no credential or unreviewed input can cross onto the host.
REVISION=$(git -C "$REPO_ROOT" rev-parse HEAD)
ssh "${SSHOPT[@]}" ubuntu@"$IP" "mkdir -p ~/raes ~/stage ~/uvbin ~/cpython"
(cd "$REPO_ROOT" && git ls-files -z -- implementations/python contracts README.md THIRD_PARTY_NOTICES.md tools/real-daemon \
  | tar --null --no-recursion -T - -cf -) | ssh "${SSHOPT[@]}" ubuntu@"$IP" "tar -x -C ~/raes"
echo "deployed tracked source (HEAD $REVISION plus staged working-tree edits; no untracked/ignored files)"

echo "=== pre-seed verified inputs ==="
scp "${SSHOPT[@]}" "$STAGE/cirros.img" ubuntu@"$IP":/home/ubuntu/stage/cirros.img
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

echo "=== place + re-verify the pre-seeded guest disk in the scoped run dir ==="
ssh "${SSHOPT[@]}" ubuntu@"$IP" "set -euo pipefail
  sudo install -d -m 0711 -o ubuntu -g ubuntu '$RUN_DIR'
  install -m 0644 ~/stage/cirros.img '$RUN_DIR/cirros.img'
  actual=\$(sha256sum '$RUN_DIR/cirros.img' | cut -d' ' -f1)
  size=\$(stat -c %s '$RUN_DIR/cirros.img')
  [ \"\$actual\" = '$CIRROS_SHA256' ] || { echo 'error: pre-seeded cirros digest mismatch on instance' >&2; exit 1; }
  [ \"\$size\" = '$CIRROS_SIZE' ] || { echo 'error: pre-seeded cirros size mismatch on instance' >&2; exit 1; }"

echo "=== run real-daemon smoke (scoped run dir, pinned image) ==="
ssh "${SSHOPT[@]}" ubuntu@"$IP" "cd ~/raes/implementations/python && \
  RAES_LIBVIRT_RUN_DIR='$RUN_DIR' \
  RAES_CIRROS_IMAGE='$RUN_DIR/cirros.img' \
  RAES_CIRROS_SHA256='$CIRROS_SHA256' \
  RAES_CIRROS_SIZE='$CIRROS_SIZE' \
  .venv/bin/python ~/raes/tools/real-daemon/libvirt_smoke.py"

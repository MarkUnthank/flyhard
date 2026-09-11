#!/bin/bash
# Ubuntu 22.04 native CARLA builder. Only the public SSH key is supplied by us.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
printf 'Acquire::ForceIPv4 "true";\n' > /etc/apt/apt.conf.d/99flyhard-network
sed -i 's|http://archive.ubuntu.com/ubuntu|http://us.archive.ubuntu.com/ubuntu|g; s|http://security.ubuntu.com/ubuntu|http://us.archive.ubuntu.com/ubuntu|g' /etc/apt/sources.list
apt-get update
apt-get install -y --no-install-recommends openssh-server python3 ca-certificates sudo rsync
install -m 700 -d /root/.ssh
printf '%s\n' "$PUBLIC_KEY" > /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
mkdir -p /run/sshd
ssh-keygen -A
printf '%s' "$FLYHARD_DEADLINE_SCRIPT_B64" | base64 -d > /opt/pod_deadline.py
python3 -u /opt/pod_deadline.py --deadline "$FLYHARD_DEADLINE_EPOCH" > /tmp/pod-deadline.log 2>&1 &
id builder >/dev/null 2>&1 || useradd -m -s /bin/bash builder
printf 'builder ALL=(ALL) NOPASSWD:ALL\n' > /etc/sudoers.d/flyhard-builder
chmod 440 /etc/sudoers.d/flyhard-builder
# Let the unprivileged builder create its own files on root-squashed storage.
mkdir -p /workspace/flyhard-build
chmod 777 /workspace/flyhard-build
exec /usr/sbin/sshd -D -e

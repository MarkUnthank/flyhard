#!/bin/bash
# Ubuntu 22.04 native CARLA builder. Only the public SSH key is supplied by us.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
printf 'Acquire::ForceIPv4 "true";\n' > /etc/apt/apt.conf.d/99flyhard-network
sed -i 's|http://archive.ubuntu.com/ubuntu|http://us.archive.ubuntu.com/ubuntu|g; s|http://security.ubuntu.com/ubuntu|http://us.archive.ubuntu.com/ubuntu|g' /etc/apt/sources.list
apt-get update
apt-get install -y --no-install-recommends openssh-server python3 ca-certificates sudo rsync curl
install -m 700 -d /root/.ssh
printf '%s\n' "$PUBLIC_KEY" > /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
mkdir -p /run/sshd
ssh-keygen -A
: "${FLYHARD_DEADLINE_SCRIPT_B64:?The launch client must inject the deadline helper}"
: "${FLYHARD_DEADLINE_EPOCH:?The launch client must inject the deadline}"
printf '%s' "$FLYHARD_DEADLINE_SCRIPT_B64" | base64 -d > /opt/pod_deadline.py
python3 -u /opt/pod_deadline.py --deadline "$FLYHARD_DEADLINE_EPOCH" > /tmp/pod-deadline.log 2>&1 &
id builder >/dev/null 2>&1 || useradd -m -s /bin/bash builder
cat > /usr/local/sbin/flyhard-install-dependencies <<'SCRIPT'
#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
packages=( \
  build-essential g++-12 cmake ninja-build libvulkan1 mesa-vulkan-drivers vulkan-tools \
  libegl1 libgl1 libopengl0 \
  python3-dev python3-pip python3-venv autoconf automake libtool pkg-config \
  wget curl rsync unzip git git-lfs aria2 \
  mono-runtime ca-certificates-mono libmono-posix4.0-cil libmono-system-xml-linq4.0-cil \
  libmono-system-data-datasetextensions4.0-cil libmono-microsoft-csharp4.0-cil \
  libmono-system-data4.0-cil libmono-system-io-compression4.0-cil \
  libmono-system-io-compression-filesystem4.0-cil \
  libpng-dev libtiff5-dev libjpeg-dev libx11-6 libxcursor1 libxrandr2 libxi6 \
  libxss1 libxcomposite1 libasound2 libnss3 libatk1.0-0 libgtk-3-0 xdg-user-dirs xdg-utils )
/usr/bin/apt-get -o DPkg::Lock::Timeout=600 update
/usr/bin/apt-get -o DPkg::Lock::Timeout=600 install -y --no-install-recommends "${packages[@]}"
SCRIPT
chown root:root /usr/local/sbin/flyhard-install-dependencies
chmod 755 /usr/local/sbin/flyhard-install-dependencies
printf 'builder ALL=(root) NOPASSWD: /usr/local/sbin/flyhard-install-dependencies\n' > /etc/sudoers.d/flyhard-builder
chmod 440 /etc/sudoers.d/flyhard-builder
# Let the unprivileged builder create its own files on root-squashed storage.
mkdir -p /workspace/flyhard-build
chmod 777 /workspace/flyhard-build
exec /usr/sbin/sshd -D -e

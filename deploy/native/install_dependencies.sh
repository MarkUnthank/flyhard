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
python3 "$(dirname "$0")/fetch_apt_packages.py" "${packages[@]}"
apt-get -o DPkg::Lock::Timeout=600 install -y --no-install-recommends "${packages[@]}"
sudo -u builder python3 "$(dirname "$0")/prepare_python_compat.py"

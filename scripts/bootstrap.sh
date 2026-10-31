#!/usr/bin/env bash
set -euo pipefail
if (( EUID != 0 )); then exec sudo bash "$0" "$@"; fi
source /etc/os-release
case "$ID" in
  ubuntu)
    [[ "$VERSION_ID" == 24.04 ]] || { echo 'Ruta soportada: Ubuntu 24.04 LTS'; exit 1; }
    apt-get update
    apt-get install -y python3 python3-venv python3-libvirt qemu-kvm qemu-utils libvirt-daemon-system libvirt-clients virtinst virt-manager dnsmasq-base ovmf xorriso curl openssh-client ipmitool git
    ;;
  arch|omarchy)
    packages=(python python-pip libvirt-python qemu-desktop libvirt virt-install virt-manager dnsmasq edk2-ovmf libisoburn curl openssh ipmitool git)
    if command -v omarchy >/dev/null; then
      omarchy pkg add "${packages[@]}"
    else
      pacman -S --needed "${packages[@]}"
    fi
    ;;
  *) echo 'Sistema no soportado por bootstrap: use Ubuntu 24.04 LTS o Arch/Omarchy.'; exit 1 ;;
esac
modprobe kvm
if grep -q AuthenticAMD /proc/cpuinfo; then modprobe kvm_amd; else modprobe kvm_intel; fi
systemctl enable --now libvirtd
printf '\nDependencias listas. Continúe con: sudo python3 lab.py doctor\n'

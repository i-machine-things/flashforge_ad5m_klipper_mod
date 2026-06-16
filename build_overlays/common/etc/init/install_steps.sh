#!/bin/sh
# This script is called once during install after initial
# setup of the chroot (executed within the chroot)
set -x

# prepare swap
fallocate -l 128M /mnt/swap
mkswap /mnt/swap
chmod 0600 /mnt/swap

##############################
# static data setup
##############################

static_dir="/mnt/data/.klipper_mod/static"
mkdir -p $static_dir

setup_static_data()
{
  # initial static data is initialized from the chroot
  if [ ! -e "$static_dir/$1" ]; then
    mkdir -p "$static_dir/"$(dirname "$1")
    mv "$1" "$static_dir/$1"
  fi

  # symlink the target to the static data dir
  rm -rf "$1"
  ln -s "$static_dir$1" "$1"
}

# keep essential network settings
setup_static_data /etc/hostname
setup_static_data /var/lib/iwd
setup_static_data /etc/network/interfaces
setup_static_data /etc/wpa_supplicant.conf

# keep dropbear keys (that is a symlink to /var/run/dropbear originally)
rm -f /etc/dropbear
mkdir -p /etc/dropbear
setup_static_data /etc/dropbear
# keep /root/.ssh
mkdir -p /root/.ssh
chmod 700 /root/.ssh
setup_static_data /root/.ssh

# keep moonraker database
mkdir -p /root/printer_data/database
setup_static_data /root/printer_data/database
# keep gcode files
mkdir -p /root/printer_data/gcodes
setup_static_data /root/printer_data/gcodes

##############################
# user provided overlay
##############################

# install usb flash drive is mounted to /media if available
if [ -d /media/klipper_mod/ ]; then
    # copy everything into the chroot
    rsync -rltvK /media/klipper_mod/* /
fi
umount /media

##############################
# update klipper firmware
##############################
if /etc/init.d/S54mcu_update start; then
  sleep 3
else
  # display mcu update failure screen for longer time
  # update must be restarted in this case
  sleep 300
  exit 1
fi

##############################
# check wifi connectivity
##############################

if ls /var/lib/iwd/*.psk > /dev/null 2>&1; then
    echo "=== WiFi Connectivity Check ==="
    iwd &
    sleep 8

    WIFI_IP=""
    WIFI_WAIT=0
    while [ $WIFI_WAIT -lt 22 ]; do
        WIFI_IP=$(ip -4 addr show wlan0 2>/dev/null | grep 'inet ' | sed 's/.*inet \([0-9.\/]*\).*/\1/')
        [ -n "$WIFI_IP" ] && break
        sleep 1
        WIFI_WAIT=$((WIFI_WAIT + 1))
    done

    if [ -n "$WIFI_IP" ]; then
        echo "WiFi connected! IP: $WIFI_IP"
    else
        echo "WiFi did not connect within 30s"
    fi
    iwctl station wlan0 show 2>/dev/null || true
    kill "$(pidof iwd)" 2>/dev/null || true
else
    echo "=== No WiFi profiles configured ==="
fi

##############################
# install done
##############################

audio midi -m /usr/share/midis/getitem.mid &
exit 0

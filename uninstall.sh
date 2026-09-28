#!/bin/sh
# Remove everything install.sh put outside this directory. Normal GRUB entries were never changed.
set -e
[ "$(id -u)" = 0 ] || { echo "Run with sudo." >&2; exit 1; }
rm -f /boot/acpi_override.cpio /etc/grub.d/09_touchpad_fix /etc/grub.d/42_touchpad_fix \
	/etc/default/grub.d/99_touchpad_fix.cfg
update-grub
echo "Removed. Reboot to use the firmware's own DSDT again."

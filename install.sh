#!/bin/sh
# Patch this machine's DSDT, install it as an early-initrd override, and add a
# GRUB entry that uses it. Pass --no-default to leave the default entry alone.
# Set IRQ=<n> if the touchpad IRQ can't be detected (e.g. an override is already active).
set -e
[ "$(id -u)" = 0 ] || { echo "Run with sudo." >&2; exit 1; }
cd "$(dirname "$0")"

if [ ! -f dsdt-original.dat ]; then
	if dmesg | grep -q 'Table Upgrade: override \[DSDT'; then
		echo "A DSDT override is already active, so the firmware's original table isn't readable." >&2
		echo "Boot without the override first, or put the original in dsdt-original.dat." >&2
		exit 1
	fi
	cat /sys/firmware/acpi/tables/DSDT > dsdt-original.dat
fi

python3 patch_dsdt.py dsdt-original.dat dsdt.aml ${IRQ:+--irq "$IRQ"}

staging=$(mktemp -d)
trap 'rm -rf "$staging"' EXIT
mkdir -p "$staging/kernel/firmware/acpi"
cp dsdt.aml "$staging/kernel/firmware/acpi/dsdt.aml"
(cd "$staging" && find kernel | cpio -H newc -o -R 0:0 --quiet) > acpi_override.cpio
[ -n "$SUDO_USER" ] && chown "$SUDO_USER": dsdt-original.dat dsdt.aml acpi_override.cpio

install -m 644 acpi_override.cpio /boot/acpi_override.cpio
install -m 755 42_touchpad_fix /etc/grub.d/42_touchpad_fix
if [ "$1" != "--no-default" ]; then
	mkdir -p /etc/default/grub.d
	echo "GRUB_DEFAULT='Linux (touchpad ACPI fix)'" > /etc/default/grub.d/99_touchpad_fix.cfg
fi
update-grub
sed -n "/touchpad ACPI fix/,/^}/p" /boot/grub/grub.cfg
echo "Installed. Reboot; 'Linux (touchpad ACPI fix)' is in the GRUB menu."

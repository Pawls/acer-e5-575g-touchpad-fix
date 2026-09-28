# Acer Aspire E5-575G: touchpad dead on Linux in BIOS "Advanced" mode

On the Acer Aspire E5-575G (ELAN0501 touchpad, BIOS V1.47), setting **Main → Touchpad** in the BIOS to **Advanced** gives Windows a proper Precision Touchpad but leaves the touchpad dead or half-working on Linux. **Basic** works on Linux but makes Windows track badly, because in Basic mode the touchpad is only exposed as a PS/2 mouse.

This repo patches one flag in the firmware's ACPI table so the touchpad works on Linux in Advanced mode, and you no longer have to choose between the two.

## Symptoms

- The touchpad is detected (`ELAN0501:00 04F3:3019 Touchpad` in `/proc/bus/input/devices`, bound to `i2c_hid_acpi` and `hid-multitouch`) but doesn't move the cursor.
- The touchpad's line in `/proc/interrupts` says `-edge`, and its count barely grows when you touch the pad:
  ```
  82:  157  0  0  0  IR-IO-APIC  82-edge  ELAN0501:00
  ```
- Sometimes you'll also see `i2c_hid_acpi i2c-ELAN0501:00: i2c_hid_get_input: IRQ triggered but there's no data` in dmesg.
- Unbinding and rebinding the `i2c_hid_acpi` driver only partly revives it: taps register but the cursor doesn't move.

## Cause

In Advanced mode the DSDT describes the touchpad interrupt as edge-triggered:

```
Interrupt (ResourceConsumer, Edge, ActiveLow, Exclusive, ,, ) { 0x00000052 }
```

An I2C HID device holds its interrupt line low until the host reads its report, so the interrupt should be level-triggered. With edge triggering, a single missed edge leaves the line stuck low and no further interrupts arrive. Windows copes with this and Linux doesn't.

## Fix

`patch_dsdt.py` rewrites the touchpad's interrupt descriptors from `Edge` to `Level`. It leaves the polarity alone, bumps the table's OEM revision, and fixes the checksum. The kernel loads the patched table from an early initrd (this needs `CONFIG_ACPI_TABLE_UPGRADE=y`, which Ubuntu and Mint kernels have). A separate GRUB entry boots with it, and your existing entries are left unchanged.

On the E5-575G the change is two bytes: one flag byte in each of the two touchpad device definitions (`TPD1` for the Synaptics variant, `TPDE` for ELAN), plus the revision number and checksum. After the fix, the interrupt shows as `82-fasteoi` and the touchpad works, though not the way the Cause section suggests; see [Known issue: interrupt storm](#known-issue-interrupt-storm).

The table is patched on your machine from your own firmware. No DSDT is distributed here.

## Install

Boot in Advanced mode, without any DSDT override active, then run:

```
git clone https://github.com/Pawls/acer-e5-575g-touchpad-fix.git
cd acer-e5-575g-touchpad-fix
sudo ./install.sh              # puts the fix entry first in GRUB, so it boots by default
sudo ./install.sh --no-default # or: add the entry at the end and keep your current default
```

If the IRQ can't be detected automatically, find the touchpad's number in `/proc/interrupts` and pass it with `sudo IRQ=82 ./install.sh`.

Reboot, pick **Linux (touchpad ACPI fix)** if it isn't the default, then check that the override loaded:

```
sudo dmesg | grep -i 'table upgrade'   # ACPI: Table Upgrade: override [DSDT-ACRSYS-ACRPRDCT]
grep -i elan /proc/interrupts          # ... 82-fasteoi  ELAN0501:00
```

The entry boots `/boot/vmlinuz` and `/boot/initrd.img`, which Debian, Ubuntu, and Mint keep pointed at the newest kernel, so it keeps working after kernel updates.

## Uninstall

```
sudo ./uninstall.sh
```

This removes `/boot/acpi_override.cpio` and the GRUB entry. If the fix entry ever fails to boot, pick your normal entry from the GRUB menu.

## Known issue: interrupt storm

With the fix in place, the line stays asserted even when the touchpad has nothing to send. Measured on kernel 7.0.0-34, sitting idle:

- IRQ 82 fires about 1,740 times a second, touched or not, and the `irq/82-ELAN0501` thread uses about 4% of one CPU thread.
- An I2C trace over 2 seconds recorded 3,487 reads of the touchpad, and every one returned `ff ff ...`, the I2C HID "no data" reply. The kernel drops these silently (ELAN devices get `I2C_HID_QUIRK_BOGUS_IRQ`).
- No input events arrive while idle.

The touchpad works because the kernel reads it nonstop and picks up real reports along the way, not because the interrupt signals them. Now and then a read comes back garbled (`i2c_hid_get_input: incomplete report (14/60416)` in dmesg) and that report is lost, which may be why the cursor occasionally skips. The storm also keeps the CPU out of deep idle states, which costs battery.

Check the rate on your machine (hands off the touchpad):

```
a=$(grep ELAN0501 /proc/interrupts | awk '{print $2+$3+$4+$5}'); sleep 5
b=$(grep ELAN0501 /proc/interrupts | awk '{print $2+$3+$4+$5}'); echo $(( (b - a) / 5 ))/s
```

The cause is still open. What's been ruled out or learned so far:

- The chipset GPIO controller is hidden from the OS (`INT344B` has ACPI status 0). Routing the pad whose interrupt select is 82 (community `0xAD`, pad 2) to the IO-APIC at runtime didn't change the rate.
- Flipping the descriptor to `Level, ActiveHigh` stops the storm (0 interrupts/s) but the touchpad goes dead: IRQ 82 never fires for real touches.
- In every boot where the touchpad isn't read constantly (stock `Edge`, or `ActiveHigh`), the kernel logs `irq 16: nobody cared` and `Disabling IRQ #16`. IRQ 16 is shared by `idma64.0`, `i2c_designware.0` (the touchpad's I2C bus) and `i801_smbus`. With `Level, ActiveLow` the constant reads keep the touchpad's buffer empty and IRQ 16 stays quiet. So the touchpad's real interrupt probably lands on IRQ 16, not 82. A DSDT fix can't simply point the touchpad at IRQ 16, because `i2c-hid` requests its IRQ without `IRQF_SHARED`.

## Caveats

- **Run `uninstall.sh` before updating the BIOS.** The kernel replaces the DSDT based on its OEM ID and table ID, not its version, so an old patched table would override the new firmware's table. After the BIOS update, boot without the override and install again.
- An overridden ACPI table marks the kernel as tainted (flag `I`). This is harmless, but mention it in any kernel bug report.
- Tested only on an Aspire E5-575G, BIOS V1.47, Linux Mint 22.3, kernel 7.0.0-34-generic. Other Acer laptops from the same era (Skylake/Kaby Lake) with a Basic/Advanced touchpad setting may have the same bug. The patcher will refuse to change anything if it doesn't find an edge-triggered interrupt for the touchpad's IRQ.

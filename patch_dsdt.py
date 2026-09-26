#!/usr/bin/env python3
"""Rewrite an I2C touchpad's edge-triggered interrupt as level-triggered in a DSDT.

Reads a DSDT, flips every matching ACPI Extended Interrupt descriptor for the
given IRQ from edge to level (polarity untouched), bumps the OEM revision and
fixes the checksum. See README.md for why.
"""
import argparse
import re
import struct
import sys

EXT_IRQ_TAG = 0x89
FLAG_CONSUMER = 0x01
FLAG_EDGE = 0x02


def find_edge_irq_descriptors(table, irq):
    """Offsets of single-IRQ Extended Interrupt descriptors for `irq` that are edge-triggered."""
    descriptor = struct.pack('<BHB', EXT_IRQ_TAG, 6, 0) + b'\x01' + struct.pack('<I', irq)
    offsets = []
    for match in re.finditer(re.escape(descriptor[:3]), table):
        start = match.start()
        candidate = table[start:start + 9]
        flags = candidate[3]
        if candidate[4:] != descriptor[4:]:
            continue
        if flags & FLAG_CONSUMER and flags & FLAG_EDGE:
            offsets.append(start)
    return offsets


def patch(table, irq):
    table = bytearray(table)
    if table[:4] != b'DSDT' or struct.unpack_from('<I', table, 4)[0] != len(table):
        sys.exit('input is not a complete DSDT')

    offsets = find_edge_irq_descriptors(table, irq)
    if not offsets:
        sys.exit(f'no edge-triggered interrupt descriptor for IRQ {irq} found '
                 '(already patched, or this firmware describes it differently)')

    for offset in offsets:
        table[offset + 3] &= ~FLAG_EDGE & 0xFF

    oem_revision = struct.unpack_from('<I', table, 24)[0]
    struct.pack_into('<I', table, 24, oem_revision + 1)
    table[9] = 0
    table[9] = -sum(table) & 0xFF
    return bytes(table), offsets


def detect_touchpad_irq():
    """IRQ of the first edge-triggered I2C HID device in /proc/interrupts (ELAN, SYNA, ...)."""
    with open('/proc/interrupts') as f:
        for line in f:
            if re.search(r'-edge\s+(ELAN|SYNA|ALPS|MSFT|FTCS|ATML|DELL|CUST)[0-9A-F]{4}:', line):
                return int(line.split(':')[0])
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', help='original DSDT, e.g. a copy of /sys/firmware/acpi/tables/DSDT')
    parser.add_argument('output', help='patched DSDT (.aml) to write')
    parser.add_argument('--irq', type=int, help='touchpad IRQ (default: detect from /proc/interrupts)')
    args = parser.parse_args()

    irq = args.irq if args.irq is not None else detect_touchpad_irq()
    if irq is None:
        sys.exit('could not detect an edge-triggered I2C touchpad IRQ; pass --irq')

    with open(args.input, 'rb') as f:
        original = f.read()
    patched, offsets = patch(original, irq)
    with open(args.output, 'wb') as f:
        f.write(patched)
    print(f'IRQ {irq}: set {len(offsets)} descriptor(s) to level-triggered at '
          f'{", ".join(hex(o) for o in offsets)}; wrote {args.output}')


if __name__ == '__main__':
    main()

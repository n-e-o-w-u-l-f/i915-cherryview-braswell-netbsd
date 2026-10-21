#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# NetBSD 11 target-userland extracted connector/AUX unwind regression.
# No kernel modification, no HP install/reboot, no actual DRM fault injection.
set -eu
: "${NETBSD11_SYSROOT:?Set NETBSD11_SYSROOT to the verified NetBSD 11 amd64 base+comp target root}"
NETBSD11_CC="${NETBSD11_CC:-x86_64--netbsd-gcc}"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OUTPUT="${1:-$SCRIPT_DIR/test0068}"
[ -r "$NETBSD11_SYSROOT/usr/include/stdio.h" ] || { echo "missing NetBSD11 target headers" >&2; exit 2; }
[ -r "$NETBSD11_SYSROOT/usr/lib/libc.a" ] || { echo "missing NetBSD11 static libc" >&2; exit 2; }
"$NETBSD11_CC" -v "--sysroot=$NETBSD11_SYSROOT" \
  -O2 -std=gnu11 -Wall -Wextra -Werror -static \
  -o "$OUTPUT" "$SCRIPT_DIR/connector_unwind_netbsd_0068.c"
printf '%s\n' "Generated NetBSD 11 native userland harness: $OUTPUT"
# Only run resulting ELF on NetBSD 11; it is not Linux executable.

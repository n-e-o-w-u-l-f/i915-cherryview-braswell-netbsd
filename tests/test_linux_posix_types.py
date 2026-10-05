#!/usr/bin/env python3
"""Compile the native types header with pinned Linux UAPI ABI assertions on HP.

The sys/bus.h shim supplies only OS bus scalar declarations in userland;
linux/stddef.h supplies the standard C NULL/offsetof definitions. The
Linux types, POSIX headers, architecture selection and ioctl structure under
test are actual source files. This does not test DRM ioctl dispatch or compat32.
"""
import argparse
from pathlib import Path
import platform
import socket
import subprocess
import tempfile

PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
TYPES = "sys/external/bsd/common/include/linux/types.h"

C = r'''
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <linux/types.h>
#include <drm/drm.h>
#define SAME(T, U) _Static_assert(__builtin_types_compatible_p(T, U), #T " scalar ABI")
SAME(__kernel_size_t, unsigned long);
SAME(__kernel_ssize_t, long);
SAME(__kernel_ptrdiff_t, long);
SAME(__kernel_long_t, long);
SAME(__kernel_ulong_t, unsigned long);
SAME(__kernel_off_t, long);
SAME(__kernel_loff_t, long long);
SAME(__kernel_time64_t, long long);
SAME(__kernel_old_uid_t, unsigned short);
SAME(__kernel_old_gid_t, unsigned short);
SAME(__kernel_old_dev_t, unsigned long);
SAME(__kernel_uid_t, unsigned int);
SAME(__kernel_gid_t, unsigned int);
SAME(u64, unsigned long long);
SAME(__u64, unsigned long long);
SAME(__le64, unsigned long long);
SAME(__be64, unsigned long long);
SAME(s64, long long);
SAME(__s64, long long);
_Static_assert(sizeof(long) == 8 && sizeof(void *) == 8, "HP amd64 ABI");
_Static_assert(sizeof(struct drm_version) == 64, "Linux amd64 drm_version ABI");
_Static_assert(offsetof(struct drm_version, name_len) == 16, "drm name size offset");
_Static_assert(offsetof(struct drm_version, name) == 24, "drm name pointer offset");
_Static_assert(offsetof(struct drm_version, date_len) == 32, "drm date size offset");
_Static_assert(offsetof(struct drm_version, desc_len) == 48, "drm desc size offset");
int main(void) {
    char b[64]; u64 u = UINT64_MAX; s64 s = INT64_MIN;
    return snprintf(b, sizeof(b), "%llu %lld", u, s) != 41;
}
'''

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--netbsd-tree", type=Path, required=True)
    p.add_argument("--baseline", action="store_true")
    p.add_argument("--apply-candidate", action="store_true")
    a = p.parse_args()
    if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
        p.error("compiler-invoking checks are authorized only on HP/NetBSD")
    if platform.machine() != "amd64": p.error("this ABI fixture requires HP amd64")
    owner = Path(__file__).resolve().parents[1]
    stage = Path('/root/hp-driver-port-20261005/netbsd-full-linux')
    if not stage.is_dir(): p.error("actual HP full graph inputs required")
    with tempfile.TemporaryDirectory(prefix="i915-posix-types-") as temporary:
        temp = Path(temporary)
        header = temp / "linux/types.h"
        header.parent.mkdir(parents=True)
        if a.baseline or a.apply_candidate:
            original = subprocess.check_output(["git", "-C", str(a.netbsd_tree), "show", PIN + ":" + TYPES])
            source = temp / TYPES; source.parent.mkdir(parents=True); source.write_bytes(original)
            if a.apply_candidate:
                patch = owner / "patches/0020-netbsd-linux-posix-types.patch"
                subprocess.run(["git", "-C", str(temp), "apply", "--check", str(patch)], check=True)
                subprocess.run(["git", "-C", str(temp), "apply", str(patch)], check=True)
            header.write_bytes(source.read_bytes())
        else:
            header.write_bytes((a.netbsd_tree / TYPES).read_bytes())
        bus = temp / "sys/bus.h"; bus.parent.mkdir(exist_ok=True)
        bus.write_text("#include <stdint.h>\ntypedef uint64_t bus_addr_t;\ntypedef uint64_t paddr_t;\n")
        (temp / "linux/stddef.h").write_text("#include <stddef.h>\n")
        c = temp / "abi.c"; c.write_text(C)
        exe = temp / "abi"
        include = [temp, stage / "sys/external/bsd/common/include",
                   stage / "sys/external/bsd/drm2/include", stage / "sys/external/bsd/drm2/dist/include"]
        command = ["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-D__KERNEL__"]
        for path in include: command += ["-I", str(path)]
        subprocess.run(command + [str(c), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
    print("LINUX_POSIX_TYPES_OK: 19 native amd64 scalar type checks; fixed64 format contracts; frozen drm_version ABI")

if __name__ == "__main__":
    main()

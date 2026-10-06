#!/usr/bin/env python3
"""HP-only exact-body adapters and independent integer oracle vectors."""
from pathlib import Path
import importlib.util
import json
import platform
import random
import re
import socket

if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
    raise SystemExit("HP-only functional test preparation")
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("pwm_generate", ROOT / "generate.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
header = (ROOT / "include/linux/pwm.h").read_text()
(ROOT / "tests/test_pwm_header.h").write_text(re.sub(r"^#include[^\n]*\n", "", header, flags=re.M))
err = (ROOT / "base/native_err.h").read_text()
(ROOT / "tests/test_err_header.h").write_text(re.sub(r"^#include[^\n]*\n", "", err, flags=re.M))
types = (ROOT / "base/native_types.h").read_text()
start = types.index("struct list_head {")
(ROOT / "tests/test_list_type.h").write_text(types[start:types.index("};", start) + 3])
math = (ROOT / "base/linux_math.h").read_text()
start = math.index("#define DIV_ROUND_CLOSEST_ULL(")
stop = math.index("\n\n", start)
div = (ROOT / "base/linux_div64.h").read_text()
div_start = div.index("# define do_div(")
div_stop = div.index("\n\n", div_start)
(ROOT / "tests/test_math_macros.h").write_text(div[div_start:div_stop] + "\n" +
    module.translate(math[start:stop], module.HEADER_MAPPING) + "\n")

# Use Python unbounded integers with explicit 64/32-bit result projections as
# an independent oracle for the frozen macro's documented 32-bit divisor domain.
U32 = (1 << 32) - 1
U64 = (1 << 64) - 1
rng = random.Random(0x50574d)
get_inputs = [(p, d, s) for p in [0, 1, 2, 3, 100, U32 - 1, U32]
    for d in [0, 1, 2, U32, (1 << 63), U64 - 1, U64]
    for s in [0, 1, 2, 100, U32 - 1, U32]]
get_inputs += [(rng.randint(1, U32), rng.getrandbits(64), rng.getrandbits(32))
               for _ in range(8192)]
set_inputs = [(p, d, s) for p in [0, 1, 2, 3, U32, (1 << 63), U64 - 1, U64]
    for s in [0, 1, 2, 3, 100, U32 - 1, U32]
    for d in sorted(set([0, 1, s // 2, s, min(U32, s + 1), U32]))]
set_inputs += [(rng.getrandbits(64), rng.getrandbits(32), rng.getrandbits(32))
               for _ in range(8192)]
get_rows = []
for period, duty, scale in get_inputs:
    expected = 0 if period == 0 else (((duty * scale + period // 2) & U64) // period) & U32
    get_rows.append("{ %dULL, %dULL, %dU, %dU }" % (period, duty, scale, expected))
set_rows = []
for period, duty, scale in set_inputs:
    old = rng.getrandbits(64)
    invalid = scale == 0 or duty > scale
    expected = old if invalid else ((duty * period + scale // 2) & U64) // scale
    set_rows.append("{ %dULL, %dULL, %dU, %dU, %s, %dULL }" %
                    (period, old, duty, scale, "-EINVAL" if invalid else "0", expected))
vectors = "struct get_vector { u64 period, duty; unsigned int scale, result; };\n"
vectors += "static const struct get_vector get_vectors[] = {\n" + ",\n".join(get_rows) + "\n};\n"
vectors += "struct set_vector { u64 period, old; unsigned int duty, scale; int error; u64 result; };\n"
vectors += "static const struct set_vector set_vectors[] = {\n" + ",\n".join(set_rows) + "\n};\n"
(ROOT / "tests/vectors.h").write_text(vectors)
(ROOT / "tests/vector-manifest.json").write_text(json.dumps({"seed": "0x50574d",
    "get_count": len(get_rows), "set_count": len(set_rows),
    "getter_domain": "period=0 or 1..UINT32_MAX, scale=uint32, duty=uint64; result=uint32",
    "setter_domain": "period=uint64, scale/duty=uint32; invalid scale/duty preserve state",
    "arithmetic": "unbounded Python oracle; explicit modulo2^64 before division; getter result modulo2^32"}, indent=2) + "\n")

linux_probe = (ROOT / "tests/linux_consumer_probe.inc").read_text()
native_probe = (ROOT / "tests/native_probe_prefix.inc").read_text()
translated = module.translate(linux_probe).replace("NATIVE_ENABLE", "pwm_enable").replace("NATIVE_DISABLE", "pwm_disable")
for order in ["before", "after"]:
    linux_inc = "#include <linux/pwm.h>\n"
    native_inc = "#include <dev/pwm/pwmvar.h>\n"
    incs = native_inc + linux_inc if order == "before" else linux_inc + native_inc
    (ROOT / ("tests/native_probe_" + order + ".c")).write_text(native_probe + incs + translated)

# Keep OF pointer evidence separate from the consumer implementation. Compile
# the exact frozen signatures/bodies with the candidate file-scope declaration.
modes = (ROOT / "modern/include/drm/drm_modes.h").read_text()
start = modes.index("#if defined(CONFIG_OF)\n")
stop = modes.index("#endif\n", start) + len("#endif\n")
prefix = "#include <sys/types.h>\n#include <linux/types.h>\n#include <linux/errno.h>\nstruct drm_display_mode;\n"
suffix = '''
int of_pointer_signature_probe(struct device_node *, struct drm_display_mode *);
int
of_pointer_signature_probe(struct device_node *node, struct drm_display_mode *mode)
{
    int (*display)(struct device_node *, struct drm_display_mode *, u32 *, int) =
        of_get_drm_display_mode;
    int (*panel)(struct device_node *, struct drm_display_mode *, u32 *) =
        of_get_drm_panel_display_mode;
    u32 flags = 0;
    return display(node, mode, &flags, 0) + panel(node, mode, &flags);
}
'''
for name, declaration in [("of_pointer_probe.c", "struct device_node;\n"),
                           ("of_pointer_before_probe.c", "")]:
    (ROOT / "tests" / name).write_text(prefix + declaration + modes[start:stop] + suffix)

# Root's actual current namespace contract is required by the full modern header.
ns_spec = importlib.util.spec_from_file_location("root_namespace", "/root/hp-driver-port-20261005/i915/tools/namespace_linux_compiler_math.py")
ns = importlib.util.module_from_spec(ns_spec)
ns_spec.loader.exec_module(ns)
mapping = ns.bindings(Path("/root/linux-rtl8723be-ref-fresh"))
mapping.update(module.MAPPING)
full = ROOT / "probe_include/drm/drm_modes.h"
full.parent.mkdir(parents=True, exist_ok=True)
full.write_text(ns.translate(modes, mapping))

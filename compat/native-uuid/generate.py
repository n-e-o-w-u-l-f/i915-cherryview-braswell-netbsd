#!/usr/bin/env python3
"""Generate a native UUID/GUID candidate from exact pinned header/algorithm inputs."""
from pathlib import Path
import difflib
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "base"
PINS = {"linux": "fd179f8a05be3ccae366b9b96e176b51fbe54aab",
        "netbsd": "03d918f6d0e81fa05b8f1160eca0628ad39988a6"}
EXPECTED = {
    "native_uuid.h": "a020a9785c1131b1c9dddee7cc62a50d859b4567e3de270cc7fd873895b02f9d",
    "linux_uuid.h": "a7c5418fa73f15fc23a1c04a1580fbe48559a9394254c8b396ec2df6924e029e",
    "linux_uuid.c": "bcb3dce5754b705a10fafcb50c9d40ccc54e280e487beddeaa74a4aa1784d357",
    "native_cprng.h": "18a884fb593368b160aa24dbab538b21bfcb913255ad8537fba64ca4ca1268a4",
    "native_cprng.c": "2e8bdc37be2106bb448d7a0182bb9c8694a1b0120338b2d491617cad410b3884",
    "linux_drm_dp_mst_helper.h": "d0f4dda7b717db766c494e0ec63d72c65291a09c12ede6ec759659c67821f44c",
    "linux_vfio.h": "e2508b895506881f14fa78f774c01caeb54834cd0eb8f5ad0d4bb4465d5755df",
    "native_acpi.c": "ffe6fea145e39e09b01124a3407d5f6eca5226a34cc486e9d07b4f40b894f874",
}
for name, expected in EXPECTED.items():
    if hashlib.sha256((BASE / name).read_bytes()).hexdigest() != expected:
        raise RuntimeError("changed pinned input: " + name)

# Native libuuid has uuid_t/uuid_equal with a different representation/API.
# Translate only Linux-owned C identifiers; never publish global token aliases
# which would change native declarations included later in the same unit.
NAMES = ["uuid_t", "uuid_null", "uuid_equal", "uuid_copy", "import_uuid",
         "export_uuid", "uuid_is_null", "generate_random_uuid", "uuid_gen",
         "uuid_index", "uuid_parse"]
MAPPING = {name: "netbsd_linux_" + name for name in NAMES}
TOKEN = re.compile(r'/\*[\s\S]*?\*/|//(?:\\\r?\n|[^\n])*|"(?:\\[\s\S]|[^"\\])*"|\'(?:\\[\s\S]|[^\'\\])*\'|[A-Za-z_][A-Za-z_0-9]*')

def translate(text):
    return TOKEN.sub(lambda m: MAPPING.get(m[0], m[0]), text)

INCLUDE_HYGIENE = {
    "include/drm/display/drm_dp_mst_helper.h": "#include <linux/types.h>\n",
    "include/linux/vfio.h": "#include <linux/iommu.h>\n",
}

def adapt_includes(text, linux_path):
    """Explicit UUID dependency lost when Linux include chains use native adapters."""
    if linux_path not in INCLUDE_HYGIENE:
        return text
    anchor = INCLUDE_HYGIENE[linux_path]
    addition = anchor + "#include <linux/uuid.h>\n"
    if addition in text:
        return text
    return replace_once(text, anchor, addition)

def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError("expected exactly one match: " + old[:100])
    return text.replace(old, new)

native = (BASE / "native_uuid.h").read_text()
linux = (BASE / "linux_uuid.h").read_text()
header = linux[:linux.index("#ifndef _LINUX_UUID_H_")] + native
header = replace_once(header, "#define _LINUX_UUID_H_\n",
    "#define _LINUX_UUID_H_\n\n#include <sys/types.h>\n#include <sys/systm.h>\n\n"
    "/* Frozen Linux byte-array ABI; native guid_bytes remains an alias. */\n"
    "#define UUID_SIZE 16\n")
header = replace_once(header,
    "typedef struct {\n\tunsigned char guid_bytes[16];\n} guid_t;",
    "typedef struct {\n\tunion {\n\t\tunsigned char b[UUID_SIZE];\n"
    "\t\tunsigned char guid_bytes[UUID_SIZE];\n\t};\n} guid_t;\n\n"
    "typedef struct {\n\tunsigned char b[UUID_SIZE];\n} netbsd_linux_uuid_t;")
uuid_init = linux[linux.index("#define UUID_INIT("):linux.index("/*\n * The length")]
header = replace_once(header, "#define\tUUID_STRING_LEN\t\t36",
    translate(uuid_init) + "#define\tUUID_STRING_LEN\t\t36")
# Native callers still get the same 0/1 validation and first-36-byte contract;
# bool and a compiler warning attribute also match the modern Linux signature.
header = replace_once(header, "static inline int\nuuid_is_valid(const char uuid[static 36])",
    "static inline bool __attribute__((__warn_unused_result__))\n"
    "uuid_is_valid(const char *uuid)")
interfaces = linux[linux.index("extern const guid_t guid_null;"):linux.rindex("#endif")]
interfaces = replace_once(interfaces,
    "bool __must_check uuid_is_valid(const char *uuid);\n", "")
interfaces = interfaces.replace("__u8", "unsigned char")
interfaces = re.sub(r"\bu8\b", "unsigned char", interfaces)
interfaces = interfaces.replace("void generate_random_uuid",
    "/* Generation requires thread/softint context; hard-IRQ parity is OPEN. */\n"
    "void generate_random_uuid", 1)
interfaces = translate(interfaces)
header = replace_once(header, "#endif  /* _LINUX_UUID_H_ */",
    interfaces + "\n#endif  /* _LINUX_UUID_H_ */")

source = (BASE / "linux_uuid.c").read_text()
start = source.index("#include <linux/kernel.h>")
end = source.index("const guid_t guid_null;", start)
source = source[:start] + '''/* Native CPRNG supplies all 16 bytes; no synthetic seed or fallback. */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");
#include <sys/types.h>
#include <sys/cprng.h>
#include <sys/errno.h>
#include <sys/systm.h>
#include <linux/uuid.h>

static void
linux_uuid_random_bytes(unsigned char *buf, size_t len)
{

\t/* Pinned cprng_strong always fills len; thread/softint contexts only. */
\t(void)cprng_strong(kern_cprng, buf, len, 0);
}

static int
linux_uuid_hex_to_bin(unsigned char ch)
{

\tif (ch >= '0' && ch <= '9')
\t\treturn ch - '0';
\tif (ch >= 'a' && ch <= 'f')
\t\treturn ch - 'a' + 10;
\tif (ch >= 'A' && ch <= 'F')
\t\treturn ch - 'A' + 10;
\treturn -1;
}

''' + source[end:]
source = re.sub(r"^EXPORT_SYMBOL(?:_GPL)?\([^\n]+\);\n", "", source, flags=re.M)
validation_start = source.index("/**\n * uuid_is_valid -")
validation_end = source.index("static int __uuid_parse", validation_start)
source = source[:validation_start] + source[validation_end:]
source = source.replace("get_random_bytes(", "linux_uuid_random_bytes(")
source = source.replace("hex_to_bin(", "linux_uuid_hex_to_bin(")
source = source.replace("linux_uuid_linux_uuid_hex_to_bin(", "linux_uuid_hex_to_bin(")
source = source.replace("__u8", "unsigned char")
source = re.sub(r"\bu8\b", "unsigned char", source)
source = translate(source)
ROOT.joinpath("include/linux").mkdir(parents=True, exist_ok=True)
(ROOT / "include/linux/uuid.h").write_text(header)
(ROOT / "linux_uuid.c").write_text(source)
diff = list(difflib.unified_diff(native.splitlines(True), header.splitlines(True),
    "a/sys/external/bsd/drm2/include/linux/uuid.h",
    "b/sys/external/bsd/drm2/include/linux/uuid.h"))
diff.extend(difflib.unified_diff([], source.splitlines(True), "/dev/null",
    "b/sys/external/bsd/drm2/linux/linux_uuid.c"))
acpi_old = (BASE / "native_acpi.c").read_text()
if len(re.findall(r"\bu64\b", acpi_old)) != 6:
    raise RuntimeError("changed native ACPI scalar parameter baseline")
acpi_new = re.sub(r"\bu64\b", "uint64_t", acpi_old)
(ROOT / "native_acpi.c").write_text(acpi_new)
diff.extend(difflib.unified_diff(acpi_old.splitlines(True), acpi_new.splitlines(True),
    "a/sys/external/bsd/drm2/linux/linux_acpi.c", "b/sys/external/bsd/drm2/linux/linux_acpi.c"))
(ROOT / "native-uuid.patch").write_text("".join(diff))
hygiene_diff, hygiene_rows = [], []
for name, linux_path in [("linux_drm_dp_mst_helper.h", "include/drm/display/drm_dp_mst_helper.h"),
                          ("linux_vfio.h", "include/linux/vfio.h")]:
    old = (BASE / name).read_text()
    new = adapt_includes(old, linux_path)
    candidate = ROOT / "modern" / linux_path
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text(new)
    target = "sys/external/bsd/drm2/dist/" + linux_path
    hygiene_diff.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                           "a/" + target, "b/" + target))
    hygiene_rows.append({"linux_path": linux_path, "native_path": target,
        "frozen_sha256": hashlib.sha256(old.encode()).hexdigest(),
        "candidate_sha256": hashlib.sha256(new.encode()).hexdigest()})
(ROOT / "uuid-include-hygiene.patch").write_text("".join(hygiene_diff))
(ROOT / "include-hygiene-manifest.json").write_text(json.dumps({"linux_pin": PINS["linux"],
    "rows": hygiene_rows, "order": "adapt frozen include dependencies before private token translation"}, indent=2) + "\n")
(ROOT / "uuid-namespace.json").write_text(json.dumps({"linux_pin": PINS["linux"],
    "mapping": MAPPING, "scope": "Only frozen Linux-owned source and imported Linux API headers",
    "native_shared": ["guid_t", "GUID_INIT", "uuid_is_valid", "UUID_STRING_LEN"]}, indent=2) + "\n")
(ROOT / "candidate-sha256.json").write_text(json.dumps({
    name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    for name in ["include/linux/uuid.h", "linux_uuid.c", "native_acpi.c", "native-uuid.patch", "uuid-namespace.json",
                 "uuid-include-hygiene.patch", "include-hygiene-manifest.json"]
}, indent=2) + "\n")

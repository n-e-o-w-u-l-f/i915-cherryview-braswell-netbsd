#!/usr/bin/env python3
"""Derive the native kernel-buffer entry from one exact frozen DRM owner.

This is source preparation only.  It does not execute a compiler, alter a
native source tree, or establish native file/VM/driver acceptance.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path

LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
SOURCE = "drivers/gpu/drm/drm_ioctl.c"
STAGED_SOURCE = "sys/external/bsd/drm2/dist/drm/drm_ioctl.c"
# Set to the complete verified frozen input, never a partial function hash.
EXPECTED_SOURCE_SHA256 = "106d88395f14ccb6ef1969e12d8497af8e4f9cba558bfd22ed8f5d8ab69715e5"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("frozen DRM source anchor changed: " + old[:80])
    return text.replace(old, new, 1)


def derive(data):
    if sha(data) != EXPECTED_SOURCE_SHA256:
        raise ValueError("frozen DRM ioctl source SHA256 differs")
    text = data.decode("utf-8")
    text = replace_once(text, "#include <drm/drm_file.h>\n",
        "#include <drm/drm_file.h>\n"
        "#ifdef __NetBSD__\n#include <drm/drm_file_netbsd.h>\n#endif\n")
    text = replace_once(text,
        "long drm_ioctl(struct file *filp,\n\t      unsigned int cmd, unsigned long arg)\n",
        "static long drm_ioctl_dispatch(struct file *filp, unsigned int cmd,\n"
        "\t\t\t       unsigned long arg, void *native_data,\n"
        "\t\t\t       unsigned int *native_out_size)\n")
    text = replace_once(text,
        "\tbool is_driver_ioctl;\n\n\tdev = file_priv->minor->dev;\n",
        "\tbool is_driver_ioctl;\n\n"
        "\tif (native_out_size)\n\t\t*native_out_size = 0;\n\n"
        "\tdev = file_priv->minor->dev;\n")
    text = replace_once(text,
        "\tif (copy_from_user(kdata, (void __user *)arg, in_size) != 0) {\n"
        "\t\tretcode = -EFAULT;\n\t\tgoto err_i1;\n\t}\n",
        "\tif (native_out_size) {\n"
        "\t\tif (in_size)\n\t\t\tmemcpy(kdata, native_data, in_size);\n"
        "\t} else if (copy_from_user(kdata, (void __user *)arg, in_size) != 0) {\n"
        "\t\tretcode = -EFAULT;\n\t\tgoto err_i1;\n\t}\n")
    text = replace_once(text,
        "\tretcode = drm_ioctl_kernel(filp, func, kdata, ioctl->flags);\n"
        "\tif (copy_to_user((void __user *)arg, kdata, out_size) != 0)\n"
        "\t\tretcode = -EFAULT;\n",
        "\tretcode = drm_ioctl_kernel(filp, func, kdata, ioctl->flags);\n"
        "\tif (native_out_size) {\n"
        "\t\tif (out_size)\n\t\t\tmemcpy(native_data, kdata, out_size);\n"
        "\t\t*native_out_size = out_size;\n"
        "\t} else if (copy_to_user((void __user *)arg, kdata, out_size) != 0) {\n"
        "\t\tretcode = -EFAULT;\n\t}\n")
    text = replace_once(text,
        "}\nEXPORT_SYMBOL(drm_ioctl);\n",
        "}\n\n"
        "long drm_ioctl(struct file *filp, unsigned int cmd, unsigned long arg)\n"
        "{\n\treturn drm_ioctl_dispatch(filp, cmd, arg, NULL, NULL);\n}\n"
        "EXPORT_SYMBOL(drm_ioctl);\n\n"
        "#ifdef __NetBSD__\n"
        "/* The native boundary owns exactly _IOC_SIZE(cmd) bytes.  Never\n"
        " * dispatch directly into that buffer: the canonical driver ABI\n"
        " * may be larger.  The shared dispatcher retains all frozen lookup,\n"
        " * permission, unplug, zero-extension and output-on-error rules.\n"
        " */\n"
        "long drm_ioctl_kernel_data(struct file *filp, unsigned int cmd,\n"
        "\t\t\t   void *data, unsigned int *out_size)\n"
        "{\n"
        "\tif (!out_size)\n\t\treturn -EINVAL;\n"
        "\t*out_size = 0;\n"
        "\tif (_IOC_SIZE(cmd) && !data)\n\t\treturn -EINVAL;\n"
        "\treturn drm_ioctl_dispatch(filp, cmd, 0, data, out_size);\n"
        "}\nEXPORT_SYMBOL(drm_ioctl_kernel_data);\n"
        "#endif\n")
    return text.encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.output.is_dir():
        parser.error("output must be an existing owned source directory")
    before = args.source.read_bytes()
    after = derive(before)
    patch = "".join(difflib.unified_diff(
        before.decode("utf-8").splitlines(keepends=True),
        after.decode("utf-8").splitlines(keepends=True),
        "a/" + STAGED_SOURCE, "b/" + STAGED_SOURCE)).encode("utf-8")
    patch_path = args.output / "drm_ioctl_kernel_data.patch"
    contract_path = args.output / "drm_ioctl_kernel_data.json"
    if patch_path.exists() or contract_path.exists():
        parser.error("preserve existing patch/contract; select new outputs")
    contract = {
        "linux_pin": LINUX_PIN,
        "linux_path": SOURCE,
        "staged_path": STAGED_SOURCE,
        "before_sha256": sha(before),
        "after_sha256": sha(after),
        "patch_sha256": sha(patch),
        "limitation": "Source-derived ioctl factor only; native namespace, "
            "file provider, user-ioctl syscall hook and kernel compilation "
            "remain separate mandatory acceptance gates.",
    }
    patch_path.write_bytes(patch)
    contract_path.write_text(json.dumps(contract, indent=2) + "\n",
        encoding="utf-8", newline="\n")
    print("FROZEN_DRM_IOCTL_KERNEL_DATA_PATCH_CREATED")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate a pinned NetBSD VLV/CHV display-error IRQ integration patch.

Frozen Linux: fd179f8a05be3ccae366b9b96e176b51fbe54aab
Frozen NetBSD: 03d918f6d0e81fa05b8f1160eca0628ad39988a6
Implements Linux's EIR/EMR and DPINVGTT ACK/disable sequencing and enables
the VLV master error IRQ. Plane-specific fault reporting is still an OPEN
whole-driver task; do not treat this as a FULL IRQ parity claim.
"""
from pathlib import Path
import argparse
import difflib
import subprocess

LINUX_PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
ROOT = "sys/external/bsd/drm2/dist/drm/i915/"
IRQ = ROOT + "i915_irq.c"
REG = ROOT + "i915_reg.h"

HELPERS = r"""
/* Linux intel_display_irq.c:vlv_display_error_irq_ack(), ported to MMIO API. */
static void
vlv_display_error_irq_ack(struct drm_i915_private *dev_priv,
			  u32 *eir, u32 *dpinvgtt)
{
	u32 emr;

	*eir = I915_READ(VLV_EIR);
	*dpinvgtt = 0;

	if (*eir & VLV_ERROR_PAGE_TABLE) {
		u32 value = I915_READ(DPINVGTT);
		u32 status = value & 0xffff;
		u32 enable = value >> 16;

		/*
		 * Linux: page-table status may remain latched until the
		 * display power well cycles. Ignore already disabled faults
		 * and disable newly stuck status bits after acknowledging.
		 */
		*dpinvgtt = status & enable;
		I915_WRITE(DPINVGTT, status);
		I915_WRITE(DPINVGTT, (enable & ~status) << 16);
	}

	I915_WRITE(VLV_EIR, *eir);

	/* Linux toggles the mask to re-arm the ISR master-error edge. */
	emr = I915_READ(VLV_EMR);
	I915_WRITE(VLV_EMR, 0xffffffff);
	I915_WRITE(VLV_EMR, emr);
}

/*
 * The frozen Linux tree separately reports each faulted plane. That
 * plane-specific callback cannot be transplanted without the newer
 * intel_display plane/IRQ adapter, so record the complete enabled
 * DPINVGTT fault bitmap here; per-plane attribution remains open.
 */
static void
vlv_display_error_irq_handler(u32 eir, u32 dpinvgtt)
{
	DRM_DEBUG("VLV/CHV Master Error, EIR 0x%08x\n", eir);
	if (eir & VLV_ERROR_PAGE_TABLE)
		DRM_ERROR("VLV/CHV display page-table faults: 0x%08x\n",
			  dpinvgtt);
}

"""

def head(root: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()

def exactly(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"{label}: expected one anchor, got {text.count(old)}")
    return text.replace(old, new, 1)

def rewrite_function(src: str, name: str) -> str:
    marker = "static irqreturn_t " + name + "(DRM_IRQ_ARGS)"
    pos = src.find(marker)
    if pos < 0 or src.find(marker, pos + 1) != -1:
        raise RuntimeError("missing/duplicate IRQ function " + name)
    start = src.index("{", pos)
    depth, stop = 0, None
    for idx in range(start, len(src)):
        if src[idx] == "{":
            depth += 1
        elif src[idx] == "}":
            depth -= 1
            if depth == 0:
                stop = idx + 1
                break
    if stop is None:
        raise RuntimeError("unbalanced C body " + name)
    body = src[pos:stop]
    body = exactly(body, "\t\tu32 hotplug_status = 0;",
        "\t\tu32 hotplug_status = 0;\n\t\tu32 eir = 0, dpinvgtt = 0;",
        name + ": irq state")
    pipestat = "\t\ti9xx_pipestat_irq_ack(dev_priv, iir, pipe_stats);"
    body = exactly(body, pipestat,
        pipestat +
        "\n\n\t\tif (iir & I915_MASTER_ERROR_INTERRUPT)\n"
        "\t\t\tvlv_display_error_irq_ack(dev_priv, &eir, &dpinvgtt);",
        name + ": ack before clearing IIR")
    hpd = "\t\tif (hotplug_status)\n\t\t\ti9xx_hpd_irq_handler(dev_priv, hotplug_status);"
    body = exactly(body, hpd,
        "\t\tif (iir & I915_MASTER_ERROR_INTERRUPT)\n"
        "\t\t\tvlv_display_error_irq_handler(eir, dpinvgtt);\n\n" + hpd,
        name + ": report acknowledged error")
    return src[:pos] + body + src[stop:]

def generate(netbsd: Path, linux: Path, output: Path) -> None:
    if head(linux) != LINUX_PIN or head(netbsd) != NETBSD_PIN:
        raise RuntimeError("frozen Linux/NetBSD HEAD mismatch")
    upstream = (linux /
        "drivers/gpu/drm/i915/display/intel_display_irq.c").read_text()
    for name in ["vlv_display_error_irq_ack", "vlv_page_table_error_irq_ack",
                 "vlv_display_irq_postinstall", "vlv_display_error_irq_handler"]:
        if name not in upstream:
            raise RuntimeError("missing Linux source evidence: " + name)

    orig_regs = (netbsd / REG).read_text()
    reg_anchor = "#define VLV_ISR\t\t_MMIO(VLV_DISPLAY_BASE + 0x20ac)\n"
    reg_extra = (
        "#define VLV_EIR\t\t_MMIO(VLV_DISPLAY_BASE + 0x20b0)\n"
        "#define VLV_EMR\t\t_MMIO(VLV_DISPLAY_BASE + 0x20b4)\n"
        "#define VLV_ESR\t\t_MMIO(VLV_DISPLAY_BASE + 0x20b8)\n"
        "#define   VLV_ERROR_PAGE_TABLE\t(1 << 4)\n"
    )
    regs = exactly(orig_regs, reg_anchor, reg_anchor + reg_extra, "VLV regs")

    orig_irq = (netbsd / IRQ).read_text()
    irq = exactly(orig_irq,
        "static irqreturn_t valleyview_irq_handler(DRM_IRQ_ARGS)",
        HELPERS + "static irqreturn_t valleyview_irq_handler(DRM_IRQ_ARGS)",
        "VLV helpers")
    irq = rewrite_function(irq, "valleyview_irq_handler")
    irq = rewrite_function(irq, "cherryview_irq_handler")

    reset_anchor = (
        "\telse\n"
        "\t\tintel_uncore_write(uncore, DPINVGTT, DPINVGTT_STATUS_MASK);\n"
    )
    reset = (
        "\n\t/* Linux _vlv_display_irq_reset(): reset the EIR/EMR bank. */\n"
        "\tintel_uncore_write(uncore, VLV_EMR, 0xffffffff);\n"
        "\tintel_uncore_posting_read(uncore, VLV_EMR);\n"
        "\tintel_uncore_write(uncore, VLV_EIR, 0xffffffff);\n"
        "\tintel_uncore_posting_read(uncore, VLV_EIR);\n"
        "\tintel_uncore_write(uncore, VLV_EIR, 0xffffffff);\n"
        "\tintel_uncore_posting_read(uncore, VLV_EIR);\n"
    )
    irq = exactly(irq, reset_anchor, reset_anchor + reset, "VLV IRQ reset")

    post_anchor = "\tpipestat_mask = PIPE_CRC_DONE_INTERRUPT_STATUS;\n"
    post = (
        "\t/* Linux _vlv_display_irq_postinstall(): enable GTT faults. */\n"
        "\tif (IS_CHERRYVIEW(dev_priv))\n"
        "\t\tintel_uncore_write(uncore, DPINVGTT,\n"
        "\t\t    DPINVGTT_STATUS_MASK_CHV | DPINVGTT_EN_MASK_CHV);\n"
        "\telse\n"
        "\t\tintel_uncore_write(uncore, DPINVGTT,\n"
        "\t\t    DPINVGTT_STATUS_MASK | DPINVGTT_EN_MASK);\n"
        "\tintel_uncore_write(uncore, VLV_EIR, 0xffffffff);\n"
        "\tintel_uncore_posting_read(uncore, VLV_EIR);\n"
        "\tintel_uncore_write(uncore, VLV_EIR, 0xffffffff);\n"
        "\tintel_uncore_posting_read(uncore, VLV_EIR);\n"
        "\tintel_uncore_write(uncore, VLV_EMR, ~VLV_ERROR_PAGE_TABLE);\n"
        "\tintel_uncore_posting_read(uncore, VLV_EMR);\n\n"
    )
    irq = exactly(irq, post_anchor, post + post_anchor, "VLV postinstall")
    mask_anchor = "\t\tI915_DISPLAY_PIPE_B_EVENT_INTERRUPT |\n\t\tI915_LPE_PIPE_A_INTERRUPT |"
    irq = exactly(irq, mask_anchor,
        "\t\tI915_DISPLAY_PIPE_B_EVENT_INTERRUPT |\n"
        "\t\tI915_MASTER_ERROR_INTERRUPT |\n"
        "\t\tI915_LPE_PIPE_A_INTERRUPT |",
        "VLV error enable")
    output.parent.mkdir(parents=True, exist_ok=True)
    parts = []
    for path, old, new in [(REG, orig_regs, regs), (IRQ, orig_irq, irq)]:
        diff = list(difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile="a/" + path, tofile="b/" + path))
        if not diff:
            raise RuntimeError("empty diff: " + path)
        parts.extend(diff)
    output.write_text("".join(parts))
    print(f"VLV_ERROR_PATCH_OK: {len(parts)} diff lines, 2 files")

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--netbsd-tree", type=Path, required=True)
    ap.add_argument("--linux-tree", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    generate(a.netbsd_tree, a.linux_tree, a.out)

if __name__ == "__main__":
    main()

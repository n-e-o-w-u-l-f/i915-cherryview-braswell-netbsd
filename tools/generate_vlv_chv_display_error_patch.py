#!/usr/bin/env python3
"""Generate a pinned NetBSD VLV/CHV display-error IRQ integration patch.

Frozen Linux: fd179f8a05be3ccae366b9b96e176b51fbe54aab
Frozen NetBSD: 03d918f6d0e81fa05b8f1160eca0628ad39988a6
Implements Linux's EIR/EMR and DPINVGTT ACK/disable sequencing and enables
the VLV master error IRQ. Ports frozen Linux VLV/CHV per-plane fault bits and hardware snapshots.
This is only an isolated patch; generic IRQ and kernel integration remain OPEN.
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
 * The frozen Linux plane capture callbacks collect CTL/SURF/SURFLIVE.
 * NetBSD's imported VLV/CHV primary, sprite and cursor register families
 * provide the equivalent hardware snapshots, translated to the old
 * i915_reg_t and I915_READ adapter.
 */
static bool
vlv_display_plane_fault(struct drm_i915_private *dev_priv,
			enum pipe pipe, enum plane_id plane_id)
{
	struct drm_plane *base;
	i915_reg_t ctl, surf, live;
	bool present = false;

	/* Linux skips planes without an installed capture_error callback. */
	drm_for_each_plane(base, &dev_priv->drm) {
		struct intel_plane *plane = to_intel_plane(base);

		if (plane->pipe == pipe && plane->id == plane_id) {
			present = true;
			break;
		}
	}
	if (!present)
		return false;

	switch (plane_id) {
	case PLANE_PRIMARY:
		ctl = DSPCNTR(pipe);
		surf = DSPSURF(pipe);
		live = DSPSURFLIVE(pipe);
		break;
	case PLANE_CURSOR:
		ctl = CURCNTR(pipe);
		surf = CURBASE(pipe);
		live = CURSURFLIVE(pipe);
		break;
	case PLANE_SPRITE0:
	case PLANE_SPRITE1:
		ctl = SPCNTR(pipe, plane_id);
		surf = SPSURF(pipe, plane_id);
		live = SPSURFLIVE(pipe, plane_id);
		break;
	default:
		return false;
	}

	DRM_ERROR("VLV/CHV pipe %d plane %d GTT fault "
		  "(CTL=0x%08x SURF=0x%08x SURFLIVE=0x%08x)\n",
		  pipe, plane_id, I915_READ(ctl), I915_READ(surf),
		  I915_READ(live));
	return true;
}

/* Linux intel_display_irq.c:vlv_pipe_fault_handlers order/bit map. */
static void
vlv_display_error_irq_handler(struct drm_i915_private *dev_priv,
			      u32 eir, u32 dpinvgtt)
{
	static const u32 faults[3][4] = {
		{ PLANEA_INVALID_GTT_STATUS, SPRITEA_INVALID_GTT_STATUS,
		  SPRITEB_INVALID_GTT_STATUS, CURSORA_INVALID_GTT_STATUS },
		{ PLANEB_INVALID_GTT_STATUS, SPRITEC_INVALID_GTT_STATUS,
		  SPRITED_INVALID_GTT_STATUS, CURSORB_INVALID_GTT_STATUS },
		{ PLANEC_INVALID_GTT_STATUS, SPRITEE_INVALID_GTT_STATUS,
		  SPRITEF_INVALID_GTT_STATUS, CURSORC_INVALID_GTT_STATUS },
	};
	static const enum plane_id ids[4] = {
		PLANE_PRIMARY, PLANE_SPRITE0, PLANE_SPRITE1, PLANE_CURSOR
	};
	enum pipe pipe;
	unsigned int i;

	DRM_DEBUG("VLV/CHV Master Error, EIR 0x%08x\n", eir);
	if (!(eir & VLV_ERROR_PAGE_TABLE))
		return;

	for_each_pipe(dev_priv, pipe) {
		for (i = 0; i < 4; i++) {
			u32 fault = faults[pipe][i];

			if (!(dpinvgtt & fault))
				continue;
			if (vlv_display_plane_fault(dev_priv, pipe, ids[i]))
				dpinvgtt &= ~fault;
		}
	}
	if (dpinvgtt)
		DRM_ERROR("VLV/CHV unreported display GTT faults 0x%08x\n",
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
        "\t\t\tvlv_display_error_irq_handler(dev_priv, eir, dpinvgtt);\n\n" + hpd,
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
    for symbol, orig, address in (
        ("_SPASURFLIVE", "_SPASURF", "0x721ac"),
        ("_SPBSURFLIVE", "_SPBSURF", "0x722ac"),
    ):
        old = next((line for line in regs.splitlines(keepends=True)
                    if line.startswith("#define " + orig + "\t")), None)
        if old is None:
            raise RuntimeError("missing NetBSD sprite surface anchor " + orig)
        new = "#define " + symbol + "\t\t(VLV_DISPLAY_BASE + " + address + ")\n"
        regs = exactly(regs, old, old + new, symbol)
    old = next((line for line in regs.splitlines(keepends=True)
                if line.startswith("#define SPSURF(pipe, plane_id)")), None)
    if old is None:
        raise RuntimeError("missing NetBSD SPSURF macro")
    new = ("#define SPSURFLIVE(pipe, plane_id)\t"
           "_MMIO_VLV_SPR((pipe), (plane_id), _SPASURFLIVE, _SPBSURFLIVE)\n")
    regs = exactly(regs, old, old + new, "SPSURFLIVE")

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

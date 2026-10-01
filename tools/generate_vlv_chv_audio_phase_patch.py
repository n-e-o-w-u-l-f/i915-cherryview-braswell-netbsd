#!/usr/bin/env python3
"""Generate a narrowly scoped v5.6->pinned-Linux VLV/CHV audio phase patch.

Reads ONLY the exact frozen NetBSD Git tree; does not mutate that tree.
Reference: Linux fd179f8a05be3ccae366b9b96e176b51fbe54aab,
drivers/gpu/drm/i915/display/g4x_dp.c:g4x_dp_audio_enable and
g4x_hdmi.c:g4x_hdmi_enable_port/g4x_hdmi_audio_enable.
"""
from __future__ import annotations

import argparse
import difflib
from pathlib import Path
import subprocess

PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
ROOT = "sys/external/bsd/drm2/dist/drm/i915/display/"


def once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"expected one original hunk; found {text.count(old)}: {old[:95]!r}")
    return text.replace(old, new, 1)


def dp(text: str) -> str:
    text = once(text, (
        "\tintel_dp->DP |= DP_PORT_EN;\n"
        "\tif (old_crtc_state->has_audio)\n"
        "\t\tintel_dp->DP |= DP_AUDIO_OUTPUT_ENABLE;\n"
    ), (
        "\tintel_dp->DP |= DP_PORT_EN;\n"
        "\t/* Linux g4x_dp_audio_enable(): VLV/CHV audio follows pre-enable. */\n"
        "\tif (old_crtc_state->has_audio &&\n"
        "\t    !IS_VALLEYVIEW(dev_priv) && !IS_CHERRYVIEW(dev_priv))\n"
        "\t\tintel_dp->DP |= DP_AUDIO_OUTPUT_ENABLE;\n"
    ))
    text = once(text, (
        "\tif (pipe_config->has_audio) {\n"
        "\t\tDRM_DEBUG_DRIVER(\"Enabling DP audio on pipe %c\\n\",\n"
        "\t\t\t\t pipe_name(pipe));\n"
        "\t\tintel_audio_codec_enable(encoder, pipe_config, conn_state);\n"
        "\t}\n"
    ), (
        "\tif (pipe_config->has_audio &&\n"
        "\t    !IS_VALLEYVIEW(dev_priv) && !IS_CHERRYVIEW(dev_priv)) {\n"
        "\t\tDRM_DEBUG_DRIVER(\"Enabling DP audio on pipe %c\\n\",\n"
        "\t\t\t\t pipe_name(pipe));\n"
        "\t\tintel_audio_codec_enable(encoder, pipe_config, conn_state);\n"
        "\t}\n"
    ))
    text = once(text, (
        "static void vlv_enable_dp(struct intel_encoder *encoder,\n"
        "\t\t\t  const struct intel_crtc_state *pipe_config,\n"
        "\t\t\t  const struct drm_connector_state *conn_state)\n"
        "{\n"
        "\tintel_edp_backlight_on(pipe_config, conn_state);\n"
        "}\n"
    ), (
        "static void vlv_enable_dp(struct intel_encoder *encoder,\n"
        "\t\t\t  const struct intel_crtc_state *pipe_config,\n"
        "\t\t\t  const struct drm_connector_state *conn_state)\n"
        "{\n"
        "\tstruct drm_i915_private *dev_priv = to_i915(encoder->base.dev);\n"
        "\tstruct intel_dp *intel_dp = enc_to_intel_dp(encoder);\n"
        "\n"
        "\t/* Audio presence and codec setup belong to the enable phase. */\n"
        "\tif (pipe_config->has_audio) {\n"
        "\t\tintel_dp->DP |= DP_AUDIO_OUTPUT_ENABLE;\n"
        "\t\tI915_WRITE(intel_dp->output_reg, intel_dp->DP);\n"
        "\t\tPOSTING_READ(intel_dp->output_reg);\n"
        "\t\tintel_audio_codec_enable(encoder, pipe_config, conn_state);\n"
        "\t}\n"
        "\tintel_edp_backlight_on(pipe_config, conn_state);\n"
        "}\n"
    ))
    return text


def hdmi(text: str) -> str:
    g4x = text.index("static void g4x_enable_hdmi(")
    ibx = text.index("static void ibx_enable_hdmi(", g4x)
    chunk = text[g4x:ibx]
    chunk = once(chunk,
        "\tif (pipe_config->has_audio)\n\t\ttemp |= HDMI_AUDIO_ENABLE;\n",
        "\tif (pipe_config->has_audio &&\n"
        "\t    !IS_VALLEYVIEW(dev_priv) && !IS_CHERRYVIEW(dev_priv))\n"
        "\t\ttemp |= HDMI_AUDIO_ENABLE;\n")
    chunk = once(chunk,
        "\tif (pipe_config->has_audio)\n"
        "\t\tintel_enable_hdmi_audio(encoder, pipe_config, conn_state);\n",
        "\tif (pipe_config->has_audio &&\n"
        "\t    !IS_VALLEYVIEW(dev_priv) && !IS_CHERRYVIEW(dev_priv))\n"
        "\t\tintel_enable_hdmi_audio(encoder, pipe_config, conn_state);\n")
    text = text[:g4x] + chunk + text[ibx:]
    text = once(text, (
        "static void vlv_enable_hdmi(struct intel_encoder *encoder,\n"
        "\t\t\t    const struct intel_crtc_state *pipe_config,\n"
        "\t\t\t    const struct drm_connector_state *conn_state)\n"
        "{\n"
        "}\n"
    ), (
        "static void vlv_enable_hdmi(struct intel_encoder *encoder,\n"
        "\t\t\t    const struct intel_crtc_state *pipe_config,\n"
        "\t\t\t    const struct drm_connector_state *conn_state)\n"
        "{\n"
        "\tstruct drm_i915_private *dev_priv = to_i915(encoder->base.dev);\n"
        "\tstruct intel_hdmi *intel_hdmi = enc_to_intel_hdmi(encoder);\n"
        "\tu32 temp;\n"
        "\n"
        "\tif (!pipe_config->has_audio)\n"
        "\t\treturn;\n"
        "\n"
        "\t/* Linux g4x_hdmi_audio_enable(): set presence after port enable. */\n"
        "\ttemp = I915_READ(intel_hdmi->hdmi_reg);\n"
        "\ttemp |= HDMI_AUDIO_ENABLE;\n"
        "\tI915_WRITE(intel_hdmi->hdmi_reg, temp);\n"
        "\tPOSTING_READ(intel_hdmi->hdmi_reg);\n"
        "\tintel_enable_hdmi_audio(encoder, pipe_config, conn_state);\n"
        "}\n"
    ))
    return text


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--netbsd-tree", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    args = p.parse_args()
    head = subprocess.check_output(
        ["git", "-C", str(args.netbsd_tree), "rev-parse", "HEAD"],
        text=True).strip()
    if head != PIN:
        raise ValueError(f"wrong NetBSD source pin: {head} != {PIN}")
    hunks = []
    for name, transform in [("intel_dp.c", dp), ("intel_hdmi.c", hdmi)]:
        rel = ROOT + name
        original = subprocess.check_output(
            ["git", "-C", str(args.netbsd_tree), "show", "HEAD:" + rel],
            text=True)
        modified = transform(original)
        diff = "".join(difflib.unified_diff(
            original.splitlines(keepends=True), modified.splitlines(keepends=True),
            fromfile="a/" + rel, tofile="b/" + rel, n=5,
        ))
        if not diff:
            raise ValueError(f"empty patch: {name}")
        hunks.append("diff --git a/" + rel + " b/" + rel + "\n" + diff)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(hunks))
    print(f"I915_AUDIO_PATCH_OK files=2 NetBSD={head}")


if __name__ == "__main__":
    main()

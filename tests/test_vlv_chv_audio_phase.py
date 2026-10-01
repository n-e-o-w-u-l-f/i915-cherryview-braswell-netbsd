#!/usr/bin/env python3
"""Test the real VLV/CHV enable-stage functions extracted from patch output.

Host-only compile and mocked MMIO/order test. NOT a NetBSD kernel build or
hardware/KMS validation.
"""
from __future__ import annotations

from pathlib import Path
import runpy
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NETBSD = Path("/opt/ChatGPT/hp-driver-port/netbsd")
REL = "sys/external/bsd/drm2/dist/drm/i915/display/"
GEN = ROOT / "tools/generate_vlv_chv_audio_phase_patch.py"
PATCH = ROOT / "patches/0005-vlv-chv-dp-hdmi-audio-phase-linux-netbsd11.patch"


def original(name: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(NETBSD), "show", "HEAD:" + REL + name],
        text=True,
    )


def extract(source: str, name: str) -> str:
    marker = "static void " + name + "("
    pos = source.find(marker)
    if pos < 0 or source.find(marker, pos + 1) != -1:
        raise AssertionError("missing/non-unique function " + name)
    start = source.index("{", pos)
    depth = 0
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[pos:i + 1]
    raise AssertionError("unclosed function " + name)


PRELUDE = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32; /* LinuxKPI type supplied by NetBSD in kernel. */

struct drm_device { int unused; };
struct intel_encoder { struct { struct drm_device *dev; } base; };
struct intel_crtc_state { bool has_audio; };
struct drm_connector_state { int unused; };
struct drm_i915_private { int unused; };
struct intel_dp { uint32_t DP; unsigned output_reg; };
struct intel_hdmi { unsigned hdmi_reg; };
#define DP_AUDIO_OUTPUT_ENABLE (1U << 8)
#define HDMI_AUDIO_ENABLE (1U << 9)

static struct drm_i915_private priv;
static struct intel_dp dp;
static struct intel_hdmi hdmi;
static uint32_t regs[8];
static unsigned events[16], nevents, codecs, backlights;

static struct drm_i915_private *to_i915(struct drm_device *dev)
{ (void)dev; return &priv; }
static struct intel_dp *enc_to_intel_dp(struct intel_encoder *encoder)
{ (void)encoder; return &dp; }
static struct intel_hdmi *enc_to_intel_hdmi(struct intel_encoder *encoder)
{ (void)encoder; return &hdmi; }
#define I915_READ(r) ((void)dev_priv, regs[(r)])
#define I915_WRITE(r, v) do { (void)dev_priv; regs[(r)] = (v); events[nevents++] = 1; } while (0)
#define POSTING_READ(r) do { (void)regs[(r)]; events[nevents++] = 2; } while (0)
static void intel_audio_codec_enable(struct intel_encoder *encoder,
    const struct intel_crtc_state *s, const struct drm_connector_state *c)
{ (void)encoder; (void)s; (void)c; events[nevents++] = 3; codecs++; }
static void intel_enable_hdmi_audio(struct intel_encoder *encoder,
    const struct intel_crtc_state *s, const struct drm_connector_state *c)
{ intel_audio_codec_enable(encoder, s, c); }
static void intel_edp_backlight_on(const struct intel_crtc_state *s,
    const struct drm_connector_state *c)
{ (void)s; (void)c; events[nevents++] = 4; backlights++; }
"""

MAIN = r"""
int main(void)
{
    struct drm_device device = {0};
    struct intel_encoder encoder = { .base = { .dev = &device } };
    struct intel_crtc_state s = {0};
    struct drm_connector_state c = {0};

    dp.output_reg = 1;
    dp.DP = 0x800;
    vlv_enable_dp(&encoder, &s, &c);
    assert(nevents == 1 && events[0] == 4);
    assert(codecs == 0 && backlights == 1);
    assert(regs[1] == 0);

    s.has_audio = true;
    nevents = 0;
    vlv_enable_dp(&encoder, &s, &c);
    assert(nevents == 4 && events[0] == 1 && events[1] == 2);
    assert(events[2] == 3 && events[3] == 4);
    assert((dp.DP & DP_AUDIO_OUTPUT_ENABLE) != 0);
    assert(regs[1] == dp.DP && codecs == 1 && backlights == 2);

    hdmi.hdmi_reg = 2;
    regs[2] = 0x400;
    s.has_audio = false;
    nevents = 0;
    vlv_enable_hdmi(&encoder, &s, &c);
    assert(nevents == 0 && regs[2] == 0x400 && codecs == 1);

    s.has_audio = true;
    vlv_enable_hdmi(&encoder, &s, &c);
    assert(nevents == 3 && events[0] == 1 && events[1] == 2 &&
           events[2] == 3);
    assert(regs[2] == (0x400 | HDMI_AUDIO_ENABLE) && codecs == 2);
    puts("I915_AUDIO_PHASE_OK: DP/HDMI audio after port setup; no-audio safe");
    return 0;
}
"""


def main() -> None:
    generate = runpy.run_path(str(GEN))
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        output = tmp / "generated.patch"
        subprocess.run(["python3", str(GEN), "--netbsd-tree", str(NETBSD),
                        "--out", str(output)], check=True)
        if output.read_bytes() != PATCH.read_bytes():
            raise AssertionError("canonical patch differs from frozen generator")
        print("I915_AUDIO_PATCH_BYTE_MATCH_OK")
        dp = generate["dp"](original("intel_dp.c"))
        hdmi = generate["hdmi"](original("intel_hdmi.c"))
        # Check the pre-enable path cannot trigger VLV/CHV audio.
        assert "if (old_crtc_state->has_audio &&\n\t    !IS_VALLEYVIEW" in dp
        assert "if (pipe_config->has_audio &&\n\t    !IS_VALLEYVIEW" in dp
        assert "if (pipe_config->has_audio &&\n\t    !IS_VALLEYVIEW" in hdmi
        code = (PRELUDE + "\n" + extract(dp, "vlv_enable_dp") + "\n" +
                extract(hdmi, "vlv_enable_hdmi") + "\n" + MAIN)
        src, exe = tmp / "audio_test.c", tmp / "audio_test"
        src.write_text(code)
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                        "-pedantic", str(src), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    main()

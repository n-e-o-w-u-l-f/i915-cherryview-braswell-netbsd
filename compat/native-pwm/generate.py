#!/usr/bin/env python3
"""Derive the disabled PWM consumer profile from the exact frozen Linux API."""
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
    "native_pwm.h": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "linux_pwm.h": "0edf8e8abb8d79335d6dea27df20aa032a4178eb1d58653e16ded48fcf78393e",
    "linux_pwm_Kconfig": "ab3523430a4f3512eb290564270fdaef28fdd5a591f54e356ed89be0409801c7",
    "linux_i915_Kconfig": "673d9eb80ad622c559fc2dac0f1bcffc80d9bd6c154a90f612d807cf4876f262",
    "linux_drm_modes.h": "89fd24d07f8e9852705ff51d563ce645b2ecb90f310f69baad748562998d08e5",
    "native_pwmvar.h": "3f858fb95a2d3b7002eb10186359d4a4f2ccc8d48aa31c94e5ada8164788dfd4",
    "native_pwm.c": "b1b9123a04eb64d4fceb5ca4d596b6e38637dda23a2a312a79328fb9c3d05ce7",
    "native_files_pwm": "767e37a69735b13523504d13a08be73df84ac5a2faab6f4be45ab3200ce4ba6f",
    "native_lpssreg.h": "7874a697206e3e543adadf2bed95173c27daac56f5240ad4e4136d8ba6fe2e06",
    "linux_math.h": "e0437f2850ef21b25d7f574830d2213cfc97441883624577d7bf1fd7e61adcf1",
    "linux_of.h": "cef3c80f7b56a4e4e280780baf314f4b8495ccd0dd929ac08d6a08363f11ccbc",
    "native_err.h": "0d878c3aa7c480164dbbb125ff40226df3a9459ae9c94c98a6a4229e31c55119",
    "native_list.h": "0049e571462e5fae2f910e14647f844fcc3ae9d9c7ba50b67626f0aac70bbea0",
    "native_types.h": "54b523717eb9f2ed1d4441cf215a08b3a9905e629ecf36285c52c301e7afdeb9",
    "linux_div64.h": "288acb881f07893b78dde25bd9df2185db53442a38dc42de4ece20e34a7ccdb9",
}
for name, expected in EXPECTED.items():
    if hashlib.sha256((BASE / name).read_bytes()).hexdigest() != expected:
        raise RuntimeError("changed frozen/native input: " + name)

# These three identifiers conflict with the real native PWM framework.
# Do not publish macros that would rename later native declarations.
MAPPING = {name: "netbsd_linux_" + name
           for name in ["pwm_polarity", "pwm_enable", "pwm_disable"]}
HEADER_MAPPING = dict(MAPPING, DIV_ROUND_CLOSEST_ULL="netbsd_linux_DIV_ROUND_CLOSEST_ULL")
TOKEN = re.compile(r'/\*[\s\S]*?\*/|//(?:\\\r?\n|[^\n])*|"(?:\\[\s\S]|[^"\\])*"|\'(?:\\[\s\S]|[^\'\\])*\'|[A-Za-z_][A-Za-z_0-9]*')

def translate(text, mapping=MAPPING):
    return TOKEN.sub(lambda m: mapping.get(m[0], m[0]), text)

def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError("expected one frozen anchor: " + old[:100])
    return text.replace(old, new)

def mark_parameters_used(text):
    """The native strict profile also accepts disabled bodies with unused args."""
    pattern = re.compile(r"(static inline\b[^{;]*?\(([^()]*)\)\s*\n\{\n)")
    def add(match):
        names = [re.search(r"([A-Za-z_][A-Za-z_0-9]*)\s*$", param).group(1)
                 for param in match[2].split(",") if param.strip() not in ("", "void")]
        return match[1] + "".join("\t(void)" + name + ";\n" for name in names)
    return pattern.sub(add, text)

linux = (BASE / "linux_pwm.h").read_text()
common = linux[linux.index("struct pwm_chip;"):linux.index("#define PWM_WFHWSIZE")]
enabled = linux.index("#if IS_REACHABLE(CONFIG_PWM)")
disabled_start = linux.index("#else\n", enabled) + len("#else\n")
disabled_end = linux.index("#endif\n", disabled_start)
disabled = mark_parameters_used(linux[disabled_start:disabled_end])
disabled = disabled.replace("might_sleep();", "ASSERT_SLEEPABLE();")
lookup_start = linux.index("struct pwm_lookup {", disabled_end)
lookup_end = linux.index("#if IS_REACHABLE(CONFIG_PWM)", lookup_start)
lookup = linux[lookup_start:lookup_end]
tables_start = linux.index("#else\n", lookup_end) + len("#else\n")
tables_end = linux.index("#endif\n", tables_start)
tables = mark_parameters_used(linux[tables_start:tables_end])
header = '''/* SPDX-License-Identifier: GPL-2.0 */
#ifndef __LINUX_PWM_H
#define __LINUX_PWM_H

/*
 * Exact frozen consumer contract for the selected CONFIG_PWM-disabled profile.
 * Enabled native resource lookup, chip lifetime and LPSS PWM support are OPEN.
 * Never silently select the disabled branch for an enabled kernel/profile.
 */
#if (defined(CONFIG_PWM) && CONFIG_PWM) || \\
    (defined(CONFIG_PWM_MODULE) && CONFIG_PWM_MODULE)
#error "NetBSD enabled PWM consumer/provider and LPSS runtime are not ported"
#endif

#include <sys/types.h>
#include <sys/systm.h>
#include <linux/types.h>
#include <linux/errno.h>
#include <linux/err.h>
#include <linux/list.h>
#include <linux/math.h>

struct device;
struct fwnode_handle;

'''
header += translate(common + disabled + "\n" + lookup + tables, HEADER_MAPPING)
header += "\n#endif /* __LINUX_PWM_H */\n"
(ROOT / "include/linux").mkdir(parents=True, exist_ok=True)
(ROOT / "include/linux/pwm.h").write_text(header)
target = "sys/external/bsd/drm2/include/linux/pwm.h"
patch = difflib.unified_diff((BASE / "native_pwm.h").read_text().splitlines(True),
    header.splitlines(True), "a/" + target, "b/" + target)
(ROOT / "native-pwm.patch").write_text("".join(patch))
(ROOT / "pwm-namespace.json").write_text(json.dumps({"linux_pin": PINS["linux"],
    "mapping": MAPPING, "scope": "Only frozen Linux-owned sources/API headers; native PWM owners retain their names",
    "existing_dependency": {"DIV_ROUND_CLOSEST_ULL": "netbsd_linux_DIV_ROUND_CLOSEST_ULL"},
    "profile": "CONFIG_PWM absent or zero; CONFIG_PWM=1/CONFIG_PWM_MODULE=1 must fail compilation",
    "provider_status": "OPEN"}, indent=2) + "\n")

def adapt_of_pointer(text, linux_path):
    """A prototype pointer needs the canonical file-scope tag, not OF fields."""
    if linux_path != "include/drm/drm_modes.h":
        return text
    new = "struct videomode;\nstruct device_node;\n"
    if new in text:
        return text
    return replace_once(text, "struct videomode;\n", new)

old = (BASE / "linux_drm_modes.h").read_text()
new = adapt_of_pointer(old, "include/drm/drm_modes.h")
modern = ROOT / "modern/include/drm/drm_modes.h"
modern.parent.mkdir(parents=True, exist_ok=True)
modern.write_text(new)
target = "sys/external/bsd/drm2/dist/include/drm/drm_modes.h"
(ROOT / "of-pointer-hygiene.patch").write_text("".join(difflib.unified_diff(
    old.splitlines(True), new.splitlines(True), "a/" + target, "b/" + target)))
(ROOT / "of-pointer-manifest.json").write_text(json.dumps({"linux_pin": PINS["linux"],
    "linux_path": "include/drm/drm_modes.h", "native_path": target,
    "frozen_sha256": hashlib.sha256(old.encode()).hexdigest(),
    "candidate_sha256": hashlib.sha256(new.encode()).hexdigest(),
    "scope": "Opaque canonical device_node pointer only; no OF provider or node fields",
    "order": "adapt frozen source before root token namespace baseline"}, indent=2) + "\n")
(ROOT / "candidate-sha256.json").write_text(json.dumps({name:
    hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in [
    "include/linux/pwm.h", "native-pwm.patch", "pwm-namespace.json",
    "modern/include/drm/drm_modes.h", "of-pointer-hygiene.patch", "of-pointer-manifest.json"]
}, indent=2) + "\n")

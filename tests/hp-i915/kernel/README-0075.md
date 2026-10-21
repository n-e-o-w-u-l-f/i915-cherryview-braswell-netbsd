# HP-I915 0075 — NetBSD 11 daily 0066 archive SHA512 offline validator

**Scope:** A completely offline verifier for three **exact** files in the NetBSD 11 daily snapshot `netbsd-11/20261021045729Z/amd64/binary/sets/`: `rescue.tar.xz`, `etc.tar.xz`, `base.tar.xz`.

- [Official same-snapshot checksum manifest](https://nycdn.netbsd.org/pub/NetBSD-daily/netbsd-11/20261021045729Z/amd64/binary/sets/SHA512) is currently publicly visible and its **three digest strings match** those printed in the historical HP-I915 0066 report (3/3).
- This verifier **does not download**, invoke external programs, mount, decompress, write to or execute a NetBSD guest; it reads a supplied local `SHA512` file and all three archive binaries in streaming mode, then checks pinned snapshot names, manifest digest text, original byte lengths and recomputed SHA512.
- It rejects malformed/duplicate manifest entries, missing files, symlinks, size mismatch and hash mismatch. A checksum string-only match cannot result in `PASS`: **all three real archive files must be readable and match**.
- The script's built-in seven synthetic self-tests passed in an isolated local Python 3 environment on 2026-10-21. Published Git blob equals tested local Git blob `f2c5bcb01fa8656ca34eb9b6971caf39d2176847`. This is **not proof** that the original NetBSD archive contents were independently hashed today.
- Original read-only/public retrieval via the separate local verifier environment could not resolve `nycdn.netbsd.org` (`curl` exit 6). No actual archive-byte verification was carried out in 0075. The 0071 denied Legion source read **must not be rerouted** via this utility.

Self-test, runnable anywhere with Python 3 and a disposable synthetic test environment:

```sh
python3 verify_netbsd11_0066_sets_0075.py --self-test
```

**Actual archive-byte check: ONLY after an independently authorized operator has staged exactly the three original archives plus `SHA512`, without using a denied 0071 access route:**

```sh
python3 verify_netbsd11_0066_sets_0075.py \
  --sets-dir /path/to/verified-netbsd-11-20261021045729Z-sets \
  --manifest /path/to/verified-netbsd-11-20261021045729Z-sets/SHA512
```

Exit 0 and `status: PASS` require *all* manifest and file checks. Exit 2 indicates FAIL or ERROR; preserve its JSON output in the future provenance audit. The verifier does not validate the cryptographic authenticity or trusted distribution channel of the manifest itself; independently pin and attest that source.

Source pin: `NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6`. HP target, i915, Nouveau and Bootloader were **not touched**. [Governance 0075](https://github.com/n-e-o-w-u-l-f/Agent-Governance/blob/main/docs/HP-I915-0075-0066-SET-SHA512-MANIFEST-REVERIFICATION-20261021.md).

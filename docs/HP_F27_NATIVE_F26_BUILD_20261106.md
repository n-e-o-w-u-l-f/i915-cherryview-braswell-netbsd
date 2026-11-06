# F27: native HP F26 test-kernel build verified — 2026-11-06

## Result and limits

**PASS:** clean native NetBSD 11 amd64 F26 kernel compile/link on the actual HP, followed by an independent artifact verifier. Build exit 0; verifier exit 0. Build elapsed 2709 seconds (45 min 09 s). No installed kernel, boot configuration, EFI, firmware or radio change. The kernel was not installed or booted.

This result covers the older native Cherryview composition with eleven F26 patches and the older partial RTL PHY stage. It is **not** acceptance of the recovered modern 410-unit port, current complete RTL runtime, physical display/KMS, WPA2, suspend/resume or recovery. The F26 candidate remains compile-only and must not be installed/booted as a complete driver release. Conditional repository cleanup was not performed.

## Exact identities

| Component | Verified identity |
|---|---|
| Native host | hp-tpnw121.lan; andreas uid1000/gid100; NetBSD11 amd64 F77 |
| Actual build checkout | `5c7ac64c8c740701365dfbf3bf9159cc13fcf344`, clean |
| F26 base | `b863e1ef62adf5d9793a84aaa3255c13c5030434` |
| Artifact verifier | `f1f4fcd5345c91fb2d5dc5fd989866e282f9e3d4`; blob `903cf7613b627dbcc4ac3bafc44a6b4ba2e9b5d8` |
| NetBSD source | `03d918f6d0e81fa05b8f1160eca0628ad39988a6` |
| NetBSD archive SHA256 | `3645aca2c1ac9716558075b7747a98583a8e87435f00ff30c786b4b438dbe15b` |
| Native RTL PHY source | `df3bc40086d38dcf0e25628c22c06f8c7674fe3d`; 56 exact source blobs, 25 C units |
| Separate latest RTL runtime WIP | `438931eec65d6cf145f5ea2304e4bf12b9826ddd`; not the F26 build input |
| Separate modern i915 recovery | `fd61cceac3774f68795f6bd91b241889c3b69f13`; not the F26 build input |
| Compiler/tools | NetBSD GCC12.5; /usr/bin/make; /usr/pkg/bin/git; /usr/pkg/bin/python3 3.14.7 |
| Hardware observation | HP Notebook / HP8205 board; Celeron N3060 @1.60GHz, 2 CPUs; 4112666624 RAM bytes; UEFI Insyde F.34 dated20200528 |

Exact marketing model/PCI identity remain historical source facts because unprivileged /dev/pci0 access was denied. No PCI revision, EDID or successful physical output is inferred.

## Reproducible native execution

Source staging: `/home/andreas/projects/hp-i915-f26-20261106/src-03d918f6d0e81fa05b8f1160eca0628ad39988a6`.
Clean project clone: `/home/andreas/projects/hp-i915-f26-20261106/i915`.
Private build output: `/tmp/hp-i915-f26-build-20261106-a01`.

Executed from the clean project checkout:

```sh
/usr/pkg/bin/python3 -u tools/run_f26_native_chv_kernel.py \
  --ack-compile-only \
  --source-stage /home/andreas/projects/hp-i915-f26-20261106/src-03d918f6d0e81fa05b8f1160eca0628ad39988a6 \
  --toolchain /usr/obj/tooldir.NetBSD-11.0-amd64 \
  --output /tmp/hp-i915-f26-build-20261106-a01 \
  --jobs 2 --timeout-seconds 21600
```

This command documents the completed run, not a request to rerun into the existing output. The original toolchain was copied privately. No old object reuse. Source-stage preparation verifies the archive and 56 RTL blobs; the native runner verifies 17 original NetBSD blobs and eleven patch blobs/path sets before applying them. The separately hash-verified artifact checker ran only after native-build.exit=0 and did not alter the clean build checkout.

Two source improvements enabled reproducibility: an exact-source stage preparer and a bounded 60..86400-second configurable timeout (default retained at3400 seconds). The run used21600 seconds. No timeout failure was reproduced in this successful run. Previously provider-denied model operations were not rerouted.

## Independent artifact checks

- ELF64 AMD64 executable, 29652840 bytes.
- Actual native `nbmake-amd64 -V '${OBJS}'` returned 3264 configured objects; every object exists.
- 39 driver/configuration objects hashed: all13 modified C units, all25 older RTL PHY units, and ioconf.o.
- Both `i915drmkms_ca` and `rtwn8723be_native_ca` are linked in the final kernel.
- Native `nm -u` on the final kernel returned no unresolved symbols.
- Eleven patch blobs,17 original source blobs,17 post-patch source SHA256s and56 RTL input blobs checked.
- Installed /netbsd and /boot.cfg SHA256s remain exactly equal to the recorded pre-build baseline.

Inherited F25 messages in the runner log are historical labels; the actual F26 acceptance marker is `F26_NATIVE_HP_11_PATCH_17_FILE_CLEAN_KERNEL_COMPILE_LINK_PASS`. F26 verified eleven patches and seventeen originals. Object/link checks establish composition, not device behavior.

## Durable artifacts and debugging

All70 selected kernel/debug/log/source/object files (363926901 bytes) were copied and independently SHA256-verified in:

`/home/andreas/projects/hp-i915-f26-20261106/artifacts-f26-a01`

The durable `manifest.json` identifies every source path, saved path, size and hash. Under that directory, `kernel/` contains the following corresponding files:

| File | Bytes | SHA256 |
|---|---:|---|
| `netbsd` | 29652840 | `d845e4c33ef26222641c20084ba46d7a31d3049ce9e281a9db88b99fb62092d2` |
| `netbsd-F26_CHV_FULL_RTL_TEST.debug` | 92916376 | `d2cbec65f93ed8c707d51057e76a6fe67a5fd7044494f6b829e8c773293ee75f` |
| `netbsd.gdb` | 189362736 | `3e49982536568de23e580eee6439f73701b8d3f6a1624a83821e76ae5cdbdabd` |
| `netbsd.ldscript` | 1142 | `e5e791c40fd5ba3c51faf95f87875ae7fa9fba88255e777284b3fae01f6a5892` |
| `netbsd.map` | 13198053 | `9c3ef10aa99eaab8386dfedcf6510b58a0a3e580359cdc1a0663c3d35f246c1b` |

The durable `evidence/` directory contains full kernel-build and runner/verifier logs, terminal exits, original source manifest, artifact receipt and complete symbol map. `objects/` retains39 verified driver/config objects; `patched-source/` retains17 exact patched native sources. The clean source stage remains in the user-owned home workspace. A failed or lost /tmp tree therefore does not remove these debugging artifacts.

The [machine-readable receipt](evidence/HP_F27_NATIVE_F26_BUILD_20261106.json) contains complete provenance, hashes, source manifest, native checks and durable-file manifest. Debug binaries are retained on HP; only structured textual evidence is committed.

Protected installed hashes:

- /netbsd: `9b65629c0527bbd40f7ffa0d4ef0c59a32b5edceb597a5df8c86d1e7be1c8fde`
- /boot.cfg: `f7e0ccc00308172d5787f47c2c66b33921c53341f896e2339079a66980b6a4df`

F77 default entry1 and i915-disabled recovery remain unchanged.

## Fleet reconciliation and knowledge handoff

All six requested hosts were inspected in available developer roots. PHOBOS used its existing BMAX SSH route; HP root/megal-owned areas were partly inaccessible. This is not a claim to have read every protected filesystem.

146 unpublished BMAX source files are preserved on i915 debug fd61ccea with exact remote blob verification.46 dirty Legion RTL source files are preserved at80d3204c307056b116a7476f70172773260319cf with exact readback. Additional original histories6ab2012 (BMAX i915) andcda48e5 (Legion RTL) are preserved under dated recovery tags. Original worktrees/indexes remain intact; divergent history is not merged solely by timestamp.

The [Dr.Debug collection](https://github.com/doktor-debug/.memory/tree/main/MEMORY/DRIVERS/NETBSD_HP_I915_RTL8723BE) holds378 complete authored document snapshots and65 structured diagnostic source reports,443 exact blobs representing700 pinned source references, plus current fleet/tool/hardware/package facts and execution evidence. Historical statements are retained as dated evidence, not promoted to current acceptance.

## Next acceptance gate

Review/integrate the recovered modern FILE/MM/DRM providers and current RTL runtime against the pinned contracts, establish their full native object/kernel integration, and perform governed physical KMS/WPA2/recovery validation on an appropriate candidate. This F26 compile-only artifact does not satisfy those gates. Keep all relevant kernel/debug material until successful physical-driver tests establish the user's cleanup condition.

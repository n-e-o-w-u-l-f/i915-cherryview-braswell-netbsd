# HP i915 checkpoint, 2026-10-06

STATE: IN_PROGRESS. Full port acceptance remains OPEN. Builds/install: HP only.

## PWM consumer and direct header dependencies

Patch0034 implements the true frozen CONFIG_PWM-disabled consumer types, state
helpers, rounding and error/release bodies. Enabled PWM/LPSS consumer ownership,
lookup and providers are still explicitly rejected. Native PWM names coexist
through three private Linux bindings. No fake device_node or dentry layouts
are introduced: their file-scope declarations establish opaque tag identity.
Modern DRM includes actual native completion for three embedded fields and
actual ktime for its vblank callback; UUID/vfio dependencies remain preserved.

All 35 source/C scripts pass on HP. The PWM proof validates 13 checks including
four expected negative compilations, actual arithmetic bodies against 8486
getter and 8448 setter Python-oracle cases, real Native coexistence, relocatable
link and complete-type tests using the shared modern headers. The fresh selected
410-source/Kconfig audit is reproduced in each test without an agent directory.
The full OF-header probe now compiles too; it proves opaque prototypes only.

Both fresh real modern drm_buddy and dvo_ch7017 objects now compile with -Werror.
Their source bytes are preserved during the explicit mtime refresh. The proof
recorder was corrected to derive a newly successful object's artifact path
when its prior failed record lacked one. First direct-header errors and that
proof-metadata failure are retained rather than presented as compiler passes.

See [HP PWM consumer evidence](evidence/HP_NATIVE_PWM_CONSUMER_20261006.json).
The namespace now has 92 private bindings and six version3 include contracts.
Full410/kernel/lifecycle, MM/folio/UVM, native task entry/fatal/code ownership,
enabled PWM/LPSS providers and physical KMS remain OPEN. No installation or
reboot; boot/running/F77 recovery hashes remain unchanged.

## Earlier checkpoints

### HP i915 checkpoint, 2026-10-06

STATE: IN_PROGRESS. Full port acceptance remains OPEN. Builds/install: HP only.

## Native UUID/GUID and explicit type dependencies

Patch0033 implements the frozen 16-byte UUID/GUID APIs, endian initializers,
full-byte copy/compare/null/import/export, parse and version4 generation with
real NetBSD cprng_strong. The GUID byte-array alias preserves native ACPI layout.
Six ACPI scalar parameter spellings now match their retained uint64_t prototypes.
Native libuuid types and declarations coexist with eleven private Linux UUID
bindings. Explicit UUID includes repair the real DP-MST and vfio dependencies.

All 34 source/C scripts pass on HP. Four fresh real Native objects, including
the actual ACPI body, compile with -Werror and link with no unresolved UUID/GUID
API. Five actual-code algorithm groups cover 1024 OS-entropy adapter fills and
512 parse roundtrips; they do not execute kernel cprng_strong or prove hard-IRQ
generation. The native object has the real cprng_strong/kern_cprng references.

The owned namespace ledger now has 89 bindings and versioned include contracts.
Reproduction applies the prior task-runtime build graph before adding UUID.
The retained first suite failed only its missing audit metadata source; all
native compilation and algorithm tests had passed before the complete rerun.

See [HP UUID/GUID evidence](evidence/HP_NATIVE_UUID_GUID_20261006.json).
Fresh modern buddy compilation passes. DVO compilation no longer reports GUID,
wait-queue or kthread-work types; completion/device_node/PWM remain real errors.
Full410 compilation/link, native MM/folio/UVM and task entry/fatal/lifetime
integration, and physical KMS remain required. No installation or reboot;
boot/running/F77 recovery hashes are unchanged.

## Earlier checkpoints

### HP i915 checkpoint, 2026-10-06

STATE: IN_PROGRESS. Full port acceptance remains OPEN. Build and installation: HP only.

## Common task, callback waits and immediate workers

Patch0032 integrates one native task identity and real generic wait callback
queues, keyed variable waits, wide timeout scheduling and selected immediate
kthread workers. Callback traversal preserves priority/exclusive/key semantics,
self-removal/free and lifetime synchronization. Native raw callbacks notify
sleepable CV owners through MPSAFE softints without a raw-to-sleep lock edge.

Task allocation reserves admission before memory/TLS access. Module finalization
atomically closes admission only with zero task owners and returns EBUSY before
any destructive teardown when busy. Generic driver/workqueue entry attachment,
external callback/code-owner rundown and actual unload execution remain OPEN.

All 33 source/C scripts pass on HP, including actual integrated source bodies,
10000 modeled wake/schedule races, 500 allocation/quiesce races and 13 worker
tests. Fresh real native task/wait/variable/worker/module objects compile with
-Werror; the four runtime objects link with no unresolved shared Linux symbols.
These checks do not execute the NetBSD scheduler or establish full kernel links.

Native completion explicitly includes its real wait dependency. Linux arithmetic
includes its required const.h directly; the unused UAPI sysinfo umbrella caused
a retained earlier module failure. Full sysinfo/UVM porting remains OPEN.

See [integrated runtime evidence](evidence/HP_NATIVE_TASK_WAIT_WORKER_20261006.json).
Fatal-only waits, UUID/GUID, PWM, full OS/ABI/lifecycle and physical KMS remain
required. No installation or reboot; boot/running/recovery hashes are unchanged.

## Earlier checkpoint

### HP i915 checkpoint, 2026-10-06

STATE: IN_PROGRESS. Full port acceptance remains OPEN. Build and installation: HP only.

## Typed objects and saturated allocation sizes

Patch 0031 supplies the exact pinned optional-GFP and four kmalloc/kzalloc
object/array macro bodies above the native allocation backend. Three complete
pinned size_mul/size_add/size_sub bodies preserve saturation at SIZE_MAX,
including the sentinel rules for subtraction. Existing native allocator and
pool/cache ownership remain explicit; this is not full slab/VM/GFP closure.

Native kmalloc and krealloc reject private-allocation-header overflow with
NULL before any backend allocation or old-memory free. The old kmalloc
assertion no longer panics on a saturated typed allocation size, and krealloc
cannot wrap the size and overwrite a tiny new allocation with old bytes.
An overflow or allocation failure preserves the old allocation and its data.

All 32 source/C scripts pass. The whole production slab and overflow headers
execute under an explicit allocation/free ledger, covering 20,000 independent
wide size oracles, return types, optional GFP, one evaluation, zero fill,
multiplication/header overflow and failed realloc ownership. Pool/RCU/VM
parsing models are not executed or claimed as OS implementations. An initial
missing kernel bit-mask macro in the model was recorded and corrected there.

The real native kernel header object and freshly compiled modern buddy object
pass. Fresh DVO compilation no longer reports the typed kzalloc_obj dependency;
actual wait/task, completion/GUID include and PWM failures remain OPEN.

See [native typed allocation evidence](evidence/HP_NATIVE_TYPED_ALLOC_20261006.json).
The full 323 i915/410 modern C graph, native OS/ABI/lifecycle/kernel link and
physical KMS acceptance remain required. No installation or reboot occurred;
boot/running/recovery hashes remain unchanged.

## Earlier checkpoint

### HP i915 checkpoint, 2026-10-06

STATE: IN_PROGRESS. Full port acceptance remains OPEN. Build and installation: HP only.

## Pinned container and assertion contracts

Patch 0030 binds the complete pinned container/type-check and optional-message
static assertion macros through private Linux names. Native container and
CTASSERT wrappers retain their previous definitions. Linux-owned source and
API inputs are verified against the frozen reference and preceding translation
ledger before expansion to the 78-name private namespace.

The first actual kernel header compile caught GNU void-pointer arithmetic and
const-removal warnings in the Linux container expression. The adapter uses
native char-pointer byte arithmetic and __UNCONST, preserving strict member
checks, the intentional non-const container result and the const-selecting
_Generic interface. No compiler warning is disabled. The original generated
patch and failed native proof are retained. An initial userspace-only assert.h
macro conflict was also recorded and corrected in the explicit test include
model; native adapter macros were not changed to accommodate that model.

All 31 source/C scripts pass. Tests execute const and void pointer cases,
nonzero offsets, one evaluation and four compile-failure controls for member
types and assertions. The real native kernel header object and freshly compiled
modern buddy object pass. Fresh DVO compilation no longer reports missing
container_of_const; actual wait/task, completion/GUID include, PWM and typed
allocation dependencies remain open. Its vblank-work field is kthread_work,
not irq_work. All compiler execution occurred on HP.

See [native container evidence](evidence/HP_NATIVE_CONTAINER_20261006.json).
The full 323 i915/410 modern C graph, complete native OS/ABI/lifecycle/kernel
link and physical KMS acceptance remain required. No installation or reboot
occurred; boot/running/recovery hashes remain unchanged.

## Earlier checkpoint

### HP i915 checkpoint, 2026-10-06

STATE: IN_PROGRESS. Full port acceptance remains OPEN. Build and installation: HP only.

## Private typechecks and word-part interfaces

Patch 0029 provides the complete pinned typecheck and word-part macro bodies
through private Linux names. Native adapter macros keep their original names.
The byte-mask predicate uses the actual NetBSD endian definition. All selected
Linux-owned source/API inputs are checked against the frozen originals before
any translation is applied; existing translation provenance is retained.

The source tokenizer now protects angle-bracket include paths, including
include_next and a continued include line. A real DVO compile exposed a
mistaken typecheck basename translation. The exact previous generated bytes
are verified through the retained version-1 tokenizer before repair; no blind
replacement or native adapter rewrite occurs. That failure remains recorded.

All 30 source/C scripts pass after the repair. New tests cover valid and
invalid type/pointer contracts, 64/32/16-bit parts, one evaluation, repeated
bytes and both explicit endian models. A fresh real NetBSD kernel header
object passes with strict warnings; the modern buddy object also recompiles
successfully. The fresh DVO compile confirms the previous typecheck and word
macro redefinition failures are gone, while real remaining API failures are
kept open. No whole-driver compile, link or physical acceptance is inferred.

See [native typecheck/word-part evidence](evidence/HP_NATIVE_TYPECHECK_WORDPART_20261006.json).
The complete 323 i915/410 modern C graph remains in scope. Native wait queues,
kthread worker/task scheduling, PWM, container/allocation/header/GUID and
actual folio/UVM adaptation still need implementation. No installation or
reboot occurred; boot/running/recovery hashes are unchanged.

## Earlier checkpoint

### HP i915 checkpoint, 2026-10-06

STATE: IN_PROGRESS. Full port acceptance remains OPEN. Build and installation: HP only.

## Completion counting and wide timeout budgets

Patch 0028 keeps NetBSD's real mutex and condition-variable backend while
correcting completion counter saturation, unsigned/long timeout ABI, remaining
timeout budgets across bounded native CV slices, clock wrap and completion
races against a signal or deadline. It adds the serialized completion_done API.

The complete production header passes the instrumented CV/mutex model on HP.
The unchanged native adapter fails the negative control. A separate fresh
object with actual NetBSD kernel headers and kernel -Werror options passes,
including timeout/counter type assertions. This proves native header and ABI
integration; actual scheduler concurrency, fatal-only signals, FIFO ordering,
IO accounting, static initializers and destruction/lifetime acceptance remain
open. Untimed interruptible races and the modern DRM transitive include remain
separate integration work.

All 29 source/C regression scripts pass. The factory applies the new patch and
the normal runner includes its regression. Prior native arithmetic/tree and
the single modern DRM buddy object proofs remain recorded in the earlier
checkpoint; this change does not establish whole-driver compilation.

See [native completion evidence](evidence/HP_NATIVE_COMPLETION_20261006.json).
The full 323 i915 and 410 selected modern-driver graph remains in scope.
Wait queues, remaining native types/headers/GUID and actual VM/folio/UVM
adaptation, kernel link and physical KMS acceptance are open. No installation
or reboot occurred. Boot, running-kernel and F77 recovery hashes are unchanged.

## Earlier checkpoint

### HP i915 checkpoint, 2026-10-06

STATE: IN_PROGRESS. Full port acceptance remains OPEN. Build and installation: HP only.

## Full-width arithmetic implementations

Patch 0027 replaces the incorrect native math64 signatures and truncating
remainders/quotients with the complete pinned math64 interface. The actual HP
compiler supplies 128-bit scalars; their pinned UAPI alignment and Kconfig
prerequisites are explicit. The native most-significant-bit adapter preserves
Linux's zero-based nonzero-word contract through NetBSD fls64.

Pinned generic division/multiply-add/divide, integer-square-root and integer
power implementation units are selected in the real native graph. All three
compile with actual NetBSD kernel headers and -Werror, and the header ABI probe
passes. They introduce no compiler 128-bit division-runtime dependencies.
Native tree and modern DRM buddy objects also pass. These are five added
native algorithm units plus one of the 410 selected modern driver units.

All 28 source/C regression scripts passed after the final changes. Arithmetic
oracles cover large 128-bit intermediate products, all valid shifts, signed and
unsigned quotient/remainder types, saturation, more than 20K random wide cases,
square roots and powers. A separate native executable produces SIGFPE for the
pinned zero-divisor contract. Scalar/model tests remain distinct from actual
kernel objects and physical driver acceptance. Earlier header and missing-bit
primitive failures are preserved alongside the final native proofs.

See [native evidence](evidence/HP_NATIVE_MATH64_20261006.json). Every selected
i915/DRM/display/TTM unit and full OS/API/lifecycle/runtime requirement remains
in scope. Completion/wait-queue, remaining native header/type/GUID and actual
VM/folio/UVM adaptation are still open. No full kernel link, installation,
reboot or physical KMS acceptance occurred; F77 and recovery hashes are unchanged.

## Earlier checkpoint

### HP i915 checkpoint, 2026-10-06

STATE: IN_PROGRESS. Full port acceptance remains OPEN. Build and installation: HP only.

## Compiler attributes and integer math

Patch 0026 binds the pinned Linux compiler attributes and math macros to
private names, leaving native compiler/OS macro semantics intact. The source
integration verifies every selected Linux seed and imported API input before
translation. Comments, strings and compiler attribute properties remain intact.
There are 63 private bindings: 258 selected inputs and 126 API headers changed.
The importer and fresh-stage factory now reproduce these bindings.

The real frozen native do_div helper truncated a 64-bit quotient to 32 bits.
A 2^48 / 3 baseline executable failed. The corrected helper retains the full
quotient, remainder and single evaluation for both native uint64_t and Linux
long-long u64, and compiles in the actual kernel context. Attribute format and
unused-result negative controls and more than 64K arithmetic cases passed.

All 27 source/C scripts passed on HP. Both native tree objects and the modern
DRM buddy unit were freshly compiled with the changed headers. The old attribute
and rounding redefinition failures disappeared. Representative DVO compilation
now exposes the next typecheck/wordpart, wait-queue/completion, GUID and math64
ABI gaps. i915/TTM VM/folio dependencies remain unresolved. Earlier fixture and
command-extraction failures remain preserved; they are not successful tests.

See [native evidence](evidence/HP_NATIVE_COMPILER_MATH_20261006.json).
All 323 i915 and 410 selected modern Linux units remain in scope. No full kernel
link, installation, reboot or physical KMS acceptance occurred. F77 and recovery
hashes were rechecked unchanged. One modern object is not whole-driver parity.

## Earlier checkpoint

### HP i915 checkpoint, 2026-10-06

STATE: IN_PROGRESS. Full port acceptance remains OPEN. Build and installation: HP only.

## Word size, raw locks and shared configuration

Owned patches 0023..0025 establish the native physical word width, real
NetBSD non-sleeping raw locks with saved interrupt priority, and the pinned
x86 instruction-location implementation. Failed raw try-lock attempts restore
the caller's priority; lock/flag expressions are evaluated once. Kernel panic
concurrency, lock destruction and caller lifetime still need full integration.

The graph factory now shares the complete selected Kconfig profile across
DRM, display, TTM and native Linux helpers. Disabled Linux boolean symbols are
absent rather than defined as zero, preserving actual #ifdef semantics.

All 26 source/C regression scripts passed on HP. The raw-lock header also
compiled with actual NetBSD kernel headers, -nostdinc and -Werror. Both native
tree implementation objects passed again with the updated shared flags.
The unchanged pinned modern Linux drm_buddy.c is the first of the 410 selected
modern Linux units to compile as a native NetBSD kernel object.

This is bounded compiler evidence. Representative dvo_ch7017 still fails at
Linux/native compiler-attribute and math collisions. i915_driver and ttm_device
still reach Linux page-layout/folio dependencies requiring real UVM adaptation.
These failures are retained. No fabricated generated/bounds.h, full kernel
link, installation, reboot or physical KMS acceptance occurred. The complete
323-unit i915 scope, remaining DRM/TTM interfaces and every platform/runtime
gate remain OPEN. F77 and recovery hashes were rechecked unchanged.

See [native evidence](evidence/HP_NATIVE_WORDSIZE_RAW_LOCKS_20261006.json).

## Earlier checkpoint

### HP i915 checkpoint, 2026-10-05

STATE: IN_PROGRESS. Full port acceptance is OPEN. Build and installation: HP only.

## Current native graph and adapter work

The actual configured NetBSD graph selects all 323 pinned i915 C units,
66 selected DRM units, eight display helper units and 13 TTM units: 410 Linux
units. The previous 11 backport objects remain separate evidence; they do
not cover the full modern Linux driver. Native module and PCI additions use
distinct names so config(5) cannot silently replace selected Linux units.

The source-owned full graph factory, include importer and native probe tool
preserve old references, worktrees and outputs. Exact pinned missing headers
are imported transitively; existing native headers remain explicitly
UNREVIEWED. The input snapshot contains 550 imported headers, 359 existing
adapter rows and 13 unresolved inputs. These are source inputs, not closure.

Owned native patches 0018..0022 provide:
- Correct release-store temporary, real acquire-load ordering and overflow-free ktime_compare.
- Frozen Linux tristate predicates using native build flags, with native endian ownership.
- Linux POSIX UAPI types and exact long-long fixed64 type/format contracts.
- Pinned Linux balancing and interval augmentation over native rb_node storage,
  independent Linux roots, cached nodes, RCU publication and overlap/span iteration.
- Namespaced Linux color/root constants, preserving native sys/tree.h and rb_tree.

All 22 source/C regression scripts passed on HP, including the genuine
six-edit overlay and exact combined-source equivalence. After the last
qualifier and fixed64 changes, the two changed production fixtures passed
again. Nineteen scalar type/format checks and the amd64 drm_version layout
passed in the actual Linux kernel header context. Tree tests validate 127
overlapping/extreme intervals, balancing, augmentation, deletion, cached/RCU
replacement, postorder and spans; the native OS tree is exercised separately.

Both new tree implementation objects compile with real NetBSD kernel headers,
-nostdinc and -Werror on HP. The tree algorithm is not replaced by native
callbacks that cannot maintain Linux augmentation. Nodes must belong to
one backend at a time; native and Linux color encodings differ.

The first complete 410-unit probe failed all units at shared input gaps.
A later redundant probe was stopped after 147 failures sharing vdso/const.h;
the source importer then resolved that input. Later real C compilation
reached additional OS/API incompatibilities. Representative DRM/i915 objects
still fail: word-size macro ownership, raw locks, lockdep, compiler attributes,
and Linux VM/folio page layout are open. No fabricated generated/bounds.h or
single-page folio alias is used. Required Kconfig/dependency and DRM header
ABI reconciliation remain open as well.

See [current evidence](evidence/HP_FULL_GRAPH_API_20261005.json). Original
failure logs and the earlier backport evidence remain preserved. No full
kernel link, installation, reboot or physical KMS acceptance occurred.
F77 and recovery hashes were rechecked unchanged. This checkpoint is a
source delivery in the ongoing full port, not completion or installation
eligibility.

## Earlier checkpoint

### HP i915 checkpoint, 2026-10-05

STATE: IN_PROGRESS. Build and installation host: HP only.
The full 323 active Linux units plus DRM/TTM/OS-adapter contract is unchanged.

Starting canonical driver revision: 64a7d044552f59ef0abc260e0828a37902e2672f.
References: Linux fd179f8a05be3ccae366b9b96e176b51fbe54aab and NetBSD
03d918f6d0e81fa05b8f1160eca0628ad39988a6. Current source/tests were materialized
on HP separately from `/usr/src` and existing import worktrees.

All 18 project Python/C regression scripts passed on HP NetBSD 11 against
both the frozen reference and the genuine six-edit overlay. The runner
verified all 24 eDP patch orders on frozen source, six orders on the overlay,
and exact combined complete-file equivalence. The six concatenated combined
source files have SHA256
`13cb25441ce3768181bc33983c38752bbbc5100510dbd3b32f5a7299b56b7c53`.
See [the source/C regression evidence](evidence/HP_PINNED_REGRESSIONS_20261005.json).
These are mocked C/source tests, separate from hardware acceptance.

Same-step repairs preserve the acceptance gates:

- Registration rollback anchors search after their predecessor, avoiding the
  earlier success-path RPM assertion call. Reversed cleanup is rejected.
- Candidates 0008 and 0011 now byte-match their canonical generators. Original
  and regenerated patches produce identical complete target source bytes;
  only diff context/blank-line classification differed.
- The MSA fixture includes the patch's trailing separator blank line.
- The AUX IRQ fallback generator's invalid parenthesis is repaired.
- ASan/UBSan executables use NetBSD's ELF PaX flag on resolved disposable
  temporary binaries only. No global security policy is changed.
- Negative controls require SIGABRT and the specific violated expression,
  including NetBSD's lowercase assertion format.
- The DPCD C11 test includes stdbool.h explicitly for `true`.
- Audio tests accept an explicit, clean pinned NetBSD reference instead of
  a Legion-only path. Audio and terminal PPGTT ownership tests are included
  in the shared runner; all 18 scripts now execute there.
- Source staging rejects existing outputs, unknown Git identity, incomplete
  sparse paths, dirty Git blobs and copied-byte mismatches before claiming
  a complete manifest. Six disposable Git-fixture tests pass; five failed
  with the original tool, including its deletion of an existing output.

The initial frozen-and-overlay job stopped at the missing stdbool.h include.
The connection outage prevented its result being read. After the user's
continuation, the live HP SSH route recovered, that durable failure was read,
the evidenced test defect was repaired, and the complete final suite passed.
Read `i915-all18.status` (EXIT 0) and `i915-all18.log` in the task workspace.
No infrastructure failure was counted as a pass.

All eleven affected native NetBSD C objects subsequently compiled with the
actual frozen kernel headers and HP's GCC 12.5.0 tools, with `_KERNEL`,
`-nostdinc` and warnings as errors. This bounded stack consists of the genuine
six-edit overlay plus 0005/0006/0007..0013/0016/0017; 0014 and 0015 are already
present in the overlay. The isolated build stage holds twelve changed files,
including the shared register header. Object hashes, patch hashes, source
hashes and actual make commands are recorded in
[the native object evidence](evidence/HP_BACKPORT_OBJECTS_20261005.json).
The existing tools, original references, user overlay and `/usr/src` remain
separate from the writable stage.

Actual commands on HP:

```sh
python3 -B tools/run_pinned_i915_source_checks.py \
  --netbsd-tree /root/netbsd-src-ref \
  --linux-tree /root/linux-rtl8723be-ref-fresh \
  --overlay-tree /root/hp-driver-port-20261005/netbsd-six-overlay-verified
python3 -B tools/build_hp_backport_objects.py \
  --netbsd-tree /root/hp-driver-port-20261005/netbsd-native \
  --objdir /root/hp-driver-port-20261005/native-obj \
  --overlay-tree /root/hp-driver-port-20261005/netbsd-six-overlay-verified
```

The genuine six-file Legion overlay's binary Git diff SHA256 is
`2623b640b713b01b1aa83383f9bf4a318abdd8d76963a3478f39dcc0cadca5bb`.
Its HP copy is byte-identical. Original Legion files and HP's older 497-file
whole-driver import were preserved. A local clone of the partial frozen
reference failed because upload-pack could not obtain a promisor object with
lazy fetching disabled; the separately materialized detached sparse worktree
succeeded. Do not repeat that failed partial-clone command.

Source publication uses verified HP commits and BMAX's ordinary Git route;
HP's HTTPS push has no credentials. Commit messages skip hosted CI to honor
HP-only builds. This checkpoint does not reactivate the quarantined workflow.

The frozen Linux sparse checkout was expanded for DRM/display/TTM and all
selected headers/top-level DRM files. The existing pin and clean tracked
state were retained. The first import had stopped after a missing sparse
directory; its partial output was preserved. After complete preflight, a
new output at `full-scope-audit/linux-stage-verified` contains 1,266 files,
including 915 i915 files. Every selected input and copied output was checked
against the exact Git blob before the manifest was written. See
[the complete source manifest](evidence/HP_I915_REFERENCE_MANIFEST_20261005.json)
and [the active build profile](evidence/HP_I915_ACTIVE_PROFILE_20261005.json).

The actual pinned Linux Makefile again selects 323 active C units. Against
the isolated NetBSD backport stage, [the structural matrix](evidence/HP_I915_STRUCTURAL_20261005.json)
finds 136 exact active paths, 13 overrides/moved units, seven present but
unbuilt units and 167 without a basename counterpart. **All semantic rows
remain UNREVIEWED**: even identical names do not establish matching Linux
semantics. External kernel APIs, reachable/generated dependencies and full
native integration are not closed by this lexical/build-file inventory.

No kernel link, installation, reboot or physical KMS acceptance is claimed.
The F77 boot selection, `/boot.cfg`, `/netbsd` and F77 kernel hashes were
rechecked unchanged after the object builds. i915 remains disabled there.

NEXT: continue semantic/dependency classification and implementation of all
323 active Linux units and required DRM/TTM/NetBSD adapters; link the complete
experimental graph, test ownership/PM/reset, and establish HP display/runtime
acceptance before installation eligibility. Eleven backport objects do not
close the complete Linux-driver contract.

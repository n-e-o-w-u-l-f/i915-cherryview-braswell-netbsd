# Native character-inode lifetime owner

This component is one dependency of the full modern Linux i915/DRM port to
HP TPN-W121 NetBSD 11. It does not complete the file bridge or change the
running kernel. The canonical modern `drm_cdevsw.c` and its replay hash remain
unchanged. No missing bridge header is replaced with a placeholder.

## Locked parent coverage

| Required port area | This change / remaining acceptance |
|---|---|
| PCI selection, resources, MMIO and firmware | Existing source work; physical modern attach remains open |
| GEM/GTT/PPGTT, DMA, TTM, requests and reset | Full selected modern ownership, error unwind and hardware acceptance open |
| IRQ, work, task identity and concurrent teardown | Full adapter context/lifetime closure open |
| File and inode lifetime | Native character-inode allocation/reference owner added; Linux file open/release, FD ownership, final-close task context and mapping references open |
| Poll, event and kqueue registration | Event-reader tests exist; real modern waitqueue-to-native registration, callback lifetime and drain remain open |
| Native ioctl dispatch | Pinned `sys/file.h` lacks `fo_ioctl_user` and `fo_linux_file`; corresponding callers and actual DRM dispatch provider remain open |
| MM/UVM/GEM mapping | Real backing object, pager/fault/detach, rights and lifetime remain open |
| Display, panel, hotplug and framebuffer handoff | Native KMS/console and physical verification open |
| PM, recovery and detach | Full reference-derived state machine and physical acceptance open |
| Source/build identity | Exact410 source admission exists; actual selected410 owners, ABI and complete modern kernel link open |
| Delivery and physical tests | No installation or experimental boot; independent early trace and exercised F77/stock fallback required |
| RTL8723BE parent | DMA/IRQ/queue teardown, scan/RX, association, WPA2/data, PM and recovery remain open; this component does not change RTL |

## Implemented contract

`compat/native-drm-inode/native_drm_inode.h` intentionally exposes an opaque
native object. It is a synthetic character-device identity, with immutable
device number, inode number and mode. It is not a Linux VFS inode, vnode,
address space or mapping. Creation returns a **native errno** and an output
pointer; this is not silently substituted for the canonical adapter's
`linux_inode_alloc` / `ERR_PTR` contract.

Creation establishes one reference, rejects non-character modes and uses
the native `kmem_zalloc(..., KM_NOSLEEP)` failure contract. The caller owns
publication. `tryget` uses the native CAS operation, refuses zero and
`UINT_MAX`, and requires an already owned reference or independent lifetime
protection. It cannot rescue an unprotected or freed pointer. Each `put`
publishes prior accesses before decrementing; final put acquires before
freeing exactly the original allocation size. Underflow is fatal even when
diagnostic assertions are disabled. Creation/final free are sleepable native
allocator operations; no driver or Linux release callback is invoked.

The ordering follows the pinned NetBSD DRM `kref` implementation's
release-before-decrement/acquire-before-final-free pattern. The native
reference for allocation is the pinned `sys/kmem.h`; atomic operations come
from the pinned `sys/atomic.h`. This does not establish a future file release
context: the native close path cannot rely on a fallible new task allocation
after a descriptor has already closed.

## Verification boundaries

`tools/check_hp_native_drm_inode.py` permits non-root execution only on the
HP NetBSD 11 amd64. It takes explicit clean pinned source, existing configured
kernel-object and new output directories. Real kernel flags are read from
the existing private configured Makefile. Source includes are relocated to
the clean pinned tree; generated kernel headers remain independently hashed.
Machine headers reached through configured symlinks must be byte-identical
to the corresponding pinned source. The compiler's dependency file records
the actual header closure. `-D_KERNEL`, `-nostdinc` and `-Werror` are required;
the model macro/header is forbidden in this compilation.

The separately compiled userspace C fixture includes the production function
bodies with an explicitly identified allocator/atomic model. It exercises
lifetime and concurrent retain/drop contracts, not kernel allocator behavior,
kernel concurrency or hardware. The real kernel object is never loaded.
Existing native symbols are checked against the retained prior kernel; this
is a provider inventory, not a new kernel link.

## HP result (2026-10-23 12:02 UTC)

[Native receipt](evidence/HP_NATIVE_INODE_OWNER_20261023.json): PASS on the
physical HP NetBSD 11.0 amd64 as uid1004. Production C compiled with the
configured native kernel flags, including `_KERNEL`, `-nostdinc`, and
`-Werror`. All 116 consumed headers were hashed and their source/configured
ownership checked. No model header entered this compilation. The resulting
14,504-byte object has SHA256
`458aa2195e582fc905177b6eceee01808cd159d0e4f516703112427e32a7eb35`.
Its six undefined native dependency symbols all have providers in the retained
prior native kernel; no new link was performed.

The separately compiled C11/UBSan userspace model passes nine named cases,
including actual pthread retain/drop loops with two and four workers
(8,192 and 16,384 successful retains respectively). Five semantic mutants
are rejected by SIGABRT, the exact completed-case prefix and expected
assertion: zero resurrection, reference overflow, omitted final free,
premature free and wrong free size. The explicit allocator model records
logical free and quarantines storage until reset. These results do not
establish kernel allocator, interrupt, weak-memory or physical behavior.

The tested pre-publication tree is
`34135a5d65c743d1dc53c1d3e0e7443082f2f5f1` based on `edb59bc`.
The receipt binds all five production/header/fixture/runner files by SHA256;
only this report and the evidence are added after execution. The staged HP
test checkout and artifacts are retained separately under
`/home/megal/hp-driver-source-stage-20261023/{i915-native-inode-a01,inode-owner-a01}`.

F77 remained the booted kernel. The earlier private diagnostic kernel retained
SHA256 `1aabcdee27654413382a1497e52e27b4ae4f4cd031ba478a47a233198fe4fbb4`.
No full modern adapter compile, new kernel link, installation or boot occurred.

Next integration must deliberately implement the missing Linux inode/file
contract, including a held inode reference on successful file allocation,
ERR_PTR/native-error conversion, open-success-dependent release, guaranteed
final-close task context and delayed release for mapping/import references.
Do not rename this opaque native object into a purported complete Linux inode.


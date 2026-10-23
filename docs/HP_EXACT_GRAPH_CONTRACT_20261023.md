# Exact frozen 410-unit graph admission — 2026-10-23

Base: `20e245d1ef866625fd0f2eb598f9851f6ab6a904`.
Tested code tree: `22ddc304e5b8f51e08f307b6f217b90ae9f90096`.

The preserved unpublished graph work identified a missing gate in the current
full-graph preparer and probe. They previously checked only the i915323 count,
object-name uniqueness and source text presence. A same-size wrong dependency
set could pass. Importing the older complete patch would overwrite newer
native adapter replay and symbol-owner auditing protections.

## Change

Added the pure `tools/hp_graph_contract.py` contract and wired it into the real
prepare/probe entrypoints. It admits exactly323 i915,66 DRM,8 display and13 TTM
sources against the reviewed frozen source sets. It rejects wrong/missing
groups, invalid types, duplicates, unsafe/non-C paths and object basename
collisions. Both stage and evidence must bind Linux
`fd179f8a05be3ccae366b9b96e176b51fbe54aab` and NetBSD
`03d918f6d0e81fa05b8f1160eca0628ad39988a6`.

The reference evidence is additionally bound to reviewed canonical-LF SHA256
`79cc1e9bd6ceee1efbc289b091eb98706df4c496b31408925cbe1f3085db6c3b`.
Changing both the evidence source list and candidate list cannot silently
redefine the accepted graph. Only CRLF-to-LF normalization is permitted.
Admission returns deterministic source/object rows without mutating input.

Prepare performs source enumeration and existing source-hash checks first,
then exact admission before stage creation. Its enumeration can query gmake;
the new contract itself invokes no subprocess. Probe admits stored state and
pins before reading the native Makefile or creating output/dispatching a
compiler. The retained Makefile presence check is explicitly a weaker check,
not actual configured ownership. Both touched native tools now require exact
HP hostname and NetBSD major11. Existing retired-root restrictions remain;
neither tool was run against historical host staging paths in these tests.

## Actual validation

All validation ran via authenticated direct SSH on HP `megal`, NetBSD11.0
amd64, F77. Fresh checkout and evidence live beneath
`/home/megal/hp-driver-source-stage-20261023/`, separately as
`i915-graph-contract-a01` and `graph-contract-a01`.

- 23 graph contract/entrypoint test methods PASS, including same-count wrong
  sets in each group, malformed/tampered reference, pin/path/collision failures,
  reordered valid input and CRLF compatibility.
- Entrypoint controls execute real main functions with in-memory host paths
  and mocked selection enumeration. Invalid admission stops before staging or
  further native tooling; valid controls reach exactly the next simulated
  stage-creation/Makefile-read boundary. No historical native paths are read.
- Existing argv replay and bridge-header/partial-link command source checks
  PASS;4 DRM error-path contracts PASS; event fixture source assembly PASS.
- All four changed code/test Git blobs match native receipt SHA256 values.
  Existing C reader/fixture hashes match20e245d; no repeat C compilation was
  needed for this graph-only source change.

[Native source-test receipt](evidence/HP_EXACT_GRAPH_CONTRACT_20261023.json).

## Remaining native work

This is exact frozen source admission, not proof of configured410 ownership,
native ABI compilation, final linkage or Linux semantic parity. The current
retained private GENERIC configuration independently reports expanded3290
ALLFILES/OBJS, while its OBJS.i915drmkms/drmkms/drmkms_ttm are empty. A future
selection gate must use the actual native variable form, not assume an older
synthetic Makefile parser is valid.

Fresh modern DRM adapter staging still needs owned file/memory/DRM bridge
headers and runtime implementations absent from this repository. The existing
preparer also does not install the canonical modern drm_cdevsw source and its
nested tools retain retired-root assumptions. These are prerequisites to
repair/recover under a separate PRE; no placeholder header, owner substitution
or bypass of replay's source/header checks is acceptable.

The retained full diagnostic kernel is still the earlier8a/RTLa06 native
GENERIC milestone. It was not rebuilt or modified here. F77, installed kernels,
EFI, boot.cfg, radio and old source trees remain unchanged. Modern410 native
ownership/ABI/link, physical KMS/WPA2/PM and early-console/exercised F77-stock
recovery remain OPEN. No experimental boot was performed.

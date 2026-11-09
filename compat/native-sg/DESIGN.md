# Modern SG and Native DMA ownership: reviewed boundary

No SG provider is implemented by this design record. A declaration, alias or
DMA-address arithmetic cannot close the physical ownership and device teardown
dependencies below. Existing folio/UIO providers remain independently usable.

## Observed source contracts

NetBSD03 `linux/scatterlist.h` owns one legacy `sgl[1]` containing a physical page
array, Native DMA tag and map. It has no sg_set_page, modern page_link,
per-entry length/offset, or independently iterable DMA segment chain. The actual
implementation was located by pinned Gitgrep in `linux/linux_sgt.c`.

The subsequently captured genuine `drm/bus_dma_hacks.h` supplies
bus_dmamap_load_pages. It deliberately converts actual Native vm_page physical
addresses using its per-architecture PHYS_TO_BUS_MEM input encoding and invokes
the real public bus_dmamap_load_raw override path. This is a legitimate existing
Native RAM provider, rather than a modern DMA-output-to-physical inference. The
x86 raw backend rejects mappings past its bounce threshold and does not construct
a bounce buffer. A modern adapter may use this actual provider when its input
coverage, direction, offset and failure contracts fit; its returned DMA segments
must still remain independent from CPU physical/page identity. The UIO route
below is needed if actual bounce transfer support is required.

The modern selected i915 shmem code builds entries with sg_set_folio, later
extends `sg->length` across physically contiguous folios, advances sg_next,
marks its actual last entry and trims the table. The source-owned folio is an
actual Native base-page handle. No Linux binary folio overlay exists.

NetBSD03 `x86/bus_dma.c` provides these materially different paths:

* load_raw is documented for memory from bus_dmamem_alloc; its generic backend
  does not implement bounce handling. Ordinary physical RAM must not be
  relabelled as such an allocated bus segment.
* load_uio resolves kernel virtual buffers through the Native pmap and invokes
  the actual DMA-tag override chain. Its bounce cookie retains the original UIO
  pointer through sync/unload. Both UIO and its iovec array must remain owned.
* PREWRITE/PREREAD and POSTWRITE/POSTREAD are distinct phases. Native rejects a
  sync combining PRE and POST. SKIP_CPU_SYNC cannot simply discard bounce data
  movement or be treated as an always-valid no-op.
* Native DMA output addresses/lengths are `map->dm_segs` after load, including
  translation/bounce effects. They are not CPU physical page identities.

Native device_acquire pins device lifetime, but requires caller exclusion from
an already returning detach routine. The actual detach path must close admission
and drain active SG maps before releasing DMA-tag/resource ownership. The real
bus_dmatag_subregion API can acquire a Native subtag reference, released with
bus_dmatag_destroy; this must run through its actual override contract.

Native x86 bus_space_mmap returns an encoded page number and mmap flag bits,
not a byte physical address. No resource producer may feed that return value
directly into pmap or use translated DMA+iobase as a substitute physical address.

## Required source owners

Use unique `struct linux_scatterlist` and `struct linux_sg_table` names, admitted
only through digest-qualified Linux source/header transformations. Keep the
original Native structures and API intact. The source adapter needs independent
entry storage/chain bounds, original entry count, mapped DMA entry count,
physical/page or resource identity, and active Native map ownership.

A RAM physical owner holds a strong reference to every actual Native page in
the covered span. Construction validates all pages before publication, uses
VM_PAGE_TO_PHYS for each actual page and records real continuity. A later direct
source `sg->length` extension must still fit that retained, validated range;
pointer arithmetic on a presumed array of Linux/Native page structures is not
an ownership proof. Ordinary unmanaged TTM allocations need their real owner;
UAO sidecar coverage must not be generalized by assertion.

A resource physical owner requires a real attach-time Native bus resource,
bounded offset/length, device/resource hold, and reviewed CPU-physical translation.
It remains distinct from DMA mapping. A source which writes only dma_address
remains unqualified for CPU mmap and must return EOPNOTSUPP.

The agreed MM helper interface is:

`int linux_sg_mmap_page(const struct linux_scatterlist *, size_t segment_byte_offset, resource_size_t iobase, paddr_t *out)`.

It returns zero or a Linux negative errno. RAM requires iobase==-1, a retained
physical owner, page alignment and a complete page within the segment. A resource
requires its separately stamped physical identity, exact reviewed iobase contract
and bounds. It never infers physical memory from dma_address. The caller must
retain that physical owner through PTE removal/final VMA release; a temporary
helper lookup or a UAO/file reference alone does not prove a page stays wired.

An explicit Native DMA owner is created only from an actual attach-time device
and DMA tag. It holds the real subtag/device owner, limits/attributes, admission
and active maps. Device/PCI lookup is a separate registry/binding integration;
unbound calls fail rather than inventing a Native tag or returning mapped success.

For RAM, an implementation may build persistent kernel-space UIO vectors from
verified Native direct-map addresses under __HAVE_DIRECT_MAP and actual direct-map
bounds. A fallback needs a real owned Native KVA mapping. The actual public
bus_dmamap_load_uio path performs translation/bounce; no generic load_raw physical
shortcut is admitted. Mapping retains physical owners, UIO, iovecs, tag and map
until actual post-sync/unload/destroy. Output segments occupy separate fields.
If Native output cannot fit the source adapter's proven capacity, unwind and
return EFBIG before exposing any mapped entries.

## Validation before graph admission

Inventory all actual exact410 SG/DMA identifiers and direct field accesses, then
implement the reached helper/iterator/storage contracts rather than matching a
handpicked compile probe. Pin all Native source dependencies and actual compiler
configuration in the receipt.

Source-bound C controls must include multi-page continuity, empty/last/chained
entry bounds, direct source length extension, allocation failure at each owner
step, retained-page balance, Native create/load failure, output-count mismatch,
nonidentity DMA translations, bounce storage lifetime, exact PRE/POST phase order,
unsupported attributes, unbound device/tag, detach with live maps, and resource
DMA-only rejection. A VMA-held physical owner must survive table/DMA release
until actual PTE removal. Runtime/physical acceptance requires those real Native
paths; a model or source count is insufficient.

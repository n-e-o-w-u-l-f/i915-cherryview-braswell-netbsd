# Native folio batch source ownership

The exact selected modern source consumes batches of strong folio references.
The adapter stores real `struct linux_folio *` handles from the separately owned
UAO/page sidecar. Adding transfers the caller's existing reference; it does not
take an extra reference. The fixed 31-entry capacity and remaining-space return
match the pinned source interface. Full/invalid batches fail before a write.
Cursor iteration preserves reference ownership until release or explicit transfer.

`check_move_unevictable_folios` calls the real FILE page owner's
`linux_page_validate_wired` for every handle. That API checks a live sidecar and
real native UAO/page wire under the owner/object/page locks. There is no invented
Linux LRU state. Native wired pages stay outside pageable queues; the real last
`uvm_pageunwire` activates the page (`uvm_page.c:1785`). The Native sidecar owns
that deferred transition. Checking a batch does not prematurely unwire GPU pages.

Release validates all entries before consuming any, resets the batch, clears
each pointer and calls the real folio_put once. It never accesses a released
folio again, because a final put may immediately schedule Native destruction.
Another owner keeps its wire and page alive. There is no binary folio/pagevec
overlay, fabricated per-CPU LRU drain or exceptional xarray-entry provider.

The actual03 Native scatterlist interface has no sg_set_page and no modern
per-entry length/offset/page_link fields. A modern sg_set_folio wrapper cannot
be implemented by layout guessing. This package deliberately supplies no fake
scatter/gather or DMA owner. The real SG bridge remains a separate OPEN provider.
The exact410 inventory contains actual modern SG-chain users, so this boundary
cannot be treated as closed by successful batch compilation.

`run_native_model.py` executes only on unprivileged HP NetBSD11 in a fresh
output. It includes the actual adapter C and requires eight named ownership
cases and six separate diagnostic/SIGABRT controls. The model explicitly delegates
page references/wires and activation; it does not establish actual Native UAO
pagequeue locking, asynchronous retirement or GPU lifetime acceptance. Actual
Native ABI compilation with the real FILE page-owner header is a separate gate.

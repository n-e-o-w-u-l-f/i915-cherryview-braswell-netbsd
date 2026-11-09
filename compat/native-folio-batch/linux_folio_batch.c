/* SPDX-License-Identifier: BSD-2-Clause */
#ifdef NATIVE_FOLIO_BATCH_TEST
#include "test_model.h"
#else
#include <sys/param.h>
#include <sys/systm.h>
#include <linux/pagemap_netbsd.h>
#endif
#include <linux/folio_batch_netbsd.h>

void
check_move_unevictable_folios(struct folio_batch *batch)
{
    unsigned int count = folio_batch_count(batch), index;

    ASSERT_SLEEPABLE();
    for (index = 0; index < count; index++) {
        if (batch->folios[index] == NULL)
            panic("check_move_unevictable_folios: missing native owner");
        /* Each actual UAO base-page handle owns a native wire. UVM removes
         * wired pages from its pageable queues; actual uvm_pageunwire on the
         * owner's final release performs the Native activation transition.
         * Validate that ownership here; do not fabricate Linux LRU flags or
         * move a page while its native wire is still required by GPU users. */
        linux_page_validate_wired(folio_page(batch->folios[index], 0));
    }
}

void
__folio_batch_release(struct folio_batch *batch)
{
    unsigned int count = folio_batch_count(batch), index;
    struct linux_folio *folio;

    ASSERT_SLEEPABLE();
    /* Validate every entry before consuming any reference. GPU-error users
     * may call release directly without the check_move wrapper. */
    check_move_unevictable_folios(batch);
    batch->nr = batch->i = 0;
    for (index = 0; index < count; index++) {
        folio = batch->folios[index];
        batch->folios[index] = NULL;
        folio_put(folio);
        /* The last put may queue native destruction immediately. Never
         * dereference this folio after transferring its final ownership. */
    }
}

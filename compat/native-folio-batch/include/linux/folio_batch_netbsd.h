/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef _NB_LINUX_FOLIO_BATCH_H_
#define _NB_LINUX_FOLIO_BATCH_H_
#ifndef NATIVE_FOLIO_BATCH_TEST
#include <sys/types.h>
#include <sys/systm.h>
#endif
struct linux_folio;
#define FOLIO_BATCH_SIZE 31
/* Source-owned references, never a Linux binary folio or pagevec overlay. */
struct folio_batch {
    unsigned char nr;
    unsigned char i;
    struct linux_folio *folios[FOLIO_BATCH_SIZE];
};
static inline void folio_batch_init(struct folio_batch *batch)
{
    batch->nr = batch->i = 0;
}
static inline void folio_batch_reinit(struct folio_batch *batch)
{
    batch->nr = batch->i = 0;
}
static inline unsigned int folio_batch_count(const struct folio_batch *batch)
{
    if (batch->nr > FOLIO_BATCH_SIZE || batch->i > batch->nr)
        panic("folio_batch: invalid count/cursor");
    return batch->nr;
}
static inline unsigned int folio_batch_space(const struct folio_batch *batch)
{
    return FOLIO_BATCH_SIZE - folio_batch_count(batch);
}
static inline unsigned int folio_batch_add(struct folio_batch *batch, struct linux_folio *folio)
{
    if (folio == NULL || folio_batch_space(batch) == 0)
        panic("folio_batch_add: missing owner or full batch");
    /* Transfer the caller's existing strong reference; do not take a second
     * reference which __folio_batch_release would otherwise leak. */
    batch->folios[batch->nr++] = folio;
    return folio_batch_space(batch);
}
static inline struct linux_folio *folio_batch_next(struct folio_batch *batch)
{
    (void)folio_batch_count(batch);
    return batch->i == batch->nr ? NULL : batch->folios[batch->i++];
}
void check_move_unevictable_folios(struct folio_batch *);
void __folio_batch_release(struct folio_batch *);
static inline void folio_batch_release(struct folio_batch *batch)
{
    if (folio_batch_count(batch))
        __folio_batch_release(batch);
}
#endif

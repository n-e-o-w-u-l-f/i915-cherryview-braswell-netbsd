/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * Isolated native hashed variable callback queues, based on pinned Linux
 * kernel/sched/wait_bit.c. These are real generic callback queue heads and
 * exact-address keys, independent of the older native bit-wait CV table.
 * Selected variable-wait callback scope only; bit locking/IO/timeouts OPEN.
 */
#include <sys/param.h>
#include <sys/systm.h>
#include <linux/wait_bit.h>

#define VAR_WAIT_TABLE_BITS 8
static wait_queue_head_t var_wait_table[1U << VAR_WAIT_TABLE_BITS];
static bool var_wait_initialized;

/* Frozen Linux hash_ptr/hash_long distribution at the real native width. */
static unsigned int
var_wait_bucket(void *p)
{
    uintptr_t value = (uintptr_t)p;
    if (sizeof(value) == sizeof(uint64_t))
        return (unsigned int)(((uint64_t)value * 0x61C8864680B583EBULL) >>
            (64 - VAR_WAIT_TABLE_BITS));
    KASSERT(sizeof(value) == sizeof(uint32_t));
    return ((uint32_t)value * 0x61C88647U) >> (32 - VAR_WAIT_TABLE_BITS);
}

int
linux_wait_var_init(void)
{
    KASSERT(!var_wait_initialized);
    for (unsigned int i = 0; i < __arraycount(var_wait_table); i++)
        init_waitqueue_head(&var_wait_table[i]);
    var_wait_initialized = true;
    return 0;
}

void
linux_wait_var_fini(void)
{
    KASSERT(var_wait_initialized);
    /* Caller first rejects new owners and drains all variable callbacks. */
    for (unsigned int i = 0; i < __arraycount(var_wait_table); i++)
        destroy_waitqueue_head(&var_wait_table[i]);
    var_wait_initialized = false;
}

wait_queue_head_t *
__var_waitqueue(void *p)
{
    KASSERT(var_wait_initialized);
    return &var_wait_table[var_wait_bucket(p)];
}

struct wait_bit_key *
__var_wake_key(struct wait_queue_entry *entry, void *arg)
{
    struct wait_bit_queue_entry *wait;
    struct wait_bit_key *key = arg;

    wait = container_of(entry, struct wait_bit_queue_entry, wq_entry);
    if (wait->key.flags != key->flags || wait->key.bit_nr != key->bit_nr)
        return NULL;
    return key;
}

int
var_wake_function(struct wait_queue_entry *entry, unsigned int mode,
    int flags, void *key)
{
    if (!__var_wake_key(entry, key))
        return 0;
    return autoremove_wake_function(entry, mode, flags, key);
}

void
init_wait_var_entry(struct wait_bit_queue_entry *wait, void *var, int flags)
{
    *wait = (struct wait_bit_queue_entry) {
        .key = { .flags = var, .bit_nr = -1 },
        .wq_entry = {
            .flags = flags,
            .private = current,
            .func = var_wake_function,
            .entry = LIST_HEAD_INIT(wait->wq_entry.entry),
        },
    };
}

void
wake_up_var(void *var)
{
    struct wait_bit_key key = { .flags = var, .bit_nr = -1 };
    __wake_up(__var_waitqueue(var), TASK_NORMAL, 1, &key);
}

int
woken_wake_bit_function(struct wait_queue_entry *entry, unsigned int mode,
    int flags, void *arg)
{
    struct wait_bit_key *key = __var_wake_key(entry, arg);
    if (!key)
        return 0;
    smp_mb();
    entry->flags |= WQ_FLAG_WOKEN;
    return default_wake_function(entry, mode, flags, key);
}

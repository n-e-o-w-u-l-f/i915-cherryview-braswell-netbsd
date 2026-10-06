/* SPDX-License-Identifier: GPL-2.0 */
/* Selected keyed variable-callback subset from the frozen Linux wait-bit API.
 * The native legacy bit/lock/IO/timeout APIs remain separate OPEN gates. */
#ifndef _LINUX_WAIT_BIT_H_
#define _LINUX_WAIT_BIT_H_
#include <linux/wait.h>

struct wait_bit_key {
    unsigned long *flags;
    int bit_nr;
    unsigned long timeout;
};
struct wait_bit_queue_entry {
    struct wait_bit_key key;
    struct wait_queue_entry wq_entry;
};

#define __var_waitqueue linux___var_waitqueue
#define __var_wake_key linux___var_wake_key
#define init_wait_var_entry linux_init_wait_var_entry
#define var_wake_function linux_var_wake_function
#define wake_up_var linux_wake_up_var
#define woken_wake_bit_function linux_woken_wake_bit_function

int linux_wait_var_init(void);
void linux_wait_var_fini(void);
wait_queue_head_t *__var_waitqueue(void *);
struct wait_bit_key *__var_wake_key(struct wait_queue_entry *, void *);
void init_wait_var_entry(struct wait_bit_queue_entry *, void *, int);
int var_wake_function(struct wait_queue_entry *, unsigned int, int, void *);
void wake_up_var(void *);
int woken_wake_bit_function(struct wait_queue_entry *, unsigned int, int, void *);

/* Preserve the existing native ABI declarations rather than hiding them.
 * These legacy functions do not supply keyed variable callback queues. */
#define clear_and_wake_up_bit linux_clear_and_wake_up_bit
#define wait_on_bit linux_wait_on_bit
#define wait_on_bit_timeout linux_wait_on_bit_timeout
int linux_wait_bit_init(void);
void linux_wait_bit_fini(void);
void clear_and_wake_up_bit(int, volatile unsigned long *);
int wait_on_bit(const volatile unsigned long *, unsigned int, int);
int wait_on_bit_timeout(const volatile unsigned long *, unsigned int, int,
    unsigned long);

#endif

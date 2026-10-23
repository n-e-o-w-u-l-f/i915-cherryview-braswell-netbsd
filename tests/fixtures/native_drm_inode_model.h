/* Explicit userland lifecycle model; never a NetBSD kernel ABI replacement.
 * GCC atomics model the requested ordering and pthreads provide contention.
 * A logical kmem_free is recorded immediately; storage is quarantined until
 * reset so negative controls can fail deterministically without use-after-free.
 */
#ifndef NATIVE_DRM_INODE_MODEL_H
#define NATIVE_DRM_INODE_MODEL_H

#include <sys/types.h>
#include <sys/stat.h>
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static _Noreturn void
panic(const char *format, ...)
{
    va_list arguments;
    fputs("INODE_MODEL_PANIC ", stderr);
    va_start(arguments, format);
    vfprintf(stderr, format, arguments);
    va_end(arguments);
    fputc('\n', stderr);
    fflush(stderr);
    abort();
}

#define MODEL_CHECK(condition) do { \
    if (!(condition)) \
        panic("MODEL_CHECK %s at %s:%d", #condition, __FILE__, __LINE__); \
} while (0)
#define KASSERT(condition) MODEL_CHECK(condition)
#define KASSERTMSG(condition, ...) do { \
    if (!(condition)) panic(__VA_ARGS__); \
} while (0)
/* Userland workers are modelled as sleepable. This flag models admission,
 * not NetBSD IPL/LWP state or the kernel's actual sleepability assertion.
 */
static _Thread_local bool inode_model_atomic_context;
#define ASSERT_SLEEPABLE() MODEL_CHECK(!inode_model_atomic_context)

#define KM_SLEEP 1
#define KM_NOSLEEP 2

static pthread_mutex_t inode_model_allocator_lock = PTHREAD_MUTEX_INITIALIZER;
static void *inode_model_allocation;
static size_t inode_model_allocation_size, inode_model_freed_size;
static unsigned inode_model_attempts, inode_model_allocations, inode_model_frees;
static bool inode_model_fail_next;

static inline void
inode_model_reset(void)
{
    MODEL_CHECK(pthread_mutex_lock(&inode_model_allocator_lock) == 0);
    if (inode_model_allocation != NULL) {
        MODEL_CHECK(inode_model_frees == 1);
        free(inode_model_allocation);
    }
    inode_model_allocation = NULL;
    inode_model_allocation_size = 0;
    inode_model_freed_size = 0;
    inode_model_attempts = 0;
    inode_model_allocations = 0;
    inode_model_frees = 0;
    inode_model_fail_next = false;
    MODEL_CHECK(pthread_mutex_unlock(&inode_model_allocator_lock) == 0);
}

static inline void *
kmem_zalloc(size_t size, int flags)
{
    void *result;
    MODEL_CHECK(pthread_mutex_lock(&inode_model_allocator_lock) == 0);
    MODEL_CHECK(flags == KM_NOSLEEP);
    MODEL_CHECK(size != 0);
    MODEL_CHECK(inode_model_allocation == NULL);
    inode_model_attempts++;
    if (inode_model_fail_next) {
        inode_model_fail_next = false;
        MODEL_CHECK(pthread_mutex_unlock(&inode_model_allocator_lock) == 0);
        return NULL;
    }
    result = calloc(1, size);
    MODEL_CHECK(result != NULL);
    inode_model_allocation = result;
    inode_model_allocation_size = size;
    inode_model_allocations++;
    MODEL_CHECK(pthread_mutex_unlock(&inode_model_allocator_lock) == 0);
    return result;
}

static inline void
kmem_free(void *pointer, size_t size)
{
    MODEL_CHECK(pthread_mutex_lock(&inode_model_allocator_lock) == 0);
    MODEL_CHECK(pointer == inode_model_allocation && pointer != NULL);
    MODEL_CHECK(size == inode_model_allocation_size);
    MODEL_CHECK(inode_model_frees == 0);
    inode_model_freed_size = size;
    inode_model_frees++;
    MODEL_CHECK(pthread_mutex_unlock(&inode_model_allocator_lock) == 0);
}

static inline unsigned int
atomic_cas_uint(volatile unsigned int *target, unsigned int old,
    unsigned int replacement)
{
    unsigned int observed = old;
    (void)__atomic_compare_exchange_n(target, &observed, replacement, false,
        __ATOMIC_RELAXED, __ATOMIC_RELAXED);
    return observed;
}

#define atomic_load_relaxed(pointer) __atomic_load_n((pointer), __ATOMIC_RELAXED)
#define atomic_load_acquire(pointer) __atomic_load_n((pointer), __ATOMIC_ACQUIRE)
#define atomic_store_relaxed(pointer, value) \
    __atomic_store_n((pointer), (value), __ATOMIC_RELAXED)

static inline void membar_acquire(void)
{
    __atomic_thread_fence(__ATOMIC_ACQUIRE);
}

static inline void membar_release(void)
{
    __atomic_thread_fence(__ATOMIC_RELEASE);
}

#endif /* NATIVE_DRM_INODE_MODEL_H */

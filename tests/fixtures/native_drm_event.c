/* Test-only API model around unchanged extracted DRM event functions.
 * The uio/list/locks below are mocks, not an assertion of NetBSD kernel ABI.
 * User-memory bytes partially copied before EFAULT are intentionally retained.
 */
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>

#define ERESTARTSYS 512
#ifndef ERESTART
#define ERESTART 513
#endif
#define O_NONBLOCK 4
#define KM_SLEEP 1
#define EPOLLIN 1
#define EPOLLRDNORM 2
#define KASSERT(condition) assert(condition)

struct iovec { void *iov_base; size_t iov_len; };
struct uio {
    struct iovec *uio_iov;
    int uio_iovcnt;
    off_t uio_offset;
    ssize_t uio_resid;
};
struct list_head { struct list_head *next, *prev; };
struct mock_lock { int held; };
struct mock_waitq { int marker; };
struct drm_device { struct mock_lock event_lock; };
struct drm_minor { struct drm_device *dev; };
struct drm_event { uint32_t type, length; unsigned char payload[24]; };
struct drm_pending_event {
    struct list_head link;
    struct drm_event *event;
    unsigned fixture_id;
};
struct drm_file {
    struct drm_minor *minor;
    struct mock_lock event_read_lock;
    struct mock_waitq event_wait;
    unsigned event_space;
    struct list_head event_list;
};
struct linux_file { struct drm_file *private_data; int f_flags; };

struct context {
    struct drm_device device;
    struct drm_minor minor;
    struct drm_file priv;
    struct linux_file file;
    struct drm_event events[3];
    struct drm_pending_event pending[3];
    unsigned char buffers[3][8];
    struct iovec iov[3];
    struct uio uio;
    void *allocation;
    size_t allocation_size;
    unsigned allocations, frees, lock_calls, unlocks, waits, wakes, copies;
    unsigned freed_events[3];
    unsigned fail_lock_call, fail_copy_call, copy_before_failure;
    int lock_error, wait_error, wait_inject_event;
};
static struct context ctx;
static unsigned cases;

static void list_init(struct list_head *head)
{
    head->next = head;
    head->prev = head;
}
static int list_empty(const struct list_head *head)
{
    return head->next == head;
}
static void list_add(struct list_head *item, struct list_head *head)
{
    item->next = head->next;
    item->prev = head;
    head->next->prev = item;
    head->next = item;
}
static void list_add_tail(struct list_head *item, struct list_head *head)
{
    item->next = head;
    item->prev = head->prev;
    head->prev->next = item;
    head->prev = item;
}
static void list_del(struct list_head *item)
{
    assert(item->next != NULL && item->prev != NULL);
    item->prev->next = item->next;
    item->next->prev = item->prev;
    item->next = NULL;
    item->prev = NULL;
}
#define list_first_entry(head, type, member) \
    ((type *)((char *)(head)->next - offsetof(type, member)))

static void spin_lock(struct mock_lock *lock)
{
    assert(lock->held == 0);
    lock->held = 1;
}
static void spin_unlock(struct mock_lock *lock)
{
    assert(lock->held == 1);
    lock->held = 0;
}
#define spin_lock_irqsave(lock, flags) do { (flags) = 0; spin_lock(lock); } while (0)
#define spin_unlock_irqrestore(lock, flags) do { assert((flags) == 0); spin_unlock(lock); } while (0)

static int mutex_lock_interruptible(struct mock_lock *lock)
{
    assert(lock == &ctx.priv.event_read_lock && lock->held == 0);
    ctx.lock_calls++;
    if (ctx.fail_lock_call == ctx.lock_calls)
        return ctx.lock_error;
    lock->held = 1;
    return 0;
}
static void mutex_unlock(struct mock_lock *lock)
{
    assert(lock == &ctx.priv.event_read_lock && lock->held == 1);
    ctx.unlocks++;
    lock->held = 0;
}
static void queue_event(unsigned id, uint32_t length)
{
    assert(id < 3 && length >= 8 && length <= sizeof(ctx.events[id]));
    ctx.events[id].type = id + 1;
    ctx.events[id].length = length;
    memset(ctx.events[id].payload, (int)(0x30 + id), sizeof(ctx.events[id].payload));
    ctx.pending[id].event = &ctx.events[id];
    ctx.pending[id].fixture_id = id;
    assert(ctx.priv.event_space >= length);
    ctx.priv.event_space -= length;
    list_add_tail(&ctx.pending[id].link, &ctx.priv.event_list);
}
static int mock_wait(struct mock_waitq *queue, int ready)
{
    assert(queue == &ctx.priv.event_wait);
    assert(ctx.priv.event_read_lock.held == 0);
    (void)ready;
    ctx.waits++;
    if (ctx.wait_error != 0)
        return ctx.wait_error;
    assert(ctx.wait_inject_event >= 0);
    queue_event((unsigned)ctx.wait_inject_event, 8);
    ctx.wait_inject_event = -1;
    return 0;
}
#define wait_event_interruptible(queue, ready) mock_wait(&(queue), (ready))
static void wake_up_interruptible_poll(struct mock_waitq *queue, int mask)
{
    assert(queue == &ctx.priv.event_wait && mask == (EPOLLIN | EPOLLRDNORM));
    assert(ctx.device.event_lock.held == 0);
    ctx.wakes++;
}
static void *kmem_alloc(size_t size, int flags)
{
    assert(flags == KM_SLEEP && ctx.allocation == NULL);
    /* An invalid-count mutant is rejected before making a huge allocation. */
    assert(size > 0 && size <= sizeof(ctx.iov));
    ctx.allocations++;
    ctx.allocation_size = size;
    ctx.allocation = malloc(size);
    assert(ctx.allocation != NULL);
    memset(ctx.allocation, 0xa5, size);
    return ctx.allocation;
}
static void kmem_free(void *pointer, size_t size)
{
    assert(pointer == ctx.allocation && pointer != NULL);
    assert(size == ctx.allocation_size);
    assert(ctx.priv.event_read_lock.held == 0 && ctx.device.event_lock.held == 0);
    ctx.frees++;
    free(pointer);
    ctx.allocation = NULL;
}
static void kfree(struct drm_pending_event *event)
{
    assert(event->fixture_id < 3);
    assert(event->link.next == NULL && event->link.prev == NULL);
    assert(ctx.freed_events[event->fixture_id] == 0);
    ctx.freed_events[event->fixture_id]++;
}
static void copy_bytes(const unsigned char *source, size_t length, struct uio *uio)
{
    while (length != 0) {
        size_t count;
        struct iovec *iov;
        assert(uio->uio_iovcnt > 0 && uio->uio_resid > 0);
        iov = uio->uio_iov;
        if (iov->iov_len == 0) {
            uio->uio_iov++;
            uio->uio_iovcnt--;
            continue;
        }
        count = length < iov->iov_len ? length : iov->iov_len;
        assert(count <= (size_t)uio->uio_resid);
        memcpy(iov->iov_base, source, count);
        iov->iov_base = (unsigned char *)iov->iov_base + count;
        iov->iov_len -= count;
        uio->uio_offset += (off_t)count;
        uio->uio_resid -= (ssize_t)count;
        source += count;
        length -= count;
        if (iov->iov_len == 0) {
            uio->uio_iov++;
            uio->uio_iovcnt--;
        }
    }
}
static int uiomove(const void *source, size_t length, struct uio *uio)
{
    size_t count = length;
    ctx.copies++;
    assert(ctx.priv.event_read_lock.held == 1);
    if (ctx.fail_copy_call == ctx.copies) {
        if (count > ctx.copy_before_failure)
            count = ctx.copy_before_failure;
        copy_bytes(source, count, uio);
        return EFAULT;
    }
    copy_bytes(source, count, uio);
    return 0;
}

/* SOURCE_BOUND_FUNCTIONS */

static void reset(void)
{
    unsigned i;
    assert(ctx.allocation == NULL);
    memset(&ctx, 0, sizeof(ctx));
    ctx.minor.dev = &ctx.device;
    ctx.priv.minor = &ctx.minor;
    ctx.priv.event_space = 64;
    list_init(&ctx.priv.event_list);
    ctx.file.private_data = &ctx.priv;
    ctx.wait_error = -ERESTARTSYS;
    ctx.lock_error = -ERESTARTSYS;
    ctx.wait_inject_event = -1;
    for (i = 0; i < 3; i++) {
        ctx.iov[i].iov_base = ctx.buffers[i];
        ctx.iov[i].iov_len = sizeof(ctx.buffers[i]);
    }
    ctx.uio.uio_iov = ctx.iov;
    ctx.uio.uio_iovcnt = 3;
    ctx.uio.uio_resid = 24;
    ctx.uio.uio_offset = 100;
}
static void done(const char *name, unsigned allocated)
{
    assert(ctx.allocation == NULL);
    assert(ctx.allocations == allocated && ctx.frees == allocated);
    assert(ctx.priv.event_read_lock.held == 0 && ctx.device.event_lock.held == 0);
    if (allocated)
        assert(ctx.allocation_size == 3 * sizeof(struct iovec));
    cases++;
    printf("CASE_PASS %s\n", name);
    fflush(stdout);
}
static void assert_initial_uio(void)
{
    unsigned i;
    assert(ctx.uio.uio_iov == ctx.iov && ctx.uio.uio_iovcnt == 3);
    assert(ctx.uio.uio_resid == 24 && ctx.uio.uio_offset == 100);
    for (i = 0; i < 3; i++) {
        assert(ctx.iov[i].iov_base == ctx.buffers[i]);
        assert(ctx.iov[i].iov_len == sizeof(ctx.buffers[i]));
    }
}
static void assert_after_first_event(void)
{
    assert(ctx.uio.uio_iov == &ctx.iov[1] && ctx.uio.uio_iovcnt == 2);
    assert(ctx.uio.uio_resid == 16 && ctx.uio.uio_offset == 108);
    assert(ctx.iov[0].iov_base == ctx.buffers[0] + 8 && ctx.iov[0].iov_len == 0);
    assert(ctx.iov[1].iov_base == ctx.buffers[1] && ctx.iov[1].iov_len == 8);
    assert(ctx.iov[2].iov_base == ctx.buffers[2] && ctx.iov[2].iov_len == 8);
    assert(memcmp(ctx.buffers[0], &ctx.events[0], 8) == 0);
}
static void assert_queue(unsigned count, unsigned first)
{
    struct list_head *entry = ctx.priv.event_list.next;
    unsigned observed = 0;
    while (entry != &ctx.priv.event_list) {
        struct drm_pending_event *event = (struct drm_pending_event *)
            ((char *)entry - offsetof(struct drm_pending_event, link));
        assert(observed < 3);
        if (observed == 0)
            assert(event->fixture_id == first);
        assert(event->link.next->prev == &event->link);
        assert(event->link.prev->next == &event->link);
        observed++;
        entry = entry->next;
    }
    assert(observed == count);
}

int main(void)
{
    unsigned failure_bytes;
    setvbuf(stdout, NULL, _IONBF, 0);
    reset();
    assert(drm_native_error(0) == 0);
    assert(drm_native_error(-EFAULT) == EFAULT);
    assert(drm_native_error(EINTR) == EINTR);
    assert(drm_native_error(-ERESTARTSYS) == ERESTART);
    done("error_translation", 0);

    reset();
    ctx.uio.uio_iovcnt = -1;
    ctx.uio.uio_resid = 0;
    assert(drm_native_read_events(&ctx.file, &ctx.uio) == 0);
    assert(ctx.lock_calls == 0);
    done("zero_residual_before_count_validation", 0);

    reset();
    ctx.uio.uio_iovcnt = 0;
    assert(drm_native_read_events(&ctx.file, &ctx.uio) == EINVAL);
    assert(ctx.lock_calls == 0);
    done("zero_iovec_count_no_allocation", 0);

    reset();
    ctx.uio.uio_iovcnt = -1;
    assert(drm_native_read_events(&ctx.file, &ctx.uio) == EINVAL);
    assert(ctx.lock_calls == 0);
    done("negative_iovec_count_no_allocation", 0);

    reset();
    ctx.file.f_flags = O_NONBLOCK;
    assert(drm_native_read_events(&ctx.file, &ctx.uio) == EAGAIN);
    assert_initial_uio();
    assert(ctx.waits == 0 && ctx.unlocks == 1 && ctx.lock_calls == 1);
    done("empty_nonblocking", 1);

    reset();
    ctx.fail_lock_call = 1;
    assert(drm_native_read_events(&ctx.file, &ctx.uio) == ERESTART);
    assert_initial_uio();
    assert(ctx.waits == 0 && ctx.unlocks == 0 && ctx.lock_calls == 1);
    done("initial_lock_restart", 1);

    reset();
    ctx.fail_lock_call = 1;
    ctx.lock_error = -EINTR;
    assert(drm_native_read_events(&ctx.file, &ctx.uio) == EINTR);
    assert(ctx.unlocks == 0 && ctx.lock_calls == 1);
    done("initial_lock_eintr", 1);

    reset();
    assert(drm_native_read_events(&ctx.file, &ctx.uio) == ERESTART);
    assert_initial_uio();
    assert(ctx.waits == 1 && ctx.unlocks == 1 && ctx.lock_calls == 1);
    done("empty_wait_restart", 1);

    reset();
    ctx.wait_error = -EINTR;
    assert(drm_native_read_events(&ctx.file, &ctx.uio) == EINTR);
    assert_initial_uio();
    assert(ctx.waits == 1 && ctx.unlocks == 1);
    done("empty_wait_eintr", 1);

    reset();
    ctx.wait_error = 0;
    ctx.wait_inject_event = 0;
    ctx.fail_lock_call = 2;
    assert(drm_native_read_events(&ctx.file, &ctx.uio) == ERESTART);
    assert_initial_uio();
    assert_queue(1, 0);
    assert(ctx.priv.event_space == 56 && ctx.copies == 0);
    assert(ctx.waits == 1 && ctx.unlocks == 1 && ctx.lock_calls == 2);
    done("wake_then_relock_restart_retains_event", 1);

    reset();
    ctx.wait_error = 0;
    ctx.wait_inject_event = 0;
    assert(drm_native_read_events(&ctx.file, &ctx.uio) == 0);
    assert_after_first_event();
    assert_queue(0, 0);
    assert(ctx.waits == 1 && ctx.unlocks == 2 && ctx.lock_calls == 2);
    assert(ctx.freed_events[0] == 1 && ctx.priv.event_space == 64);
    done("wake_relock_and_deliver", 1);

    reset();
    queue_event(0, 12);
    ctx.uio.uio_resid = 4;
    assert(drm_native_read_events(&ctx.file, &ctx.uio) == 0);
    assert(ctx.uio.uio_resid == 4 && ctx.uio.uio_offset == 100);
    assert(ctx.uio.uio_iov == ctx.iov && ctx.uio.uio_iovcnt == 3);
    assert_queue(1, 0);
    assert(ctx.copies == 0 && ctx.wakes == 1 && ctx.priv.event_space == 52);
    done("undersized_buffer_requeues_without_copy", 1);

    reset();
    queue_event(0, 8);
    queue_event(1, 12);
    ctx.fail_copy_call = 1;
    ctx.copy_before_failure = 3;
    assert(drm_native_read_events(&ctx.file, &ctx.uio) == EFAULT);
    assert_initial_uio();
    assert_queue(2, 0);
    assert(ctx.pending[0].link.next == &ctx.pending[1].link);
    assert(ctx.freed_events[0] == 0 && ctx.freed_events[1] == 0);
    assert(ctx.wakes == 1 && ctx.priv.event_space == 44);
    done("first_fault_restores_cursor_and_queue_order", 1);

    for (failure_bytes = 3; failure_bytes <= 10; failure_bytes += 7) {
        reset();
        queue_event(0, 8);
        queue_event(1, 12);
        ctx.fail_copy_call = 2;
        ctx.copy_before_failure = failure_bytes;
        assert(drm_native_read_events(&ctx.file, &ctx.uio) == 0);
        assert_after_first_event();
        assert_queue(1, 1);
        assert(ctx.freed_events[0] == 1 && ctx.freed_events[1] == 0);
        assert(ctx.copies == 2 && ctx.wakes == 1 && ctx.priv.event_space == 52);
        done(failure_bytes == 3 ? "second_fault_restores_remaining_iovec" :
             "second_fault_crossing_iovecs_restores_both", 1);
    }

    reset();
    queue_event(0, 8);
    queue_event(1, 12);
    assert(drm_native_read_events(&ctx.file, &ctx.uio) == 0);
    assert_queue(0, 0);
    assert(ctx.uio.uio_resid == 4 && ctx.uio.uio_offset == 120);
    assert(ctx.uio.uio_iov == &ctx.iov[2] && ctx.uio.uio_iovcnt == 1);
    assert(ctx.iov[0].iov_len == 0 && ctx.iov[1].iov_len == 0);
    assert(ctx.iov[2].iov_len == 4 && ctx.iov[2].iov_base == ctx.buffers[2] + 4);
    assert(ctx.copies == 2 && ctx.freed_events[0] == 1 && ctx.freed_events[1] == 1);
    assert(ctx.priv.event_space == 64 && ctx.wakes == 0);
    done("two_events_success_free_original_snapshot_size", 1);

    reset();
    queue_event(0, 24);
    assert(drm_native_read_events(&ctx.file, &ctx.uio) == 0);
    assert(ctx.uio.uio_resid == 0 && ctx.uio.uio_iovcnt == 0);
    assert(ctx.uio.uio_iov == &ctx.iov[3] && ctx.uio.uio_offset == 124);
    assert(ctx.freed_events[0] == 1 && ctx.priv.event_space == 64);
    done("all_iovecs_consumed_free_original_snapshot_size", 1);

    reset();
    queue_event(0, 8);
    queue_event(1, 24);
    assert(drm_native_read_events(&ctx.file, &ctx.uio) == 0);
    assert_after_first_event();
    assert_queue(1, 1);
    assert(ctx.copies == 1 && ctx.freed_events[0] == 1 && ctx.wakes == 1);
    assert(ctx.priv.event_space == 40);
    done("progress_then_undersized_event_retained", 1);

    reset();
    queue_event(0, 8);
    ctx.file.f_flags = O_NONBLOCK;
    ctx.wait_error = -EINTR;
    assert(drm_native_read_events(&ctx.file, &ctx.uio) == 0);
    assert_after_first_event();
    assert(ctx.waits == 0 && ctx.freed_events[0] == 1);
    done("progress_returns_before_wait_or_eagain", 1);

    assert(cases == 19);
    printf("NATIVE_DRM_EVENT_CASES_PASS count=%u\n", cases);
    return 0;
}

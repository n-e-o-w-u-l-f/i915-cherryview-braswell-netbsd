/* Native HP userland lifecycle model of the actual native-only inode owner.
 * No Linux inode layout, native kernel ABI, FD or DRM acceptance is implied.
 */
#define _POSIX_C_SOURCE 200809L
#define _NETBSD_SOURCE 1
#define NATIVE_DRM_INODE_TEST 1
#include "native_drm_inode_model.h"
#include "../../compat/native-drm-inode/native_drm_inode.c"

#include <sys/resource.h>
#include <sys/wait.h>
#include <signal.h>
#include <unistd.h>

static unsigned cases;
static const dev_t expected_rdev = (dev_t)0x1234;
static const ino_t expected_ino = (ino_t)0x12345678;
static const mode_t expected_mode = (mode_t)(S_IFCHR | 0640);

static void
case_pass(const char *name)
{
    cases++;
    printf("CASE_PASS %s\n", name);
    fflush(stdout);
}

static struct native_drm_inode *
create_owner(void)
{
    struct native_drm_inode *inode = NULL;
    MODEL_CHECK(native_drm_inode_create(expected_rdev, expected_ino,
        expected_mode, &inode) == 0);
    MODEL_CHECK(inode != NULL);
    MODEL_CHECK(inode_model_attempts == 1 && inode_model_allocations == 1);
    MODEL_CHECK(inode_model_allocation_size == sizeof(*inode));
    MODEL_CHECK(inode_model_frees == 0);
    return inode;
}

static void
check_identity(const struct native_drm_inode *inode)
{
    MODEL_CHECK(native_drm_inode_rdev(inode) == expected_rdev);
    MODEL_CHECK(native_drm_inode_ino(inode) == expected_ino);
    MODEL_CHECK(native_drm_inode_mode(inode) == expected_mode);
}

static void
check_freed(void)
{
    /* Read allocator metadata only, never the logically freed inode. */
    MODEL_CHECK(inode_model_allocations == 1);
    MODEL_CHECK(inode_model_frees == 1);
    MODEL_CHECK(inode_model_freed_size == sizeof(struct native_drm_inode));
}

static void
invalid_arguments(void)
{
    static const mode_t modes[] = { 0, S_IFREG | 0600, S_IFDIR | 0755 };
    struct native_drm_inode *inode;
    unsigned i;

    inode_model_reset();
    MODEL_CHECK(native_drm_inode_create(expected_rdev, expected_ino,
        expected_mode, NULL) == EINVAL);
    MODEL_CHECK(inode_model_attempts == 0);
    for (i = 0; i < sizeof(modes) / sizeof(modes[0]); i++) {
        inode = (struct native_drm_inode *)(uintptr_t)1;
        MODEL_CHECK(native_drm_inode_create(expected_rdev, expected_ino,
            modes[i], &inode) == EINVAL);
        MODEL_CHECK(inode == NULL);
        MODEL_CHECK(inode_model_attempts == 0 && inode_model_frees == 0);
    }
    case_pass("invalid_arguments_and_mode");
}

static void
allocation_failure(void)
{
    struct native_drm_inode *inode = (struct native_drm_inode *)(uintptr_t)1;
    inode_model_reset();
    inode_model_fail_next = true;
    MODEL_CHECK(native_drm_inode_create(expected_rdev, expected_ino,
        expected_mode, &inode) == ENOMEM);
    MODEL_CHECK(inode == NULL);
    MODEL_CHECK(inode_model_attempts == 1 && inode_model_allocations == 0);
    MODEL_CHECK(inode_model_frees == 0 && inode_model_allocation == NULL);
    case_pass("allocation_failure_clears_output");
}

static void
initial_reference(void)
{
    struct native_drm_inode *inode;
    inode_model_reset();
    inode = create_owner();
    check_identity(inode);
    MODEL_CHECK(atomic_load_relaxed(&inode->refcount) == 1);
    native_drm_inode_put(inode);
    check_freed();
    case_pass("identity_initial_reference_and_exact_final_free");
}

static void
retained_reference(void)
{
    struct native_drm_inode *inode;
    inode_model_reset();
    inode = create_owner();
    MODEL_CHECK(native_drm_inode_tryget(inode));
    MODEL_CHECK(atomic_load_relaxed(&inode->refcount) == 2);
    native_drm_inode_put(inode);
    MODEL_CHECK(inode_model_frees == 0);
    MODEL_CHECK(atomic_load_relaxed(&inode->refcount) == 1);
    check_identity(inode);
    native_drm_inode_put(inode);
    check_freed();
    case_pass("retain_then_last_drop");
}

static void
zero_reference(void)
{
    /* Whitebox boundary control on live stack storage, never a freed object. */
    struct native_drm_inode inode;
    inode_model_reset();
    memset(&inode, 0, sizeof(inode));
    MODEL_CHECK(!native_drm_inode_tryget(NULL));
    MODEL_CHECK(!native_drm_inode_tryget(&inode));
    MODEL_CHECK(atomic_load_relaxed(&inode.refcount) == 0);
    MODEL_CHECK(inode_model_attempts == 0 && inode_model_frees == 0);
    case_pass("zero_reference_not_resurrected");
}

static void
overflow_reference(void)
{
    struct native_drm_inode inode;
    inode_model_reset();
    memset(&inode, 0, sizeof(inode));
    atomic_store_relaxed(&inode.refcount, UINT_MAX);
    MODEL_CHECK(!native_drm_inode_tryget(&inode));
    MODEL_CHECK(atomic_load_relaxed(&inode.refcount) == UINT_MAX);
    MODEL_CHECK(inode_model_attempts == 0 && inode_model_frees == 0);
    case_pass("saturated_reference_not_incremented");
}

static void
expect_put_panic(bool null_argument)
{
    int channel[2], status;
    char diagnostic[2048];
    size_t used = 0;
    ssize_t count;
    pid_t child;

    MODEL_CHECK(pipe(channel) == 0);
    child = fork();
    MODEL_CHECK(child >= 0);
    if (child == 0) {
        struct native_drm_inode inode;
        (void)close(channel[0]);
        if (dup2(channel[1], STDERR_FILENO) < 0)
            _exit(121);
        (void)close(channel[1]);
        memset(&inode, 0, sizeof(inode));
        native_drm_inode_put(null_argument ? NULL : &inode);
        _exit(122);
    }
    MODEL_CHECK(close(channel[1]) == 0);
    for (;;) {
        MODEL_CHECK(used < sizeof(diagnostic) - 1);
        count = read(channel[0], diagnostic + used,
            sizeof(diagnostic) - 1 - used);
        if (count < 0 && errno == EINTR)
            continue;
        MODEL_CHECK(count >= 0);
        if (count == 0)
            break;
        used += (size_t)count;
    }
    diagnostic[used] = '\0';
    MODEL_CHECK(close(channel[0]) == 0);
    MODEL_CHECK(waitpid(child, &status, 0) == child);
    MODEL_CHECK(WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT);
    MODEL_CHECK(strstr(diagnostic, "native_drm_inode_put") != NULL);
}

static void
underflow_panics(void)
{
    inode_model_reset();
    expect_put_panic(false);
    expect_put_panic(true);
    MODEL_CHECK(inode_model_attempts == 0 && inode_model_frees == 0);
    case_pass("zero_and_null_put_panic");
}

struct worker_arguments {
    struct native_drm_inode *inode;
    pthread_barrier_t *barrier;
    unsigned iterations;
    volatile unsigned *retains;
};

static void
barrier_wait(pthread_barrier_t *barrier)
{
    int result = pthread_barrier_wait(barrier);
    MODEL_CHECK(result == 0 || result == PTHREAD_BARRIER_SERIAL_THREAD);
}

static void *
retain_worker(void *opaque)
{
    struct worker_arguments *arguments = opaque;
    unsigned i;
    barrier_wait(arguments->barrier);
    for (i = 0; i < arguments->iterations; i++) {
        MODEL_CHECK(native_drm_inode_tryget(arguments->inode));
        check_identity(arguments->inode);
        (void)__atomic_fetch_add(arguments->retains, 1, __ATOMIC_RELAXED);
        native_drm_inode_put(arguments->inode);
    }
    return NULL;
}

static void
concurrent_references(unsigned threads, const char *name)
{
    struct native_drm_inode *inode;
    struct worker_arguments arguments;
    pthread_t workers[4];
    pthread_barrier_t barrier;
    volatile unsigned retains = 0;
    unsigned i;

    inode_model_reset();
    MODEL_CHECK(threads >= 2 && threads <= 4);
    inode = create_owner();
    MODEL_CHECK(pthread_barrier_init(&barrier, NULL, threads + 1) == 0);
    arguments.inode = inode;
    arguments.barrier = &barrier;
    arguments.iterations = 4096;
    arguments.retains = &retains;
    for (i = 0; i < threads; i++)
        MODEL_CHECK(pthread_create(&workers[i], NULL, retain_worker, &arguments) == 0);
    barrier_wait(&barrier);
    for (i = 0; i < threads; i++)
        MODEL_CHECK(pthread_join(workers[i], NULL) == 0);
    MODEL_CHECK(pthread_barrier_destroy(&barrier) == 0);
    MODEL_CHECK(atomic_load_relaxed(&retains) == threads * arguments.iterations);
    MODEL_CHECK(inode_model_frees == 0);
    MODEL_CHECK(atomic_load_relaxed(&inode->refcount) == 1);
    check_identity(inode);
    native_drm_inode_put(inode);
    check_freed();
    case_pass(name);
}

int
main(void)
{
    struct rlimit limit = { 0, 0 };
    MODEL_CHECK(setrlimit(RLIMIT_CORE, &limit) == 0);
    MODEL_CHECK(setvbuf(stdout, NULL, _IONBF, 0) == 0);
    invalid_arguments();
    allocation_failure();
    initial_reference();
    retained_reference();
    zero_reference();
    overflow_reference();
    underflow_panics();
    concurrent_references(2, "concurrent_two_threads_parent_owned");
    concurrent_references(4, "concurrent_four_threads_parent_owned");
    MODEL_CHECK(cases == 9);
    inode_model_reset();
    printf("NATIVE_DRM_INODE_CASES_PASS count=%u\n", cases);
    return 0;
}

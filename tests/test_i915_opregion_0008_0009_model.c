/* Isolated negative-path C model for NetBSD i915 candidates 0008 and 0009.
 * Does not link a kernel, invoke actual DRM callbacks, or access hardware.
 * Expected origin: pinned NetBSD/src@03d918f6 and work-branch candidate 0009.
 */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>

enum { OPREGION_SIZE = 8192 };
struct asle { size_t rvds; };
struct opregion { void *header; struct asle *asle; void *rvda; };
struct unmap_call { void *ptr; size_t size; };
static struct unmap_call unmapped[2];
static unsigned unmap_count;
static unsigned dereg_count;
static unsigned suspend_count;
static unsigned pmu_unreg_count;
static unsigned gem_unreg_count;
static unsigned drm_unreg_count;
static unsigned late_register_count;

static void mock_unmap(void *ptr, size_t size)
{
    assert(ptr != NULL);
    assert(unmap_count < 2);
    unmapped[unmap_count++] = (struct unmap_call){ ptr, size };
}

static void candidate_0009_opregion_unregister(struct opregion *o)
{
    /* Only the relevant pinned NetBSD path and 0009's changed expression. */
    ++suspend_count;
    if (!o->header)
        return;
    ++dereg_count;  /* Conditionally present ACPI notifier, mocked. */
    size_t rvds = o->rvda ? o->asle->rvds : 0;
    mock_unmap(o->header, OPREGION_SIZE);
    if (o->rvda) {
        mock_unmap(o->rvda, rvds);
        o->rvda = NULL;
    }
    o->header = NULL;
    o->asle = NULL;
}

static int candidate_0008_register_failure_path(int drm_return)
{
    /* Relevant i915 register-failure branch; full kernel cleanup omitted. */
    if (drm_return) {
        ++drm_unreg_count;
        ++pmu_unreg_count;
        ++gem_unreg_count;
        return drm_return;
    }
    ++late_register_count;
    return 0;
}

static void counters_reset(void)
{
    unmap_count = dereg_count = suspend_count = 0;
    pmu_unreg_count = gem_unreg_count = drm_unreg_count = 0;
    late_register_count = 0;
}

int main(void)
{
    int header = 1, vbt = 2;
    struct asle a = { .rvds = 4096 };
    struct opregion o = { 0 };

    /* T1: setup failed before header mapping: no dereference/unmap. */
    counters_reset();
    candidate_0009_opregion_unregister(&o);
    assert(unmap_count == 0 && suspend_count == 1 && dereg_count == 0);

    /* T2: mapped OpRegion without ASLE: original unconditional deref
     * would not be safe; 0009's guarded path must avoid it.
     */
    counters_reset();
    o = (struct opregion){ .header = &header, .asle = NULL, .rvda = NULL };
    candidate_0009_opregion_unregister(&o);
    assert(unmap_count == 1 && unmapped[0].ptr == &header);
    assert(unmapped[0].size == OPREGION_SIZE);

    /* T3: ASLE present, RVDA not mapped. */
    counters_reset();
    o = (struct opregion){ .header = &header, .asle = &a, .rvda = NULL };
    candidate_0009_opregion_unregister(&o);
    assert(unmap_count == 1 && o.asle == NULL && o.header == NULL);

    /* T4: ASLE and RVDA mapped: capture RVDS before unmapping header. */
    counters_reset();
    o = (struct opregion){ .header = &header, .asle = &a, .rvda = &vbt };
    candidate_0009_opregion_unregister(&o);
    assert(unmap_count == 2 && unmapped[0].ptr == &header);
    assert(unmapped[1].ptr == &vbt && unmapped[1].size == 4096);
    assert(o.rvda == NULL && o.asle == NULL);

    /* T5: failed DRM register: unwind via 0008, no late registration. */
    counters_reset();
    assert(candidate_0008_register_failure_path(-12) == -12);
    assert(drm_unreg_count == 1 && pmu_unreg_count == 1);
    assert(gem_unreg_count == 1 && late_register_count == 0);

    /* T6: successful DRM register must not unwind. */
    counters_reset();
    assert(candidate_0008_register_failure_path(0) == 0);
    assert(drm_unreg_count == 0 && pmu_unreg_count == 0);
    assert(gem_unreg_count == 0 && late_register_count == 1);

    puts("I915_0008_0009_ISOLATED_C_MODEL_PASS_6_6");
    return 0;
}

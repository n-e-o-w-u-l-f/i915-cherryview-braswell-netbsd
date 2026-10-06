/* Execute the generated consumer bodies and exact pinned rounding/do_div macros. */
#include <sys/types.h>
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef unsigned long long u64;
#define KASSERT(condition) assert(condition)
static unsigned int sleep_checks;
#define ASSERT_SLEEPABLE() (++sleep_checks)
#include "test_list_type.h"
#include "test_err_header.h"
#include "test_math_macros.h"
#include "test_pwm_header.h"
#include "vectors.h"

#define COUNT(a) (sizeof(a) / sizeof((a)[0]))
_Static_assert(sizeof(u64) == 8, "frozen Linux u64 width");
_Static_assert(sizeof(struct pwm_state) == 24, "HP frozen state layout");
_Static_assert(sizeof(struct pwm_args) == 16, "HP frozen args layout");
_Static_assert(sizeof(struct pwm_waveform) == 24, "waveform nanosecond widths");
_Static_assert(sizeof(struct pwm_device) == 96, "HP frozen consumer layout");
_Static_assert(offsetof(struct pwm_device, args) == 32, "args offset");
_Static_assert(offsetof(struct pwm_device, state) == 48, "state offset");
_Static_assert(offsetof(struct pwm_device, last) == 72, "debug state offset");
_Static_assert(sizeof(struct pwm_lookup) == 64, "HP lookup layout");

static void
check_get_vectors(void)
{
    for (size_t i = 0; i < COUNT(get_vectors); i++) {
        const struct get_vector *v = &get_vectors[i];
        struct pwm_state state = {
            .period = v->period, .duty_cycle = v->duty,
            .polarity = PWM_POLARITY_INVERSED, .enabled = true, .usage_power = true,
        };
        unsigned int got = pwm_get_relative_duty_cycle(&state, v->scale);
        if (got != v->result) {
            fprintf(stderr, "getter vector %zu: got %u expected %u\n", i, got, v->result);
            abort();
        }
        assert(state.period == v->period && state.duty_cycle == v->duty);
        assert(state.polarity == PWM_POLARITY_INVERSED && state.enabled && state.usage_power);
    }
    printf("GETTER_ORACLE_VECTORS %zu PASS\n", COUNT(get_vectors));
}

static void
check_set_vectors(void)
{
    for (size_t i = 0; i < COUNT(set_vectors); i++) {
        const struct set_vector *v = &set_vectors[i];
        struct pwm_state state = {
            .period = v->period, .duty_cycle = v->old,
            .polarity = PWM_POLARITY_INVERSED, .enabled = true, .usage_power = true,
        };
        int error = pwm_set_relative_duty_cycle(&state, v->duty, v->scale);
        if (error != v->error || state.duty_cycle != v->result) {
            fprintf(stderr, "setter vector %zu: got %d/%llu expected %d/%llu\n",
                i, error, state.duty_cycle, v->error, v->result);
            abort();
        }
        assert(state.period == v->period);
        assert(state.polarity == PWM_POLARITY_INVERSED && state.enabled && state.usage_power);
    }
    printf("SETTER_ORACLE_VECTORS %zu PASS\n", COUNT(set_vectors));
}

static void
check_state_helpers(void)
{
    struct pwm_device pwm = {
        .label = "panel", .flags = 0xa5, .hwpwm = 3,
        .args = { .period = 123456, .polarity = PWM_POLARITY_INVERSED },
        .state = { .period = 654321, .duty_cycle = 543210,
            .polarity = PWM_POLARITY_NORMAL, .enabled = true, .usage_power = true },
    };
    struct pwm_state state;
    struct pwm_args args;

    assert(pwm_is_enabled(&pwm));
    assert(pwm_get_period(&pwm) == 654321);
    assert(pwm_get_duty_cycle(&pwm) == 543210);
    assert(pwm_get_polarity(&pwm) == PWM_POLARITY_NORMAL);
    pwm_get_state(&pwm, &state);
    assert(state.period == 654321 && state.duty_cycle == 543210);
    assert(state.polarity == PWM_POLARITY_NORMAL && state.enabled && state.usage_power);
    pwm_get_args(&pwm, &args);
    assert(args.period == 123456 && args.polarity == PWM_POLARITY_INVERSED);
    pwm_init_state(&pwm, &state);
    assert(state.period == 123456 && state.duty_cycle == 0);
    assert(state.polarity == PWM_POLARITY_INVERSED && state.enabled && !state.usage_power);
    assert(pwm.state.period == 654321 && pwm.state.duty_cycle == 543210);
    assert(pwm.state.usage_power);
    pwm.state.enabled = false;
    pwm_init_state(&pwm, &state);
    assert(!state.enabled);
    puts("CACHE_ARGS_INIT_ENABLED_AND_USAGE_POWER PASS");
}

static void
check_disabled_profile(void)
{
    struct pwm_device pwm, saved_pwm;
    struct pwm_state state, saved_state;
    struct pwm_lookup lookup[] = {
        PWM_LOOKUP_WITH_MODULE("pwm-lpss", 2, "i915", "backlight", 10000,
            PWM_POLARITY_NORMAL, "pwm-lpss-platform"),
        PWM_LOOKUP("pwm-lpss", 0, "i915", "panel", 20000, PWM_POLARITY_INVERSED),
    };
    struct pwm_lookup saved_lookup[COUNT(lookup)];
    struct pwm_chip *chip;
    unsigned int before = sleep_checks;

    memset(&pwm, 0xa7, sizeof(pwm));
    memset(&state, 0xb6, sizeof(state));
    pwm.state.enabled = true;
    saved_pwm = pwm;
    saved_state = state;
    assert(pwm_might_sleep(NULL) && pwm_might_sleep(&pwm));
    assert(pwm_apply_might_sleep(&pwm, &state) == -EOPNOTSUPP);
    assert(pwm_apply_atomic(&pwm, &state) == -EOPNOTSUPP);
    assert(pwm_get_state_hw(&pwm, &state) == -EOPNOTSUPP);
    assert(pwm_adjust_config(&pwm) == -EOPNOTSUPP);
    assert(pwm_config(&pwm, -1, -2) == -EINVAL);
    assert(netbsd_linux_pwm_enable(&pwm) == -EINVAL);
    netbsd_linux_pwm_disable(&pwm);
    assert(IS_ERR(pwm_get(NULL, NULL)) && PTR_ERR(pwm_get(NULL, NULL)) == -ENODEV);
    assert(PTR_ERR(devm_pwm_get(NULL, NULL)) == -ENODEV);
    assert(PTR_ERR(devm_fwnode_pwm_get(NULL, NULL, NULL)) == -ENODEV);
    pwm_put(&pwm);
    assert(sleep_checks == before + 9);
    assert(memcmp(&pwm, &saved_pwm, sizeof(pwm)) == 0);
    assert(memcmp(&state, &saved_state, sizeof(state)) == 0);
    /* Even cached-enabled and NULL consumers fail in this disabled profile. */
    assert(netbsd_linux_pwm_enable(NULL) == -EINVAL);
    netbsd_linux_pwm_disable(NULL);
    pwm_put(NULL);
    assert(sleep_checks == before + 12);
    chip = pwmchip_alloc(NULL, 0, 0);
    assert(IS_ERR(chip) && PTR_ERR(chip) == -EINVAL);
    assert(PTR_ERR(devm_pwmchip_alloc(NULL, 1, 100)) == -EINVAL);
    assert(pwmchip_add(chip) == -EINVAL);
    assert(pwmchip_remove(chip) == -EINVAL);
    assert(devm_pwmchip_add(NULL, chip) == -EINVAL);
    pwmchip_put(chip);
    pwmchip_put(NULL);
    assert(lookup[0].list.prev == NULL && lookup[0].list.next == NULL);
    assert(strcmp(lookup[0].provider, "pwm-lpss") == 0 && lookup[0].index == 2);
    assert(strcmp(lookup[0].module, "pwm-lpss-platform") == 0);
    assert(strcmp(lookup[0].dev_id, "i915") == 0 && lookup[0].period == 10000);
    assert(lookup[1].module == NULL && lookup[1].polarity == PWM_POLARITY_INVERSED);
    memcpy(saved_lookup, lookup, sizeof(lookup));
    pwm_add_table(lookup, COUNT(lookup));
    pwm_remove_table(lookup, COUNT(lookup));
    assert(memcmp(saved_lookup, lookup, sizeof(lookup)) == 0);
    assert(sleep_checks == before + 12);
    puts("DISABLED_ERRORS_OUTPUT_PRESERVATION_RELEASES_LOOKUP_AND_SLEEP_CHECKS PASS");
}

int
main(void)
{
    check_get_vectors();
    check_set_vectors();
    check_state_helpers();
    check_disabled_profile();
    return 0;
}

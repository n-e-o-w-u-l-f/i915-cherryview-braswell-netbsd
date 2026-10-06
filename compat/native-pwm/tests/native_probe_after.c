#include <sys/param.h>
#include <sys/device.h>

#include <linux/pwm.h>
#include <dev/pwm/pwmvar.h>

__CTASSERT(sizeof(struct pwm_args) == 16);
__CTASSERT(sizeof(struct pwm_state) == 24);
__CTASSERT(sizeof(struct pwm_waveform) == 24);
__CTASSERT(sizeof(struct pwm_device) == 96);
__CTASSERT(offsetof(struct pwm_state, polarity) == 16);
__CTASSERT(offsetof(struct pwm_state, enabled) == 20);
__CTASSERT(offsetof(struct pwm_state, usage_power) == 21);
__CTASSERT(offsetof(struct pwm_device, args) == 32);
__CTASSERT(offsetof(struct pwm_device, state) == 48);
__CTASSERT(offsetof(struct pwm_device, last) == 72);
__CTASSERT(PWM_POLARITY_NORMAL == 0 && PWM_POLARITY_INVERSED == 1);
__CTASSERT(PWMF_REQUESTED == 0 && PWMF_EXPORTED == 1);

static struct pwm_lookup lookup[] = {
    PWM_LOOKUP_WITH_MODULE("pwm-lpss", 2, "i915", "backlight", 10000,
        PWM_POLARITY_NORMAL, "pwm-lpss-platform"),
    PWM_LOOKUP("pwm-lpss", 0, "i915", "panel", 20000, PWM_POLARITY_INVERSED),
};

int pwm_native_candidate_probe(struct device *, struct fwnode_handle *,
    struct pwm_device *, struct pwm_state *, pwm_tag_t);
int
pwm_native_candidate_probe(struct device *dev, struct fwnode_handle *fwnode,
    struct pwm_device *pwm, struct pwm_state *state, pwm_tag_t native)
{
    struct pwm_args args;
    struct pwm_chip *chip;
    enum netbsd_linux_pwm_polarity polarity = PWM_POLARITY_NORMAL;
    int result;

    pwm_get_state(pwm, state);
    pwm_get_args(pwm, &args);
    pwm_init_state(pwm, state);
    result = pwm_set_relative_duty_cycle(state, 50, 100);
    result += pwm_get_relative_duty_cycle(state, 100);
    result += pwm_get_period(pwm) + pwm_get_duty_cycle(pwm);
    result += pwm_is_enabled(pwm) + pwm_get_polarity(pwm) + polarity;
    result += pwm_might_sleep(pwm);
    result += pwm_apply_might_sleep(pwm, state) + pwm_apply_atomic(pwm, state);
    result += pwm_get_state_hw(pwm, state) + pwm_adjust_config(pwm);
    result += pwm_config(pwm, 1, 100) + netbsd_linux_pwm_enable(pwm);
    netbsd_linux_pwm_disable(pwm);
    result += PTR_ERR(pwm_get(dev, "panel"));
    result += PTR_ERR(devm_pwm_get(dev, "panel"));
    result += PTR_ERR(devm_fwnode_pwm_get(dev, fwnode, "panel"));
    pwm_put(pwm);
    chip = pwmchip_alloc(dev, 1, 0);
    result += PTR_ERR(chip) + PTR_ERR(devm_pwmchip_alloc(dev, 1, 0));
    result += pwmchip_add(chip) + pwmchip_remove(chip) + devm_pwmchip_add(dev, chip);
    pwmchip_put(chip);
    pwm_add_table(lookup, __arraycount(lookup));
    pwm_remove_table(lookup, __arraycount(lookup));
    /* Marker substituted outside the frozen source translator. */
    result += pwm_enable(native) + pwm_disable(native);
    return result + args.period;
}

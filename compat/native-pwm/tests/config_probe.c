#include <sys/param.h>
#include <linux/pwm.h>

int pwm_disabled_config_probe(void);
int
pwm_disabled_config_probe(void)
{
    return netbsd_linux_pwm_enable(NULL);
}

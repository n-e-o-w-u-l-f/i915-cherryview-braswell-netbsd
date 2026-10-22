/* HP-I915 0083 STAGED candidate, NOT deployed to NetBSD/src.
 * Integrate only after actual NetBSD native kernel build + wsdisplay provider.
 * Derived from NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6
 * and Linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab.
 */
#ifndef HP_I915_0083_BACKLIGHT_ABI_H
#define HP_I915_0083_BACKLIGHT_ABI_H

/* The original NetBSD linux/backlight.h includes only forward declarations;
 * this is an additive candidate overlay for CONFIG_BACKLIGHT_CLASS_DEVICE=1.
 */
#include <sys/types.h>
#include <sys/mutex.h>
#include <sys/condvar.h>
#include <stdbool.h>

struct device;
struct backlight_device;
enum backlight_type {
    BACKLIGHT_RAW = 1,
    BACKLIGHT_PLATFORM = 2,
    BACKLIGHT_FIRMWARE = 3
};

#define BACKLIGHT_POWER_ON 0
#define BACKLIGHT_POWER_OFF 4
#ifndef FB_BLANK_UNBLANK
#define FB_BLANK_UNBLANK BACKLIGHT_POWER_ON
#endif
#ifndef FB_BLANK_POWERDOWN
#define FB_BLANK_POWERDOWN BACKLIGHT_POWER_OFF
#endif

struct backlight_properties {
    int brightness;
    int max_brightness;
    int power;
    enum backlight_type type;
    unsigned int state;
};

struct backlight_ops {
    int (*update_status)(struct backlight_device *);
    int (*get_brightness)(struct backlight_device *);
};

struct backlight_device {
    struct backlight_properties props;
    const struct backlight_ops *ops;
    struct device *parent;
    void *devdata;
    char name[32];
    kmutex_t update_lock;
    kcondvar_t idle;
    unsigned int in_flight;
    bool closing;
};

#define backlight_device_register linux_backlight_device_register
#define backlight_device_unregister linux_backlight_device_unregister
#define backlight_update_status linux_backlight_update_status
#define backlight_enable linux_backlight_enable
#define backlight_disable linux_backlight_disable

struct backlight_device *backlight_device_register(const char *,
    struct device *, void *, const struct backlight_ops *,
    const struct backlight_properties *);
void backlight_device_unregister(struct backlight_device *);
int backlight_update_status(struct backlight_device *);
int backlight_enable(struct backlight_device *);
int backlight_disable(struct backlight_device *);
static inline void *
bl_get_data(const struct backlight_device *bd)
{
    return bd->devdata;
}
#endif

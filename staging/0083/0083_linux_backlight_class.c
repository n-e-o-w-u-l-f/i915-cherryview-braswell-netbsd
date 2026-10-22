/* HP-I915 0083 STAGED candidate, not NetBSD linked or booted.
 * Single-provider Linux backlight ABI compatibility prototype for NetBSD.
 * NO sysfs, wsdisplay or hardware exposure. Do not enable config yet.
 */
#include <sys/cdefs.h>
#include <sys/errno.h>
#include <sys/kmem.h>
#include <sys/mutex.h>
#include <sys/condvar.h>
#include <sys/once.h>
#include <sys/systm.h>
#include <linux/err.h>
#include "0083_linux_backlight_abi.h"

static kmutex_t bl_registry_lock;
static struct backlight_device *bl_registered;
static ONCE_DECL(bl_registry_once);

static int
bl_registry_init(void)
{
    mutex_init(&bl_registry_lock, MUTEX_DEFAULT, IPL_NONE);
    return 0;
}

struct backlight_device *
backlight_device_register(const char *name, struct device *parent,
    void *userdata, const struct backlight_ops *ops,
    const struct backlight_properties *props)
{
    struct backlight_device *bd;
    int error;

    if (name == NULL || name[0] == '\0' || strlen(name) >= sizeof(bd->name)
        || ops == NULL || ops->update_status == NULL || props == NULL
        || props->max_brightness <= 0 || props->brightness < 0
        || props->brightness > props->max_brightness
        || props->power < BACKLIGHT_POWER_ON
        || props->power > BACKLIGHT_POWER_OFF)
        return ERR_PTR(-EINVAL);
    error = RUN_ONCE(&bl_registry_once, bl_registry_init);
    if (error != 0)
        return ERR_PTR(-error);

    bd = kmem_zalloc(sizeof(*bd), KM_SLEEP);
    if (bd == NULL)
        return ERR_PTR(-ENOMEM);
    bd->parent = parent;
    bd->devdata = userdata;
    bd->ops = ops;
    bd->props = *props;
    (void)strlcpy(bd->name, name, sizeof(bd->name));
    mutex_init(&bd->update_lock, MUTEX_DEFAULT, IPL_NONE);
    cv_init(&bd->idle, "backlight");

    mutex_enter(&bl_registry_lock);
    /* Deliberate single owner: prevents duplicate intel_backlight.
     * Future multi-GPU support requires a keyed registry.
     */
    if (bl_registered != NULL) {
        mutex_exit(&bl_registry_lock);
        cv_destroy(&bd->idle);
        mutex_destroy(&bd->update_lock);
        kmem_free(bd, sizeof(*bd));
        return ERR_PTR(-EBUSY);
    }
    bl_registered = bd;
    mutex_exit(&bl_registry_lock);
    return bd;
}

/* Invoke the driver callback with no registry lock held. This avoids
 * registry -> DRM connection_mutex deadlock. update_lock serializes calls.
 * External callers must not retain bd past unregister completion.
 */
static int
bl_call_update(struct backlight_device *bd, int requested_power)
{
    int ret;

    if (bd == NULL)
        return 0;       /* Linux backlight_enable/disable(NULL) semantics */
    mutex_enter(&bl_registry_lock);
    if (bl_registered != bd || bd->closing) {
        mutex_exit(&bl_registry_lock);
        return -ENODEV;
    }
    bd->in_flight++;
    mutex_exit(&bl_registry_lock);

    mutex_enter(&bd->update_lock);
    if (requested_power >= 0)
        bd->props.power = requested_power;
    ret = bd->ops->update_status(bd);
    mutex_exit(&bd->update_lock);

    mutex_enter(&bl_registry_lock);
    KASSERT(bd->in_flight > 0);
    bd->in_flight--;
    if (bd->closing && bd->in_flight == 0)
        cv_broadcast(&bd->idle);
    mutex_exit(&bl_registry_lock);
    return ret;
}

int
backlight_update_status(struct backlight_device *bd)
{
    return bl_call_update(bd, -1);
}

int
backlight_enable(struct backlight_device *bd)
{
    return bl_call_update(bd, BACKLIGHT_POWER_ON);
}

int
backlight_disable(struct backlight_device *bd)
{
    return bl_call_update(bd, BACKLIGHT_POWER_OFF);
}

void
backlight_device_unregister(struct backlight_device *bd)
{
    if (bd == NULL)
        return;
    mutex_enter(&bl_registry_lock);
    if (bl_registered != bd) {
        /* A duplicate/stale pointer after free is always caller misuse. */
        mutex_exit(&bl_registry_lock);
        return;
    }
    bd->closing = true;
    while (bd->in_flight != 0)
        cv_wait(&bd->idle, &bl_registry_lock);
    bl_registered = NULL;
    mutex_exit(&bl_registry_lock);

    cv_destroy(&bd->idle);
    mutex_destroy(&bd->update_lock);
    kmem_free(bd, sizeof(*bd));
}

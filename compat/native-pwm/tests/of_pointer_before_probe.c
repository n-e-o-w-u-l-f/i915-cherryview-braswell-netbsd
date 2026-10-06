#include <sys/types.h>
#include <linux/types.h>
#include <linux/errno.h>
struct drm_display_mode;
#if defined(CONFIG_OF)
int of_get_drm_display_mode(struct device_node *np,
			    struct drm_display_mode *dmode, u32 *bus_flags,
			    int index);
int of_get_drm_panel_display_mode(struct device_node *np,
				  struct drm_display_mode *dmode, u32 *bus_flags);
#else
static inline int of_get_drm_display_mode(struct device_node *np,
					  struct drm_display_mode *dmode,
					  u32 *bus_flags, int index)
{
	return -EINVAL;
}

static inline int of_get_drm_panel_display_mode(struct device_node *np,
						struct drm_display_mode *dmode, u32 *bus_flags)
{
	return -EINVAL;
}
#endif

int of_pointer_signature_probe(struct device_node *, struct drm_display_mode *);
int
of_pointer_signature_probe(struct device_node *node, struct drm_display_mode *mode)
{
    int (*display)(struct device_node *, struct drm_display_mode *, u32 *, int) =
        of_get_drm_display_mode;
    int (*panel)(struct device_node *, struct drm_display_mode *, u32 *) =
        of_get_drm_panel_display_mode;
    u32 flags = 0;
    return display(node, mode, &flags, 0) + panel(node, mode, &flags);
}

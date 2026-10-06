#include <sys/param.h>
#include <drm/drm_modes.h>

int of_full_header_probe(struct device_node *, struct drm_display_mode *);
int
of_full_header_probe(struct device_node *node, struct drm_display_mode *mode)
{
    u32 flags = 0;
    return of_get_drm_display_mode(node, mode, &flags, 0);
}

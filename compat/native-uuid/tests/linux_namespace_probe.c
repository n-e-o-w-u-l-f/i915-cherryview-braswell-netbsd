#include <sys/param.h>
#include <sys/uuid.h>
#include <linux/uuid.h>

/* The translator must preserve this comment's uuid_t and uuid_equal text. */
static const char literal[] = "uuid_t uuid_equal uuid_gen";
static const uuid_t linux_uuid = UUID_INIT(0xa1b2c3d4, 0xe5f6, 0x0738,
    0x89, 0xab, 0xcd, 0xef, 0x01, 0x23, 0x45, 0x67);
int uuid_namespace_probe(uuid_t *);
int
uuid_namespace_probe(uuid_t *uuid)
{
    uuid_copy(uuid, &linux_uuid);
    return uuid_equal(uuid, &linux_uuid) && literal[0] == 'u';
}

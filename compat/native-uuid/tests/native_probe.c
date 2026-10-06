#include <sys/param.h>
#include <sys/uuid.h>
#include <linux/uuid.h>
#include <linux/acpi.h>

__CTASSERT(sizeof(guid_t) == 16);
__CTASSERT(sizeof(netbsd_linux_uuid_t) == 16);
__CTASSERT(__alignof__(guid_t) == 1);
__CTASSERT(__alignof__(netbsd_linux_uuid_t) == 1);
__CTASSERT(offsetof(guid_t, b) == 0);
__CTASSERT(offsetof(guid_t, guid_bytes) == 0);

static const guid_t native_guid = GUID_INIT(0xa1b2c3d4, 0xe5f6, 0x0738,
    0x89, 0xab, 0xcd, 0xef, 0x01, 0x23, 0x45, 0x67);
static const netbsd_linux_uuid_t linux_uuid = UUID_INIT(0xa1b2c3d4, 0xe5f6,
    0x0738, 0x89, 0xab, 0xcd, 0xef, 0x01, 0x23, 0x45, 0x67);

int uuid_candidate_probe(guid_t *, netbsd_linux_uuid_t *);
int
uuid_candidate_probe(guid_t *guid, netbsd_linux_uuid_t *uuid)
{
    guid_copy(guid, &native_guid);
    netbsd_linux_uuid_copy(uuid, &linux_uuid);
    return guid->b[0] + guid->guid_bytes[1] + uuid->b[0];
}

#include <sys/types.h>
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <uuid.h>

/* Native libuuid declarations/type deliberately precede the Linux API. */
#ifndef __KERNEL_RCSID
#define __KERNEL_RCSID(a,b)
#endif
static unsigned char last_entropy[16];
static unsigned entropy_calls;
static void *kern_cprng = &entropy_calls;
static size_t
cprng_strong(void *cprng, void *buf, size_t len, int flags)
{
    assert(cprng == kern_cprng && len == 16 && flags == 0);
    arc4random_buf(buf, len);
    memcpy(last_entropy, buf, len);
    entropy_calls++;
    return len;
}
#include "test_uuid_header.h"
#include "test_uuid_impl.inc"

_Static_assert(CHAR_BIT == 8, "8-bit byte ABI");
_Static_assert(sizeof(guid_t) == 16 && sizeof(netbsd_linux_uuid_t) == 16, "UUID size");
_Static_assert(_Alignof(guid_t) == 1 && _Alignof(netbsd_linux_uuid_t) == 1, "UUID alignment");
_Static_assert(offsetof(guid_t, b) == 0 && offsetof(guid_t, guid_bytes) == 0, "native alias offset");
_Static_assert(sizeof(uuid_t) == 16, "native libuuid type remains available");

static const unsigned char little[16] = {0xd4,0xc3,0xb2,0xa1,0xf6,0xe5,0x38,0x07,
    0x89,0xab,0xcd,0xef,0x01,0x23,0x45,0x67};
static const unsigned char big[16] = {0xa1,0xb2,0xc3,0xd4,0xe5,0xf6,0x07,0x38,
    0x89,0xab,0xcd,0xef,0x01,0x23,0x45,0x67};
static const char canonical[] = "a1b2c3d4-e5f6-0738-89ab-cdef01234567";
static const guid_t static_guid = GUID_INIT(0xa1b2c3d4,0xe5f6,0x0738,
    0x89,0xab,0xcd,0xef,0x01,0x23,0x45,0x67);
static const netbsd_linux_uuid_t static_uuid = UUID_INIT(0xa1b2c3d4,0xe5f6,0x0738,
    0x89,0xab,0xcd,0xef,0x01,0x23,0x45,0x67);

static void
test_abi_initializers_and_native_alias(void)
{
    guid_t guid = static_guid;
    uuid_t native;
    memset(&native, 0, sizeof(native));
    assert(memcmp(guid.b,little,16)==0);
    assert(memcmp(guid.guid_bytes,little,16)==0);
    assert(memcmp(static_uuid.b,big,16)==0);
    guid.b[5]=0x53;
    assert(guid.guid_bytes[5]==0x53);
    guid.guid_bytes[2]=0x91;
    assert(guid.b[2]==0x91);
    assert(sizeof(native)==16);
}

static void
test_copy_import_export_compare_and_null(void)
{
    guid_t guid,changed;
    netbsd_linux_uuid_t uuid,other;
    unsigned char bytes[18];
    guid_copy(&guid,&static_guid);
    netbsd_linux_uuid_copy(&uuid,&static_uuid);
    assert(guid_equal(&guid,&static_guid));
    assert(netbsd_linux_uuid_equal(&uuid,&static_uuid));
    for(unsigned i=0;i<16;i++) {
        changed=guid;other=uuid;
        changed.b[i]^=1;other.b[i]^=1;
        assert(!guid_equal(&changed,&guid));
        assert(!netbsd_linux_uuid_equal(&other,&uuid));
    }
    memset(bytes,0x55,sizeof(bytes));export_guid(bytes+1,&guid);
    assert(bytes[0]==0x55 && bytes[17]==0x55 && memcmp(bytes+1,little,16)==0);
    memset(&changed,0xff,sizeof(changed));import_guid(&changed,bytes+1);
    assert(guid_equal(&guid,&changed));
    memset(bytes,0x55,sizeof(bytes));netbsd_linux_export_uuid(bytes+1,&uuid);
    assert(bytes[0]==0x55 && bytes[17]==0x55 && memcmp(bytes+1,big,16)==0);
    memset(&other,0xff,sizeof(other));netbsd_linux_import_uuid(&other,bytes+1);
    assert(netbsd_linux_uuid_equal(&uuid,&other));
    assert(guid_is_null(&guid_null));
    assert(netbsd_linux_uuid_is_null(&netbsd_linux_uuid_null));
    assert(!guid_is_null(&guid) && !netbsd_linux_uuid_is_null(&uuid));
    for(unsigned i=0;i<16;i++) {
        assert(guid_null.b[i]==0 && netbsd_linux_uuid_null.b[i]==0);
    }
}

static void
test_parse_endian_and_case(void)
{
    const char upper[]="A1B2C3D4-E5F6-0738-89AB-CDEF01234567";
    const unsigned char expected_guid_index[16]={3,2,1,0,5,4,7,6,8,9,10,11,12,13,14,15};
    guid_t guid;netbsd_linux_uuid_t uuid;
    assert(uuid_is_valid(canonical) && uuid_is_valid(upper));
    assert(guid_parse(canonical,&guid)==0 && memcmp(guid.b,little,16)==0);
    assert(netbsd_linux_uuid_parse(canonical,&uuid)==0 && memcmp(uuid.b,big,16)==0);
    assert(guid_parse(upper,&guid)==0 && memcmp(guid.b,little,16)==0);
    assert(netbsd_linux_uuid_parse(upper,&uuid)==0 && memcmp(uuid.b,big,16)==0);
    for(unsigned i=0;i<16;i++) {
        assert(guid_index[i]==expected_guid_index[i]);
        assert(netbsd_linux_uuid_index[i]==i);
    }
}

static void
test_rejection_preserves_output_and_prefix_contract(void)
{
    char input[40];guid_t guid;netbsd_linux_uuid_t uuid;
    for(unsigned pos=0;pos<36;pos++) {
        memcpy(input,canonical,sizeof(canonical));input[pos]='#';
        memset(&guid,0x55,sizeof(guid));memset(&uuid,0x55,sizeof(uuid));
        assert(!uuid_is_valid(input));
        assert(guid_parse(input,&guid)==-EINVAL);
        assert(netbsd_linux_uuid_parse(input,&uuid)==-EINVAL);
        for(unsigned i=0;i<16;i++)assert(guid.b[i]==0x55 && uuid.b[i]==0x55);
        memcpy(input,canonical,sizeof(canonical));input[pos]='\0';
        assert(!uuid_is_valid(input));
    }
    for(unsigned value=0x80;value<0x100;value++) {
        memcpy(input,canonical,sizeof(canonical));input[0]=(char)value;
        assert(!uuid_is_valid(input));
    }
    memcpy(input,canonical,36);memcpy(input+36,"xyz",4);
    assert(uuid_is_valid(input));
    assert(guid_parse(input,&guid)==0 && memcmp(guid.b,little,16)==0);
    assert(netbsd_linux_uuid_parse(input,&uuid)==0 && memcmp(uuid.b,big,16)==0);
    /* Neither native nor frozen Linux validator requires a trailing NUL. */
    char fixed[36];memcpy(fixed,canonical,36);
    assert(uuid_is_valid(fixed));
    assert(guid_parse(fixed,&guid)==0 && netbsd_linux_uuid_parse(fixed,&uuid)==0);
}

static void
format_uuid(char text[37],const unsigned char bytes[16],const unsigned char index[16])
{
    static const char hex[]="0123456789abcdef";
    unsigned pos=0;
    for(unsigned i=0;i<16;i++) {
        if(i==4 || i==6 || i==8 || i==10)text[pos++]='-';
        unsigned byte=bytes[index[i]];
        text[pos++]=hex[byte>>4];text[pos++]=hex[byte&15];
    }
    assert(pos==36);text[pos]='\0';
}

static void
test_real_entropy_generation_bits_and_roundtrips(void)
{
    unsigned char uuid_bytes[16],guid_bytes[16],expect[16],previous[16]={0};
    char text[37];guid_t guid,parsed_guid;netbsd_linux_uuid_t uuid,parsed_uuid;
    for(unsigned round=0;round<256;round++) {
        netbsd_linux_generate_random_uuid(uuid_bytes);
        memcpy(expect,last_entropy,16);expect[6]=(expect[6]&15)|0x40;expect[8]=(expect[8]&63)|0x80;
        assert(memcmp(uuid_bytes,expect,16)==0);
        generate_random_guid(guid_bytes);
        memcpy(expect,last_entropy,16);expect[7]=(expect[7]&15)|0x40;expect[8]=(expect[8]&63)|0x80;
        assert(memcmp(guid_bytes,expect,16)==0);
        guid_gen(&guid);
        memcpy(expect,last_entropy,16);expect[7]=(expect[7]&15)|0x40;expect[8]=(expect[8]&63)|0x80;
        assert(memcmp(guid.b,expect,16)==0);
        netbsd_linux_uuid_gen(&uuid);
        memcpy(expect,last_entropy,16);expect[6]=(expect[6]&15)|0x40;expect[8]=(expect[8]&63)|0x80;
        assert(memcmp(uuid.b,expect,16)==0);
        assert(memcmp(uuid.b,previous,16)!=0);memcpy(previous,uuid.b,16);
        format_uuid(text,guid.b,guid_index);
        assert(guid_parse(text,&parsed_guid)==0 && guid_equal(&guid,&parsed_guid));
        format_uuid(text,uuid.b,netbsd_linux_uuid_index);
        assert(netbsd_linux_uuid_parse(text,&parsed_uuid)==0 && netbsd_linux_uuid_equal(&uuid,&parsed_uuid));
    }
    assert(entropy_calls==1024);
}

int
main(void)
{
#define RUN(fn) do { fn();printf("PASS %s\n",#fn); } while(0)
    RUN(test_abi_initializers_and_native_alias);
    RUN(test_copy_import_export_compare_and_null);
    RUN(test_parse_endian_and_case);
    RUN(test_rejection_preserves_output_and_prefix_contract);
    RUN(test_real_entropy_generation_bits_and_roundtrips);
    puts("PASS actual UUID algorithms; native kernel CPRNG execution/hard-IRQ parity OPEN");
    return 0;
}

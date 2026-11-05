/* SPDX-License-Identifier: BSD-2-Clause */
/* Delegated memory/errno backend only; actual native ABI compiled separately. */
#ifndef NATIVE_UIO_MODEL_H
#define NATIVE_UIO_MODEL_H
#ifdef NDEBUG
#undef NDEBUG
#endif
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
#include <unistd.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint64_t u64;
typedef int64_t loff_t;
#define MIN(a,b) ((a)<(b)?(a):(b))
#define ASSERT_SLEEPABLE() ((void)0)
#define panic(...) do { fprintf(stderr,__VA_ARGS__);fputc('\n',stderr);abort(); } while(0)
#ifndef __UNCONST
#define __UNCONST(p) ((void *)(uintptr_t)(const void *)(p))
#endif
#define atomic_load_relaxed(p) __atomic_load_n((p),__ATOMIC_RELAXED)
/* Exact03 Native flags; pinned Linux IOCB values live in production header. */
#define O_APPEND 0x00000008U
#define O_SYNC   0x00000080U
#define O_DSYNC  0x00010000U
#define O_DIRECT 0x00080000U
#define PAGE_SIZE 4096U
/* Mixed Native/Linux headers may own PAGE_MASK as Linux's page-base mask. */
#define PAGE_MASK (~((uintptr_t)PAGE_SIZE - 1))
/* Synthetic user handles have low addresses. Real C model buffers retain
 * their actual host addresses and explicit registered kernel ownership. */
#define VM_MAXUSER_ADDRESS ((uintptr_t)0x10000000)
struct vmspace { unsigned int identity; };
struct proc { struct vmspace *p_vmspace; };
struct linux_file { volatile unsigned int f_flags; };
static struct vmspace model_vm={1},other_vm={2};
static struct proc model_proc={&model_vm};
#define curproc (&model_proc)
#include <linux/uio_netbsd.h>
struct model_region { uintptr_t base;unsigned char *data;size_t size,readable,writable;bool vectors; };
static struct model_region user_region,kernel_regions[32];
static unsigned int kernel_region_count,copyin_calls,copyout_calls,kcopy_calls;
static void reset_regions(void)
{ memset(&user_region,0,sizeof(user_region));memset(kernel_regions,0,sizeof(kernel_regions));
  kernel_region_count=copyin_calls=copyout_calls=kcopy_calls=0;model_proc.p_vmspace=&model_vm; }
static void kernel_region(void *data,size_t size,size_t readable,size_t writable)
{ assert(kernel_region_count<32&&readable<=size&&writable<=size);
  kernel_regions[kernel_region_count++]=(struct model_region){(uintptr_t)data,data,size,readable,writable,false}; }
static void kernel_vectors(void *data,size_t size)
{ kernel_region(data,size,size,0);kernel_regions[kernel_region_count-1].vectors=true; }
static void user_buffer(uintptr_t base,void *data,size_t size,size_t readable,size_t writable)
{ assert(base<VM_MAXUSER_ADDRESS&&readable<=size&&writable<=size);
  user_region=(struct model_region){base,data,size,readable,writable,false}; }
static struct model_region *find_region(uintptr_t address,bool user)
{ if(user)return address>=user_region.base&&address-user_region.base<user_region.size?&user_region:NULL;
  for(unsigned int n=0;n<kernel_region_count;n++) {
    if(address>=kernel_regions[n].base&&address-kernel_regions[n].base<kernel_regions[n].size)
      return &kernel_regions[n];
  }return NULL; }
static int model_copy(const void *from,void *to,size_t bytes,bool from_user,bool to_user)
{ if(!bytes)return 0;struct model_region *s=find_region((uintptr_t)from,from_user),*d=find_region((uintptr_t)to,to_user);
  if(!s||!d)return EFAULT;
  size_t so=(uintptr_t)from-s->base,doff=(uintptr_t)to-d->base;
  size_t sr=so<s->readable?s->readable-so:0,dw=doff<d->writable?d->writable-doff:0;
  size_t n=MIN(bytes,MIN(sr,dw));if(n)memcpy(d->data+doff,s->data+so,n);
  return n==bytes?0:EFAULT; }
static int copyin(const void *from,void *to,size_t bytes)
{ assert(bytes<=PAGE_SIZE-((uintptr_t)from&(PAGE_SIZE-1)));copyin_calls++;return model_copy(from,to,bytes,true,false); }
static int copyout(const void *from,void *to,size_t bytes)
{ assert(bytes<=PAGE_SIZE-((uintptr_t)to&(PAGE_SIZE-1)));copyout_calls++;return model_copy(from,to,bytes,false,true); }
static int kcopy(const void *from,void *to,size_t bytes)
{ kcopy_calls++;
  /* Vector validation copies to a real local struct on the production C
   * stack, outside the explicit payload registrations. The source remains
   * kernel-owned; unlike a user source, such a read can be delegated here. */
  struct model_region *s=find_region((uintptr_t)from,false),*d=find_region((uintptr_t)to,false);
  if(s&&s->vectors&&!d&&bytes==sizeof(struct kvec)){size_t off=(uintptr_t)from-s->base;
    if(off<=s->readable&&bytes<=s->readable-off){memcpy(to,s->data+off,bytes);return 0;}}
  return model_copy(from,to,bytes,false,false); }
#endif

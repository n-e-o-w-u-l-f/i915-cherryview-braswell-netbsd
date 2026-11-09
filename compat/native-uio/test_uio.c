/* SPDX-License-Identifier: BSD-2-Clause */
#define NATIVE_UIO_TEST 1
#include "linux_uio.c"
static unsigned int cases;
static void pass(const char *name) { printf("PASS %u %s\n",++cases,name);fflush(stdout); }
static void test_kiocb_flags(void)
{ struct linux_file file={O_APPEND|O_SYNC|O_DSYNC|O_DIRECT};struct kiocb iocb;
  memset(&iocb,0xff,sizeof(iocb));init_sync_kiocb(&iocb,&file);
  assert(iocb.ki_filp==&file&&iocb.ki_flags==(IOCB_APPEND|IOCB_SYNC|IOCB_DSYNC|IOCB_DIRECT));
  assert(iocb.ki_pos==0&&is_sync_kiocb(&iocb)&&iocb.private==NULL&&iocb.ki_ioprio==0&&iocb.ki_waitq==NULL);
  file.f_flags=O_DSYNC;init_sync_kiocb(&iocb,&file);assert(iocb.ki_flags==IOCB_DSYNC);
  pass("actual-native-flags-initialized-synchronous-request"); }
static void test_ubuf_read(void)
{ unsigned char user[16]="0123456789abcde",out[16]={0};struct iov_iter iter;reset_regions();
  user_buffer(0x1000,user,sizeof(user),16,16);kernel_region(out,sizeof(out),16,16);
  iov_iter_ubuf(&iter,ITER_SOURCE,(void *)0x1000,16);
  assert(copy_from_iter(out,40,&iter)==16&&memcmp(user,out,16)==0&&iter.count==0&&iter.iov_offset==16);
  assert(copy_from_iter(NULL,0,&iter)==0);pass("ubuf-source-count-clamp-and-zero"); }
static void test_ubuf_write(void)
{ unsigned char user[16]={0},in[16]="0123456789abcde";struct iov_iter iter;reset_regions();
  user_buffer(0x1000,user,16,16,16);kernel_region(in,16,16,0);
  iov_iter_ubuf(&iter,ITER_DEST,(void *)0x1000,16);
  assert(copy_to_iter(in,7,&iter)==7&&iter.count==9&&iter.iov_offset==7&&memcmp(user,in,7)==0);
  assert(copy_from_iter(in,1,&iter)==0&&iter.count==9);pass("ubuf-destination-and-direction-rejection"); }
static void test_fault_prefix(void)
{ unsigned char user[16]="0123456789abcde",out[16]={0};struct iov_iter iter;reset_regions();
  user_buffer(0x1000,user,16,7,16);kernel_region(out,16,16,16);
  iov_iter_ubuf(&iter,ITER_SOURCE,(void *)0x1000,16);
  assert(copy_from_iter(out,16,&iter)==7&&iter.count==9&&iter.iov_offset==7);
  assert(copyin_calls>1&&memcmp(user,out,7)==0);
  iov_iter_revert(&iter,7);assert(iter.count==16&&iter.iov_offset==0);
  assert(!copy_from_iter_full(out,16,&iter)&&iter.count==16&&iter.iov_offset==0);
  pass("fault-prefix-confirmed-bytewise-full-copy-revert"); }
static void test_page_boundary_fault(void)
{ unsigned char user[32],out[32]={0};struct iov_iter iter;memset(user,0x5a,32);reset_regions();
  user_buffer(0x1ff0,user,32,20,32);kernel_region(out,32,32,32);
  iov_iter_ubuf(&iter,ITER_SOURCE,(void *)0x1ff0,32);
  assert(copy_from_iter(out,32,&iter)==20&&iter.count==12&&iter.iov_offset==20);
  assert(memcmp(user,out,20)==0);pass("cross-page-user-fault-residual"); }
static void test_partial_copyout(void)
{ unsigned char user[16]={0},in[16]="0123456789abcde";struct iov_iter iter;reset_regions();
  user_buffer(0x1000,user,16,16,5);kernel_region(in,16,16,0);
  iov_iter_ubuf(&iter,ITER_DEST,(void *)0x1000,16);
  assert(copy_to_iter(in,16,&iter)==5&&iter.count==11&&memcmp(user,in,5)==0&&copyout_calls>1);
  pass("copyout-fault-prefix-only-confirmed-progress"); }
static void test_owner_and_address_rejection(void)
{ unsigned char out[16]={0},user[16]={0};struct iov_iter iter;reset_regions();
  user_buffer(0x1000,user,16,16,16);kernel_region(out,16,16,16);
  iov_iter_ubuf(&iter,ITER_SOURCE,(void *)0x1000,16);model_proc.p_vmspace=&other_vm;
  assert(copy_from_iter(out,16,&iter)==0&&copyin_calls==0&&iter.count==16);
  model_proc.p_vmspace=&model_vm;iov_iter_ubuf(&iter,ITER_SOURCE,out,16);
  assert(copy_from_iter(out,16,&iter)==0&&copyin_calls==0);
  iov_iter_ubuf(&iter,ITER_SOURCE,(void *)(UINTPTR_MAX-3),16);
  assert(copy_from_iter(out,16,&iter)==0&&copyin_calls==0);
  iov_iter_ubuf(&iter,ITER_SOURCE,(void *)0x1000,16);iter.nofault=true;
  assert(copy_from_iter(out,16,&iter)==0&&iter.count==16);pass("foreign-vmspace-overflow-kernel-as-user-nofault-refused"); }
static void test_kvec_segments(void)
{ unsigned char a[3]="ab",b[5]="cdef",out[8]={0};struct kvec vectors[4]={{a,0},{a,3},{b,0},{b,5}};
  struct iov_iter iter;reset_regions();kernel_region(a,3,3,3);kernel_region(b,5,5,5);
  kernel_region(out,8,8,8);kernel_vectors(vectors,sizeof(vectors));
  iov_iter_kvec(&iter,ITER_SOURCE,vectors,4,7);assert(copy_from_iter(out,7,&iter)==7);
  assert(!memcmp(out,a,3)&&!memcmp(out+3,b,4)&&iter.count==0&&iter.iov_offset==4&&iter.nr_segs==1);
  iov_iter_revert(&iter,4);assert(iter.count==4&&iter.iov_offset==0&&iter.nr_segs==1);
  iov_iter_advance(&iter,100);assert(iter.count==0&&iter.netbsd_consumed==7);
  pass("kernel-vectors-empty-segments-advance-revert"); }
static void test_kvec_dest_and_fault(void)
{ unsigned char in[8]="abcdefg",out[8]={0};struct kvec vector={out,8};struct iov_iter iter;
  reset_regions();kernel_region(in,8,8,0);kernel_region(out,8,8,5);kernel_vectors(&vector,sizeof(vector));
  iov_iter_kvec(&iter,ITER_DEST,&vector,1,8);assert(copy_to_iter(in,8,&iter)==5);
  assert(iter.count==3&&iter.iov_offset==5&&!memcmp(in,out,5));pass("native-kcopy-protection-fault-prefix"); }
static void test_kvec_user_relabel(void)
{ unsigned char out[8]={0};struct kvec vector={(void *)0x1000,8};struct iov_iter iter;reset_regions();
  kernel_region(out,8,8,8);kernel_vectors(&vector,sizeof(vector));
  iov_iter_kvec(&iter,ITER_SOURCE,&vector,1,8);unsigned int before=kcopy_calls;
  assert(copy_from_iter(out,8,&iter)==0&&iter.count==8&&kcopy_calls==before);
  pass("kernel-vector-cannot-relabel-user-address"); }
static void test_truncate(void)
{ struct iov_iter iter;reset_regions();iov_iter_ubuf(&iter,ITER_SOURCE,(void *)0x1000,20);
  iov_iter_advance(&iter,4);iov_iter_truncate(&iter,7);assert(iter.count==7);
  iov_iter_truncate(&iter,UINT64_MAX);assert(iter.count==7);
  iov_iter_reexpand(&iter,16);iov_iter_revert(&iter,4);assert(iter.count==20&&iter.iov_offset==0);
  pass("truncate-reexpand-preserves-original-owner-bounds"); }
static void test_empty_vectors(void)
{ struct iov_iter iter;reset_regions();iov_iter_kvec(&iter,ITER_DEST,NULL,0,0);
  iov_iter_advance(&iter,5);iov_iter_revert(&iter,0);assert(iter.kvec==NULL&&iter.count==0&&iter.nr_segs==0);
  assert(copy_to_iter(NULL,1,&iter)==0);pass("empty-kernel-vector-no-null-pointer-arithmetic"); }
static void fatal_case(const char *name)
{ struct iov_iter iter;struct kvec vector={(void *)0x1000,1};reset_regions();
  if(!strcmp(name,"bad-direction"))iov_iter_ubuf(&iter,3,NULL,0);
  else if(!strcmp(name,"revert-before-start")){iov_iter_ubuf(&iter,ITER_SOURCE,(void *)0x1000,1);iov_iter_revert(&iter,1);}
  else if(!strcmp(name,"expand-past-owner")){iov_iter_ubuf(&iter,ITER_SOURCE,(void *)0x1000,1);iov_iter_reexpand(&iter,2);}
  else if(!strcmp(name,"short-vectors")){kernel_vectors(&vector,sizeof(vector));iov_iter_kvec(&iter,ITER_SOURCE,&vector,1,2);}
  else if(!strcmp(name,"user-vector-array"))iov_iter_kvec(&iter,ITER_SOURCE,(void *)0x1000,1,1);
  else if(!strcmp(name,"missing-file")){struct kiocb iocb;init_sync_kiocb(&iocb,NULL);}
  else panic("unknown fatal case");
  panic("fatal control unexpectedly returned"); }
int main(int argc,char **argv)
{ alarm(30);if(argc==2){fatal_case(argv[1]);return 99;}assert(argc==1);
  test_kiocb_flags();test_ubuf_read();test_ubuf_write();test_fault_prefix();test_page_boundary_fault();
  test_partial_copyout();test_owner_and_address_rejection();test_kvec_segments();test_kvec_dest_and_fault();
  test_kvec_user_relabel();test_truncate();test_empty_vectors();assert(cases==12);
  puts("NATIVE_UIO_MODEL_PASS cases=12 native_kernel_acceptance=OPEN");return 0; }

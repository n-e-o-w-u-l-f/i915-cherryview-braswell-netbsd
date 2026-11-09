/* SPDX-License-Identifier: BSD-2-Clause */
#include "test_model.h"
#include <linux/file_netbsd.h>
#include <linux/poll_netbsd.h>
/* Exact unchanged helper added by the Native0038 patch, extracted and hashed
 * by the runner. Native fd_getfile/fd_putfile are the explicit delegates. */
#include "fd_get_linux_file.inc"
#include "linux_fd.c"
#include "linux_poll.c"
#include "linux_file.c"

static unsigned int cases,release_calls,inode_gets,inode_puts,driver_poll_calls,event_size_calls;
static unsigned int trace[64],trace_count;
enum { TRACE_RELEASE=1,TRACE_IPUT,TRACE_SHELL,TRACE_MODULE };
static void event(unsigned int code) { assert(trace_count<64);trace[trace_count++]=code; }
static void pass(const char *name) { printf("PASS %u %s\n",++cases,name);fflush(stdout); }
static void model_shell_free_event(void) { event(TRACE_SHELL); }
static void module_rele(struct module *owner)
{ assert(!model_irq&&!model_rcu_callback&&owner&&owner->refs);owner->refs--;owner->releases++;
  assert(model_shell_freed&&file_live!=0);event(TRACE_MODULE); }
void ihold(struct linux_inode *inode) { assert(inode&&inode->netbsd_refs);inode->netbsd_refs++;inode_gets++; }
void iput(struct linux_inode *inode) { assert(inode&&inode->netbsd_refs);inode->netbsd_refs--;inode_puts++;event(TRACE_IPUT); }
const struct fileops linux_file_native_ops = { .fo_linux_file=linux_file_native_view };

static void close_native_slot(unsigned int fd)
{ struct model_fd_slot *slot=model_fd_table.slots+fd;file_t *native=slot->native;
  assert(native&&slot->installed);slot->installed=false;
  linux_file_fd_detach(native->f_data);fput(native->f_data);free(native);memset(slot,0,sizeof(*slot)); }
static void fd_putfile(unsigned int fd)
{ assert(fd<16&&model_fd_table.slots[fd].borrowed);
  if(model_close_on_borrow_drop){assert(file_count((struct linux_file *)model_fd_table.slots[fd].native->f_data)>=2);
    model_fd_table.slots[fd].borrowed--;model_fd_drops++;close_native_slot(fd);model_close_on_borrow_drop=false;}
  else{model_fd_table.slots[fd].borrowed--;model_fd_drops++;} }
static int driver_release(struct linux_inode *inode,struct linux_file *file)
{ assert(inode==file->f_inode&&!model_irq&&file->netbsd_poll==NULL);release_calls++;event(TRACE_RELEASE);return -EIO; }
static struct module callback_module;
static struct file_operations operations={.owner=&callback_module,.release=driver_release};
static struct linux_inode inode;
static struct linux_file *new_file(const struct file_operations *ops)
{ struct linux_file *file=linux_file_alloc(&inode,ops,NULL,O_RDWR);assert(file&&!IS_ERR(file));
  file->f_mode|=FMODE_OPENED;return file; }
static void retire_queued_file(struct linux_file *file)
{ model_watch_shell=file;model_shell_freed=false;unsigned int before=callback_module.releases;
  assert(file_pending==1&&file_live==1&&file_release_queue->count==1);
  assert(linux_file_system_fini()==EBUSY);
  model_run_work(file_release_queue);
  assert(file_pending==0&&file_live==1&&model_rcu_pending==1&&!model_shell_freed);
  assert(callback_module.refs==1&&callback_module.releases==before);
  assert(linux_file_system_fini()==EBUSY);
  rcu_read_lock();assert(model_run_rcu()==0&&!model_shell_freed);rcu_read_unlock();
  assert(model_run_rcu()==1&&file_release_queue->count==1&&!model_shell_freed);
  assert(callback_module.refs==1&&file_live==1);model_run_work(file_release_queue);
  assert(model_shell_freed&&callback_module.refs==0&&callback_module.releases==before+1&&file_live==0);
  model_watch_shell=NULL; }
static void last_irq_put(struct linux_file *file)
{ unsigned int allocated=model_alloc_count,freed=model_free_count;
  model_irq=true;fput(file);model_irq=false;
  assert(model_alloc_count==allocated&&model_free_count==freed); }

struct ref_race { file_ref_t ref;pthread_barrier_t barrier;volatile unsigned int finals; };
static void *ref_getter(void *v)
{ struct ref_race *race=v;int e=pthread_barrier_wait(&race->barrier);assert(e==0||e==PTHREAD_BARRIER_SERIAL_THREAD);
  if(file_ref_get(&race->ref)&&file_ref_put(&race->ref))atomic_inc_uint(&race->finals);
  return NULL; }
static void test_encoded_refs(void)
{ file_ref_t ref;file_ref_init(&ref,1);assert(file_ref_read(&ref)==1&&__file_ref_read_raw(&ref)==FILE_REF_ONEREF);
  assert(file_ref_get(&ref)&&file_ref_read(&ref)==2);assert(!file_ref_put(&ref)&&file_ref_put(&ref));
  assert(__file_ref_read_raw(&ref)==FILE_REF_DEAD&&file_ref_read(&ref)==0&&!file_ref_get(&ref));
  atomic_store_relaxed(&ref.refcnt,FILE_REF_MAXREF);assert(!file_ref_get(&ref));
  assert(__file_ref_read_raw(&ref)==FILE_REF_SATURATED&&!file_ref_put(&ref));
  pass("encoded-last-reference-no-resurrection-saturation");
  for(unsigned int i=0;i<200;i++){struct ref_race race;pthread_t thread;file_ref_init(&race.ref,1);race.finals=0;
    assert(pthread_barrier_init(&race.barrier,NULL,2)==0);assert(pthread_create(&thread,NULL,ref_getter,&race)==0);
    int e=pthread_barrier_wait(&race.barrier);assert(e==0||e==PTHREAD_BARRIER_SERIAL_THREAD);
    if(file_ref_put(&race.ref))atomic_inc_uint(&race.finals);
    assert(pthread_join(thread,NULL)==0&&race.finals==1&&!file_ref_get(&race.ref));
    assert(pthread_barrier_destroy(&race.barrier)==0);}
  pass("concurrent-get-last-put-exactly-one-final-owner"); }
static void test_empty_and_reservations(void)
{ unsigned int destroyed=model_queue_destroyed;
  model_anon_busy=true;assert(linux_file_system_fini()==EBUSY&&file_state==FILE_SYSTEM_OPEN);
  assert(model_queue_destroyed==destroyed);model_anon_busy=false;
  assert(fdget(15).word==0&&fdget_raw(UINT_MAX).word==0&&fdget_pos(15).word==0);
  assert(fd_empty(fdget(15)));fdput(fdget(15));fdput_pos(fdget_pos(15));
  pass("invalid-descriptors-are-exact-empty-with-no-drop-flags");
  assert(get_unused_fd_flags(O_APPEND)==-EINVAL&&file_live==0);
  model_fail_alloc_after=0;assert(get_unused_fd_flags(0)==-ENOMEM&&file_live==0);model_fail_alloc_after=-1;
  model_fd_alloc_error=EMFILE;assert(get_unused_fd_flags(0)==-EMFILE&&file_live==0);model_fd_alloc_error=0;
  int fd=get_unused_fd_flags(O_CLOEXEC);assert(fd>=0&&linux_fd_system_busy()&&file_live==1);
  assert(model_fd_table.slots[fd].reserved&&model_fd_table.slots[fd].exclose);
  put_unused_fd((unsigned int)fd);assert(!linux_fd_system_busy()&&file_live==0&&model_fd_aborts==1);
  pass("reservation-construction-errors-abort-and-exclose"); }
static void test_native_borrow_transfer(void)
{ struct linux_file *file=new_file(&operations);unsigned int releases=release_calls;
  int fd=get_unused_fd_flags(0);assert(fd>=0);fd_install((unsigned int)fd,file);
  assert(file_count(file)==1&&!linux_fd_system_busy()&&file_live==1&&model_fd_affixes==1);
  assert(file->netbsd_poll->descriptors==1);model_close_on_borrow_drop=true;
  struct linux_file *owned=fget_raw((unsigned int)fd);
  assert(owned==file&&file_count(owned)==1&&file_pending==0&&model_fd_borrows==1&&model_fd_drops==1);
  assert(file->netbsd_poll->descriptors==0&&fd_empty(fdget_raw((unsigned int)fd)));
  pass("owned-linux-reference-before-native-borrow-drop-close");
  trace_count=0;last_irq_put(owned);assert(!file_ref_get(&file->f_ref));
  struct linux_file *pointer=file;assert(get_file_active(&pointer)==NULL);
  retire_queued_file(file);assert(release_calls==releases+1&&trace_count==4);
  assert(trace[0]==TRACE_RELEASE&&trace[1]==TRACE_IPUT&&trace[2]==TRACE_SHELL&&trace[3]==TRACE_MODULE);
  pass("irq-final-put-release-rcu-shell-module-ordered-retirement"); }
static void test_live_lookup_and_position(void)
{ struct linux_file *file=new_file(&operations),*pointer=file;
  rcu_read_lock();assert(get_file_rcu(&pointer)==file&&file_count(file)==2);rcu_read_unlock();fput(file);
  assert(get_file_active(&pointer)==file&&file_count(file)==2);fput(file);
  int fd=get_unused_fd_flags(0);assert(fd>=0);fd_install((unsigned int)fd,file);file->f_mode|=FMODE_ATOMIC_POS;
  struct fd reference=fdget_pos((unsigned int)fd);assert(fd_file(reference)==file&&
    (reference.word&(FDPUT_FPUT|FDPUT_POS_UNLOCK))==(FDPUT_FPUT|FDPUT_POS_UNLOCK));
  assert(mutex_owned(&file->f_pos_lock.native)&&file_count(file)==2);fdput_pos(reference);
  assert(!mutex_owned(&file->f_pos_lock.native)&&file_count(file)==1);
  close_native_slot((unsigned int)fd);retire_queued_file(file);
  pass("live-rcu-lookups-and-position-reference-unlock-balance"); }
static wait_queue_head_t driver_wait;
static __poll_t driver_ready;
static __poll_t driver_poll(struct linux_file *file,struct poll_table_struct *table)
{ driver_poll_calls++;poll_wait(file,&driver_wait,table);return driver_ready; }
static size_t event_size(struct linux_file *file) { (void)file;event_size_calls++;return 17; }
static void driver_wake(__poll_t mask)
{ unsigned long flags;spin_lock_irqsave(&driver_wait.lock,flags);
  struct list_head *node=driver_wait.head.next;
  while(node!=&driver_wait.head){wait_queue_entry_t *wait=container_of(node,wait_queue_entry_t,entry);
    node=node->next;assert(wait->func(wait,~0U,0,(void *)(uintptr_t)mask)==1);}
  spin_unlock_irqrestore(&driver_wait.lock,flags); }
static void test_poll_rescan_and_native_events(void)
{ struct file_operations poll_ops=operations;poll_ops.poll=driver_poll;struct linux_file *file=new_file(&poll_ops);
  struct file native={.f_data=file};spin_lock_init(&driver_wait.lock);INIT_LIST_HEAD(&driver_wait.head);driver_ready=0;
  assert(linux_file_native_poll(&native,POLLIN)==0);
  assert(file->netbsd_poll->sel.resets==1&&file->netbsd_poll->sel.last_events==0&&file->netbsd_poll->hints==0);
  unsigned int allocated=model_alloc_count;assert(linux_file_native_poll(&native,POLLIN)==0);
  assert(model_alloc_count==allocated&&file->netbsd_poll->sel.resets==1);
  pass("new-registration-zero-event-native-rescan-without-fake-readiness");
  struct knote kn={.kn_filter=EVFILT_WRITE};file->netbsd_event_size=event_size;
  assert(linux_file_native_kqfilter(&native,&kn)==0&&file_count(file)==2);
  unsigned int queries=driver_poll_calls,sizes=event_size_calls;
  driver_wake(EPOLLWRNORM);assert(file->netbsd_poll->sel.last_events==POLLWRNORM);
  assert(driver_poll_calls==queries&&event_size_calls==sizes&&!(kn.kn_flags&EV_EOF));
  assert((__poll_t)POLLWRNORM!=EPOLLWRNORM);kn.kn_fop->f_detach(&kn);assert(file_count(file)==1);
  pass("wakeup-native-bit-translation-note-submit-never-calls-driver");
  driver_wake(POLLFREE);assert(list_empty(&driver_wait.head));spin_lock_destroy(&driver_wait.lock);
  last_irq_put(file);retire_queued_file(file);pass("pollfree-clears-head-before-owned-registration-release"); }
static void test_poll_allocation_failure(void)
{ struct file_operations poll_ops=operations;poll_ops.poll=driver_poll;struct linux_file *file=new_file(&poll_ops);
  struct file native={.f_data=file};spin_lock_init(&driver_wait.lock);INIT_LIST_HEAD(&driver_wait.head);driver_ready=0;
  model_fail_alloc_after=0;int result=linux_file_native_poll(&native,POLLIN);model_fail_alloc_after=-1;
  assert(result==POLLERR&&!(result&POLLHUP)&&file->netbsd_poll->registrations==NULL);
  assert(linux_file_native_poll(&native,POLLIN)==0);last_irq_put(file);retire_queued_file(file);
  assert(list_empty(&driver_wait.head));spin_lock_destroy(&driver_wait.lock);
  pass("poll-registration-allocation-failure-is-error-without-fake-eof"); }
static void fatal_case(const char *name)
{ file_ref_t reference;file_ref_init(&reference,1);
  if(!strcmp(name,"ref-underflow")){assert(file_ref_put(&reference));(void)file_ref_put(&reference);}
  else if(!strcmp(name,"ref-resurrect")){assert(file_ref_put(&reference));file_ref_inc(&reference);}
  else if(!strcmp(name,"ref-zero-init"))file_ref_init(&reference,0);
  else {assert(linux_file_system_init()==0);inode.netbsd_refs=1;inode.i_mapping=&inode.i_data;
    if(!strcmp(name,"missing-reservation")){struct linux_file *file=new_file(&operations);fd_install(0,file);}
    else if(!strcmp(name,"wrong-fd-table")){int fd=get_unused_fd_flags(0);assert(fd>=0);filedesc_t other={0};
      model_lwp.l_fd=&other;put_unused_fd((unsigned int)fd);}
    else if(!strcmp(name,"invalid-install"))fd_install(0,NULL);
    else panic("unknown fatal case");}
  panic("fatal case unexpectedly returned"); }
int main(int argc,char **argv)
{ alarm(45);if(argc==2){fatal_case(argv[1]);return 99;}assert(argc==1);
  test_encoded_refs();assert(linux_file_system_init()==0);inode.netbsd_refs=1;inode.i_mapping=&inode.i_data;
  test_empty_and_reservations();test_native_borrow_transfer();test_live_lookup_and_position();
  test_poll_rescan_and_native_events();test_poll_allocation_failure();
  assert(file_live==0&&file_pending==0&&model_rcu_pending==0&&model_allocations==NULL);
  assert(model_alloc_count==model_free_count&&inode_gets==inode_puts&&inode.netbsd_refs==1&&model_credential.refs==1);
  assert(linux_file_system_fini()==0&&model_queue_created==model_queue_destroyed&&model_task_live==0);
  assert(cases==11);puts("NATIVE_FILE_MODEL_PASS cases=11 native_kernel_acceptance=OPEN");return 0; }

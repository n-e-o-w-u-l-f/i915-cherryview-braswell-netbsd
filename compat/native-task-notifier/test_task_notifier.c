/* SPDX-License-Identifier: BSD-2-Clause */
/* Includes the exact generated production owner; model boundaries explicit. */
#include "test_model.h"
#include "linux_task.c"
#include "task_entry_preallocated.inc"
#include "task_quiesce_retained.inc"

static unsigned int passed;
static void pass(const char *name) { printf("PASS %u %s\n",++passed,name);fflush(stdout); }
int linux_kthread_wake_locked(struct task_struct *task)
{ assert(mutex_owned(&task->lt_lock.rsl_lock));return 0; }
static void state(struct task_struct *task,unsigned int value)
{ unsigned long f;raw_spin_lock_irqsave(&task->lt_lock,f);task->__state=value;
  raw_spin_unlock_irqrestore(&task->lt_lock,f); }
static void drain(void)
{ unsigned long f;raw_spin_lock_irqsave(&task_system_lock,f);
  workqueue_enqueue(task_notify_queue,&task_notify_barrier,NULL);
  raw_spin_unlock_irqrestore(&task_system_lock,f);
  workqueue_wait(task_notify_queue,&task_notify_barrier); }
static void irq_put(struct task_struct *task)
{ test_irq=true;put_task_struct(task);test_irq=false; }
static void init_lwp(void)
{ test_proc.p_pid=getpid();strlcpy(test_proc.p_comm,"notifier-model",sizeof(test_proc.p_comm));
  test_lwp.l_proc=curproc;mutex_init(&test_lwp.lock,0,0); }

static void test_init_failure(void)
{ test_wq_fail=true;assert(linux_task_system_init()==EAGAIN);
  assert(task_key==(specificdata_key_t)-1&&task_notify_queue==NULL&&task_count==0);
  assert(test_keys==1&&test_key_deletes==1&&test_allocs==0&&test_frees==0);
  assert(test_wq_creates==1&&test_wq_destroys==0);test_wq_fail=false;
  assert(linux_task_system_init()==0);pass("fallible-global-init-unwind"); }
static void test_single_queue_and_deferred_free(void)
{ struct task_struct *tasks[32];unsigned int before=test_frees;
  model_pause(task_notify_queue,true);
  for(unsigned int i=0;i<32;i++){tasks[i]=linux_task_alloc();assert(tasks[i]!=NULL);}
  assert(task_count==32&&test_wq_creates==2);
  for(unsigned int i=0;i<32;i++)irq_put(tasks[i]);
  assert(test_frees==before&&task_count==32&&linux_task_system_busy());
  assert(linux_task_system_quiesce()==EBUSY&&task_system_state==TASK_SYSTEM_OPEN);
  model_pause(task_notify_queue,false);drain();
  assert(test_frees==before+32&&task_count==0&&!linux_task_system_busy());
  pass("one-queue-no-irq-allocation-charged-exact-free"); }
static void test_pending_coalesces(void)
{ struct task_struct *task=linux_task_alloc();unsigned int queued=test_enqueues,signaled=test_signals;
  model_pause(task_notify_queue,true);
  for(unsigned int i=0;i<100;i++){state(task,TASK_UNINTERRUPTIBLE);assert(wake_up_process(task)==1);}
  assert(test_enqueues==queued+1&&task->lt_notify_pending);
  model_pause(task_notify_queue,false);drain();
  assert(test_signals==signaled+1&&!task->lt_notify_pending);
  irq_put(task);drain();assert(task_count==0);pass("hundred-pending-wakes-one-embedded-work"); }
static struct task_struct *hook_task;
static void wake_during_signal(void)
{ test_signal_hook=NULL;state(hook_task,TASK_UNINTERRUPTIBLE);assert(wake_up_process(hook_task)==1); }
static void test_running_coalesces(void)
{ struct task_struct *task=linux_task_alloc();unsigned int signals=test_signals,queued=test_enqueues;
  hook_task=task;test_signal_hook=wake_during_signal;
  state(task,TASK_UNINTERRUPTIBLE);assert(wake_up_process(task)==1);drain();
  /* One task work plus drain marker. The second wake races the running
   * callback and must cause its condition recheck/signal before pending clears. */
  assert(test_signals==signals+2&&test_enqueues==queued+2&&!task->lt_notify_pending);
  irq_put(task);drain();pass("wake-during-running-callback-rechecked"); }
static void drop_during_signal(void)
{ test_signal_hook=NULL;irq_put(hook_task); }
static void test_last_put_running(void)
{ struct task_struct *task=linux_task_alloc();unsigned int frees=test_frees,queued=test_enqueues;
  hook_task=task;test_signal_hook=drop_during_signal;
  state(task,TASK_UNINTERRUPTIBLE);assert(wake_up_process(task)==1);drain();
  assert(test_frees==frees+1&&task_count==0&&test_enqueues==queued+2);
  pass("last-put-during-notify-single-final-destruction"); }

struct clone_args { struct task_struct *parent;pthread_mutex_t guard; };
static void *clone_worker(void *v)
{ struct clone_args *args=v;
  for(unsigned int i=0;i<50;i++){
    assert(pthread_mutex_lock(&args->guard)==0);
    struct task_struct *child=linux_task_alloc_owner_wait(args->parent);
    assert(pthread_mutex_unlock(&args->guard)==0);
    assert(child&&child->lt_refs==1&&child->lt_lwp==NULL&&!child->lt_exited);
    get_task_struct(child);put_task_struct(child);irq_put(child);
  }return NULL; }
static void test_closed_owner_clones(void)
{ struct clone_args args={.parent=linux_task_alloc()};pthread_t threads[4];unsigned long f;
  assert(args.parent!=NULL);assert(pthread_mutex_init(&args.guard,NULL)==0);
  /* Explicit fixture of already-closed subsystem admission. A real retained
   * LWP close is exercised independently below via the production API. */
  raw_spin_lock_irqsave(&task_system_lock,f);task_system_state=TASK_SYSTEM_QUIESCED;
  raw_spin_unlock_irqrestore(&task_system_lock,f);
  assert(linux_task_alloc()==NULL);
  for(unsigned int i=0;i<4;i++)assert(pthread_create(&threads[i],NULL,clone_worker,&args)==0);
  for(unsigned int i=0;i<4;i++)assert(pthread_join(threads[i],NULL)==0);
  assert(args.parent->lt_refs==1&&args.parent->lt_lwp==NULL);
  drain();assert(task_count==1&&linux_task_system_fini()==EBUSY);
  irq_put(args.parent);assert(linux_task_system_fini()==0);
  assert(task_notify_queue==NULL&&task_count==0&&test_allocs==test_frees);
  assert(pthread_mutex_destroy(&args.guard)==0);
  pass("four-thread-internal-clones-while-external-admission-closed"); }
static void test_preallocated_retained_owner(void)
{ struct task_struct *spare,*entry=NULL,*retained;unsigned int frees=test_frees;
  assert(linux_task_system_init()==0);init_lwp();spare=linux_task_alloc();assert(spare);
  linux_task_entry_enter_preallocated(&entry,&spare);
  assert(spare==NULL&&entry!=NULL&&entry->lt_refs==2);retained=entry;
  linux_task_entry_leave(&entry);assert(entry==NULL&&retained->lt_refs==1);
  assert(linux_task_system_quiesce_retained(retained)==0);
  assert(linux_task_alloc()==NULL);
  /* Native LWP exit clears TLS before the registered destructor callback. */
  lwp_setspecific(task_key,NULL);linux_task_owner_exit(retained);
  assert(linux_task_system_fini()==0&&test_frees==frees+1&&task_count==0);
  mutex_destroy(&test_lwp.lock);pass("retained-lwp-exit-preallocated-entry-and-fini-drain"); }
static struct task_struct *volatile wait_task;
static volatile unsigned int wait_ready;
static long wait_remaining;
static void *wait_worker(void *unused)
{ (void)unused;init_lwp();struct task_struct *task=linux_task_enter_current();assert(task);
  get_task_struct(task);__atomic_store_n(&wait_task,task,__ATOMIC_RELEASE);
  set_current_state(TASK_UNINTERRUPTIBLE);__atomic_store_n(&wait_ready,1,__ATOMIC_RELEASE);
  wait_remaining=schedule_timeout(5000);
  mutex_destroy(&test_lwp.lock);return NULL; }
static void test_real_condition_wake(void)
{ pthread_t thread;assert(linux_task_system_init()==0);
  assert(pthread_create(&thread,NULL,wait_worker,NULL)==0);
  while(!atomic_load_acquire(&wait_ready))model_yield();
  struct task_struct *task=__atomic_load_n(&wait_task,__ATOMIC_ACQUIRE);assert(task);
  assert(wake_up_process(task)==1);assert(pthread_join(thread,NULL)==0);
  assert(wait_remaining>0);irq_put(task);drain();assert(task_count==0);
  assert(linux_task_system_fini()==0);pass("native-owner-wait-condition-notification-model"); }
static void fatal_case(const char *name)
{ struct task_struct task;memset(&task,0,sizeof(task));raw_spin_lock_init(&task.lt_lock);
  if(!strcmp(name,"null-parent"))linux_task_alloc_owner_wait(NULL);
  else if(!strcmp(name,"shared-parent")){task.lt_refs=2;linux_task_alloc_owner_wait(&task);}
  else if(!strcmp(name,"dead-parent")){task.lt_refs=1;task.lt_exited=true;linux_task_alloc_owner_wait(&task);}
  else if(!strcmp(name,"attached-parent")){task.lt_refs=1;task.lt_lwp=curlwp;linux_task_alloc_owner_wait(&task);}
  else if(!strcmp(name,"overflow")){assert(linux_task_system_init()==0);task.lt_refs=1;
    task_count=UINT_MAX;linux_task_alloc_owner_wait(&task);}
  else if(!strcmp(name,"underflow"))put_task_struct(&task);
  else panic("unknown fatal case");
  panic("fatal case unexpectedly returned"); }
int main(int argc,char **argv)
{ alarm(45);if(argc==2){fatal_case(argv[1]);return 99;}
  assert(argc==1);test_init_failure();test_single_queue_and_deferred_free();
  test_pending_coalesces();test_running_coalesces();test_last_put_running();
  test_closed_owner_clones();test_preallocated_retained_owner();test_real_condition_wake();
  assert(passed==8&&test_allocs==test_frees&&test_keys==test_key_deletes&&test_wq_creates==test_wq_destroys+1);
  printf("TASK_NOTIFIER_MODEL_PASS cases=%u exact_frees=%u native_acceptance=OPEN\n",passed,test_frees);return 0; }

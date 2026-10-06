/* SPDX-License-Identifier: BSD-2-Clause */
#include <wait_test_model.h>
#include "../fatal_policy.c"
#include "../linux_task.c"
#include "../linux_wait.c"
#include "../linux_wait_var.c"
#include "guc_wait.c"

int
linux_kthread_wake_locked(struct task_struct *task)
{
    assert(mutex_owned(&task->lt_lock.rsl_lock));
    return 0;
}

static void
test_native_enter(void)
{
    test_proc.p_pid=getpid();
    strcpy(test_proc.p_comm,"wait-fixture");
    test_lwp.l_proc=curproc;
    mutex_init(&test_lwp.lock,0,0);
    assert(linux_task_enter_current()!=NULL);
}

struct callback { wait_queue_entry_t wait; int id,ret; bool clear_exclusive,remove;
    void *key; unsigned int mode; int flags; };
static int trace[16], ntrace;
static int
record_callback(wait_queue_entry_t *wait,unsigned int mode,int flags,void *key)
{
    struct callback *cb=container_of(wait,struct callback,wait);
    trace[ntrace++]=cb->id;
    cb->key=key;cb->mode=mode;cb->flags=flags;
    if(cb->clear_exclusive)wait->flags&=~WQ_FLAG_EXCLUSIVE;
    if(cb->remove)list_del_init(&wait->entry);
    return cb->ret;
}
static void
callback_init(struct callback *cb,int id,int ret)
{
    memset(cb,0,sizeof(*cb));cb->id=id;cb->ret=ret;
    init_waitqueue_func_entry(&cb->wait,record_callback);INIT_LIST_HEAD(&cb->wait.entry);
}
static void
test_callback_order_budget(void)
{
    wait_queue_head_t head;struct callback cb[6];init_waitqueue_head(&head);
    for(int i=0;i<6;i++)callback_init(cb+i,i+1,1);
    add_wait_queue_exclusive(&head,&cb[0].wait);
    add_wait_queue_exclusive(&head,&cb[1].wait);
    add_wait_queue(&head,&cb[2].wait);add_wait_queue(&head,&cb[3].wait);
    add_wait_queue_priority(&head,&cb[4].wait);
    assert(add_wait_queue_priority_exclusive(&head,&cb[5].wait)==-EBUSY);
    ntrace=0;assert(__wake_up(&head,TASK_NORMAL,1,NULL)==1);
    assert(ntrace==4&&trace[0]==5&&trace[1]==4&&trace[2]==3&&trace[3]==1);
    cb[4].ret=-1;ntrace=0;assert(__wake_up(&head,TASK_NORMAL,1,NULL)==0);
    assert(ntrace==1&&trace[0]==5);cb[4].ret=1;
    cb[0].ret=0;ntrace=0;assert(__wake_up(&head,TASK_NORMAL,1,NULL)==1);
    assert(ntrace==5&&trace[4]==2);
    cb[0].ret=1;cb[0].clear_exclusive=true;ntrace=0;
    assert(__wake_up(&head,TASK_NORMAL,1,NULL)==1);assert(ntrace==4);
    cb[0].wait.flags|=WQ_FLAG_EXCLUSIVE;cb[0].clear_exclusive=false;
    ntrace=0;assert(__wake_up(&head,TASK_NORMAL,0,NULL)==2);assert(ntrace==5);
    int key=3;__wake_up_sync_key(&head,TASK_INTERRUPTIBLE,&key);
    assert(cb[4].key==&key&&cb[4].mode==TASK_INTERRUPTIBLE&&cb[4].flags==0x10);
    for(int i=0;i<5;i++)cb[i].remove=true;
    __wake_up(&head,TASK_NORMAL,0,NULL);assert(!waitqueue_active(&head));
    destroy_waitqueue_head(&head);
    /* Empty→priority-exclusive, conflicting priority and exact cleanup. */
    init_waitqueue_head(&head);callback_init(&cb[0],1,1);
    assert(add_wait_queue_priority_exclusive(&head,&cb[0].wait)==0);
    assert(cb[0].wait.flags==(WQ_FLAG_PRIORITY|WQ_FLAG_EXCLUSIVE));
    remove_wait_queue(&head,&cb[0].wait);destroy_waitqueue_head(&head);
}

static int heap_frees;
static void clear_signal(void);
static int
self_free_callback(wait_queue_entry_t *wait,unsigned int mode,int flags,void *key)
{
    (void)mode;(void)flags;(void)key;
    list_del(&wait->entry);free(wait);heap_frees++;return 0;
}
static void
test_keyed_vars(void)
{
    assert(linux_wait_var_init()==0);
    unsigned int vars[1024];void *a=NULL,*b=NULL;
    for(unsigned int i=0;i<__arraycount(vars)&&!a;i++)
        for(unsigned int j=i+1;j<__arraycount(vars);j++)
            if(__var_waitqueue(vars+i)==__var_waitqueue(vars+j)){a=vars+i;b=vars+j;break;}
    assert(a&&b&&a!=b);
    struct wait_bit_queue_entry wa,wb;
    init_wait_var_entry(&wa,a,0);init_wait_var_entry(&wb,b,0);
    wait_queue_head_t *head=__var_waitqueue(a);
    prepare_to_wait(head,&wa.wq_entry,TASK_INTERRUPTIBLE);
    prepare_to_wait(head,&wb.wq_entry,TASK_INTERRUPTIBLE);
    wake_up_var(a);
    assert(list_empty(&wa.wq_entry.entry)&&!list_empty(&wb.wq_entry.entry));
    assert(current->__state==TASK_RUNNING);
    prepare_to_wait(head,&wb.wq_entry,TASK_INTERRUPTIBLE);
    struct wait_bit_key wrong={.flags=b,.bit_nr=0};
    __wake_up(head,TASK_NORMAL,1,&wrong);
    assert(current->__state==TASK_INTERRUPTIBLE&&!list_empty(&wb.wq_entry.entry));
    wake_up_var(b);assert(!waitqueue_active(head)&&current->__state==TASK_RUNNING);
    finish_wait(head,&wa.wq_entry);finish_wait(head,&wb.wq_entry);
    init_wait_var_entry(&wa,a,0);wa.wq_entry.func=woken_wake_bit_function;
    prepare_to_wait(head,&wa.wq_entry,TASK_UNINTERRUPTIBLE);
    struct wait_bit_key bad={.flags=b,.bit_nr=-1};
    __wake_up(head,TASK_NORMAL,1,&bad);assert(!(wa.wq_entry.flags&WQ_FLAG_WOKEN));
    wake_up_var(a);assert(wa.wq_entry.flags&WQ_FLAG_WOKEN);
    finish_wait(head,&wa.wq_entry);
    /* i915_active's callback frees its own heap entry and returns zero. */
    for(int i=0;i<3;i++){
        wait_queue_entry_t *entry=calloc(1,sizeof(*entry));assert(entry);
        init_waitqueue_func_entry(entry,self_free_callback);add_wait_queue(head,entry);
    }
    wake_up_var(a);assert(heap_frees==3&&!waitqueue_active(head));
    test_virtual_time=true;assert(wait_var_event_timeout(a,false,7)==0);
    assert(wait_var_event_timeout(a,true,0)==1);
    assert(wait_var_event_timeout(a,true,(long)INT_MAX+17)==(long)INT_MAX+17);
    test_virtual_time=false;
    curlwp->signals=1U<<SIGUSR1;curlwp->l_flag=LW_PENDSIG;
    assert(wait_var_event_interruptible(a,false)==-ERESTARTSYS);
    clear_signal();assert(!waitqueue_active(head));
    linux_wait_var_fini();
}

static wait_queue_head_t *hook_head;
static bool hook_condition;
static int hook_mode;
static void
wait_hook(bool intr,int ticks)
{
    (void)ticks;
    if(hook_mode==1||hook_mode==2){assert(intr);curlwp->signals=1U<<SIGUSR1;curlwp->l_flag=LW_PENDSIG;}
    if(hook_mode==2||hook_mode==3){hook_condition=true;wake_up_all(hook_head);}
}
static void
clear_signal(void)
{
    curlwp->signals=0;curlwp->l_flag=0;
}
static void
test_state_woken_and_timeouts(void)
{
    wait_queue_head_t head;DEFINE_WAIT(wait);init_waitqueue_head(&head);
    prepare_to_wait(&head,&wait,TASK_INTERRUPTIBLE);assert(waitqueue_active(&head));
    assert(wake_up(&head)==0); /* Entry is non-exclusive. */
    assert(current->__state==TASK_RUNNING&&!waitqueue_active(&head));
    assert(schedule_timeout((long)INT_MAX+17)>INT_MAX);
    finish_wait(&head,&wait);
    init_waitqueue_func_entry(&wait,woken_wake_function);INIT_LIST_HEAD(&wait.entry);wait.private=current;
    add_wait_queue(&head,&wait);wake_up_all(&head);
    assert(wait.flags&WQ_FLAG_WOKEN);
    assert(wait_woken(&wait,TASK_INTERRUPTIBLE,17)==17);
    assert(!(wait.flags&WQ_FLAG_WOKEN)&&current->__state==TASK_RUNNING);
    /* Actual pinned GuC helper intentionally ignores kthread stop. */
    test_should_stop=1;wait.flags|=WQ_FLAG_WOKEN;
    assert(must_wait_woken(&wait,23)==23);
    assert(!(wait.flags&WQ_FLAG_WOKEN));test_should_stop=0;
    remove_wait_queue(&head,&wait);
    test_virtual_time=true;test_ticks=UINT_MAX-10;test_slices=0;
    set_current_state(TASK_UNINTERRUPTIBLE);
    assert(schedule_timeout((long)INT_MAX+17)==0&&test_slices==3);
    assert(current->__state==TASK_RUNNING);
    assert(wait_event_timeout(head,false,0)==0);
    assert(wait_event_timeout(head,true,0)==1);
    assert(wait_event_timeout(head,true,(long)INT_MAX+17)==(long)INT_MAX+17);
    /* Condition becoming true on the exact final timeout claims 1. */
    hook_head=&head;hook_mode=3;hook_condition=false;test_wait_hook=wait_hook;
    assert(wait_event_timeout(head,hook_condition,1)==1);
    assert(!waitqueue_active(&head)&&current->__state==TASK_RUNNING);
    test_wait_hook=NULL;
    curlwp->signals=1U<<SIGUSR1;curlwp->l_flag=LW_PENDSIG;
    assert(wait_event_interruptible(head,false)==-ERESTARTSYS);
    assert(wait_event_interruptible(head,true)==0);
    assert(!waitqueue_active(&head));clear_signal();
    hook_mode=1;test_wait_hook=wait_hook;
    assert(wait_event_interruptible_timeout(head,false,17)==-ERESTARTSYS);
    assert(!waitqueue_active(&head)&&current->__state==TASK_RUNNING);clear_signal();
    hook_mode=2;hook_condition=false;
    assert(wait_event_interruptible_timeout(head,hook_condition,17)==17);
    assert(!waitqueue_active(&head));clear_signal();
    test_wait_hook=NULL;test_virtual_time=false;
    linux_sched_set_fifo(current);assert(curlwp->l_class==SCHED_FIFO&&curlwp->pri==PRI_KERNEL_RT);
    unsigned int before=atomic_load_acquire(&task_count);test_softint_fail=true;
    assert(linux_task_alloc()==NULL&&atomic_load_acquire(&task_count)==before);test_softint_fail=false;
    destroy_waitqueue_head(&head);
}

struct race { wait_queue_head_t head;pthread_barrier_t prepared,finished;volatile int condition;int cycles; };
static void *
race_waiter(void *cookie)
{
    struct race *race=cookie;test_native_enter();
    for(int i=0;i<race->cycles;i++){
        DEFINE_WAIT(wait);prepare_to_wait(&race->head,&wait,TASK_UNINTERRUPTIBLE);
        int e=pthread_barrier_wait(&race->prepared);assert(e==0||e==PTHREAD_BARRIER_SERIAL_THREAD);
        long budget=1000;
        while(!__atomic_load_n(&race->condition,__ATOMIC_ACQUIRE)){
            budget=schedule_timeout(budget);assert(budget!=0);
            if(!__atomic_load_n(&race->condition,__ATOMIC_ACQUIRE))
                prepare_to_wait(&race->head,&wait,TASK_UNINTERRUPTIBLE);
        }
        finish_wait(&race->head,&wait);assert(current->__state==TASK_RUNNING);
        e=pthread_barrier_wait(&race->finished);assert(e==0||e==PTHREAD_BARRIER_SERIAL_THREAD);
    }
    return NULL; /* Native TLS destructor must drain the queued notifier. */
}
static void
test_wake_races_and_lifetime(void)
{
    struct race race;memset(&race,0,sizeof(race));race.cycles=10000;init_waitqueue_head(&race.head);
    assert(pthread_barrier_init(&race.prepared,NULL,2)==0);assert(pthread_barrier_init(&race.finished,NULL,2)==0);
    unsigned int before=atomic_load_acquire(&task_count);pthread_t thread;
    assert(pthread_create(&thread,NULL,race_waiter,&race)==0);
    for(int i=0;i<race.cycles;i++){
        __atomic_store_n(&race.condition,0,__ATOMIC_RELEASE);
        int e=pthread_barrier_wait(&race.prepared);assert(e==0||e==PTHREAD_BARRIER_SERIAL_THREAD);
        if(i%3==0)(void)sched_yield();
        __atomic_store_n(&race.condition,1,__ATOMIC_RELEASE);smp_mb();
        test_irq=true;wake_up_all(&race.head);test_irq=false;
        e=pthread_barrier_wait(&race.finished);assert(e==0||e==PTHREAD_BARRIER_SERIAL_THREAD);
    }
    assert(pthread_join(thread,NULL)==0);assert(atomic_load_acquire(&task_count)==before);
    assert(!waitqueue_active(&race.head));destroy_waitqueue_head(&race.head);
    assert(pthread_barrier_destroy(&race.prepared)==0);assert(pthread_barrier_destroy(&race.finished)==0);
}


static pthread_barrier_t alloc_entered, alloc_release;
static void
constructor_block(void)
{
    assert(atomic_load_acquire(&task_count) == 1);
    int error=pthread_barrier_wait(&alloc_entered);
    assert(error==0||error==PTHREAD_BARRIER_SERIAL_THREAD);
    error=pthread_barrier_wait(&alloc_release);
    assert(error==0||error==PTHREAD_BARRIER_SERIAL_THREAD);
}
static void *
constructor_thread(void *arg)
{
    (void)arg;
    struct task_struct *task=linux_task_alloc();assert(task);
    put_task_struct(task);return NULL;
}
struct admission_race {
    pthread_barrier_t start, allocated, done;
    struct task_struct *task;
    int cycles;
};
static void *
admission_thread(void *arg)
{
    struct admission_race *race=arg;
    for(int i=0;i<race->cycles;i++){
        int error=pthread_barrier_wait(&race->start);
        assert(error==0||error==PTHREAD_BARRIER_SERIAL_THREAD);
        race->task=linux_task_alloc();
        error=pthread_barrier_wait(&race->allocated);
        assert(error==0||error==PTHREAD_BARRIER_SERIAL_THREAD);
        if(race->task)put_task_struct(race->task);
        error=pthread_barrier_wait(&race->done);
        assert(error==0||error==PTHREAD_BARRIER_SERIAL_THREAD);
    }
    return NULL;
}
static void
test_atomic_admission(void)
{
    assert(!linux_task_system_busy());
    assert(pthread_barrier_init(&alloc_entered,NULL,2)==0);
    assert(pthread_barrier_init(&alloc_release,NULL,2)==0);
    test_alloc_hook=constructor_block;
    pthread_t thread;assert(pthread_create(&thread,NULL,constructor_thread,NULL)==0);
    int error=pthread_barrier_wait(&alloc_entered);
    assert(error==0||error==PTHREAD_BARRIER_SERIAL_THREAD);
    /* Object memory is not allocated yet. Its reservation must forbid fini. */
    assert(linux_task_system_quiesce()==EBUSY);
    assert(linux_task_system_fini()==EBUSY);
    assert(task_key!=(specificdata_key_t)-1);
    error=pthread_barrier_wait(&alloc_release);
    assert(error==0||error==PTHREAD_BARRIER_SERIAL_THREAD);
    assert(pthread_join(thread,NULL)==0);test_alloc_hook=NULL;
    assert(!linux_task_system_busy());
    assert(pthread_barrier_destroy(&alloc_entered)==0);
    assert(pthread_barrier_destroy(&alloc_release)==0);
    assert(linux_task_system_quiesce()==0);
    assert(linux_task_alloc()==NULL);
    assert(linux_task_enter_current()==NULL); /* Must reject before TLS lookup. */
    linux_task_system_resume();
    struct admission_race race={.cycles=500};
    assert(pthread_barrier_init(&race.start,NULL,2)==0);
    assert(pthread_barrier_init(&race.allocated,NULL,2)==0);
    assert(pthread_barrier_init(&race.done,NULL,2)==0);
    assert(pthread_create(&thread,NULL,admission_thread,&race)==0);
    for(int i=0;i<race.cycles;i++){
        error=pthread_barrier_wait(&race.start);
        assert(error==0||error==PTHREAD_BARRIER_SERIAL_THREAD);
        int closed=linux_task_system_quiesce();assert(closed==0||closed==EBUSY);
        error=pthread_barrier_wait(&race.allocated);
        assert(error==0||error==PTHREAD_BARRIER_SERIAL_THREAD);
        if(closed==0){assert(race.task==NULL);linux_task_system_resume();}
        else assert(race.task!=NULL);
        error=pthread_barrier_wait(&race.done);
        assert(error==0||error==PTHREAD_BARRIER_SERIAL_THREAD);
    }
    assert(pthread_join(thread,NULL)==0);assert(!linux_task_system_busy());
    assert(pthread_barrier_destroy(&race.start)==0);
    assert(pthread_barrier_destroy(&race.allocated)==0);
    assert(pthread_barrier_destroy(&race.done)==0);
    puts("PASS reservation before constructor/TLS, EBUSY preserving key, closed rejection, 500 admission races");
}


static void
fatal_condition_hook(bool intr,int ticks)
{
    (void)ticks;assert(intr);
    curlwp->signals=1U<<SIGKILL;curlwp->l_flag=LW_PENDSIG;
    hook_condition=true;wake_up_all(hook_head);
}
static void
test_fatal_filter(void)
{
    /* These two helpers are the actual candidate kern_sleepq.c source. */
    syncobj_t normal={.sobj_flag=0},fatal={.sobj_flag=SOBJ_SIGKILL};
    lwp_lock(curlwp);curlwp->l_syncobj=&normal;curlwp->l_flag=LW_SINTR;
    assert(sleepq_sigwake_allowed(curlwp,SIGUSR1));
    curlwp->l_syncobj=&fatal;
    assert(!sleepq_sigwake_allowed(curlwp,SIGUSR1));
    assert(!sleepq_sigwake_allowed(curlwp,SIGSTOP));
    assert(!sleepq_sigwake_allowed(curlwp,SIGCONT));
    assert(sleepq_sigwake_allowed(curlwp,SIGKILL));
    curlwp->l_flag=0;assert(!sleepq_sigwake_allowed(curlwp,SIGKILL));
    curlwp->l_syncobj=NULL;lwp_unlock(curlwp);
    wait_queue_head_t head;init_waitqueue_head(&head);
    test_virtual_time=true;
    curlwp->signals=1U<<SIGUSR1;curlwp->l_flag=LW_PENDSIG;
    assert(signal_pending(current)&&!fatal_signal_pending(current));
    assert(!signal_pending_state(TASK_KILLABLE,current));
    assert(wait_event_killable_timeout(head,false,17)==0);
    assert(curlwp->signals==(1U<<SIGUSR1)&&curlwp->l_flag==LW_PENDSIG);
    curlwp->signals=1U<<SIGSTOP;
    assert(wait_event_killable_timeout(head,false,(long)INT_MAX+17)==0);
    assert(curlwp->signals==(1U<<SIGSTOP));
    clear_signal();
    curlwp->signals=1U<<SIGKILL;curlwp->l_flag=LW_PENDSIG;
    assert(fatal_signal_pending(current));
    assert(wait_event_killable(head,false)==-ERESTARTSYS);
    assert(!waitqueue_active(&head)&&current->__state==TASK_RUNNING);
    assert(wait_event_killable_timeout(head,true,17)==17);
    assert(linux_wait_var_init()==0);int var=0;
    assert(wait_var_event_killable(&var,false)==-ERESTARTSYS);
    assert(!waitqueue_active(__var_waitqueue(&var)));linux_wait_var_fini();
    clear_signal();curlwp->l_flag=LW_WEXIT;
    assert(fatal_signal_pending(current)&&signal_pending(current));
    assert(wait_event_killable(head,false)==-ERESTARTSYS);
    assert(wait_event_interruptible(head,false)==-ERESTARTSYS);
    clear_signal();curlwp->l_flag=LW_WCORE;
    assert(wait_event_killable(head,false)==-ERESTARTSYS);
    clear_signal();
    hook_head=&head;hook_condition=false;test_wait_hook=fatal_condition_hook;
    assert(wait_event_killable_timeout(head,hook_condition,17)==17);
    assert(!waitqueue_active(&head)&&current->__state==TASK_RUNNING);
    test_wait_hook=NULL;clear_signal();test_virtual_time=false;
    destroy_waitqueue_head(&head);
    puts("PASS actual Native policy: nonfatal/stop/continue filtering, SIGKILL, exit/core predicates, wide timeout, condition/fatal race, selected var-killable cleanup");
}

int
main(void)
{
    alarm(40);assert(sizeof(long)==8);assert(linux_task_system_init()==0);test_native_enter();
    assert(linux_task_system_quiesce()==EBUSY);assert(linux_task_system_fini()==EBUSY);
    test_callback_order_budget();puts("PASS callback priority/order/key/negative/exclusive/removal");
    test_state_woken_and_timeouts();puts("PASS prepare/wake-before-schedule/GuC/wide-timeout-wrap/signal-condition/FIFO/allocation-failure");
    test_keyed_vars();puts("PASS hashed address collision/key/bit filtering/var-timeout/signal/self-free callbacks");
    test_fatal_filter();
    test_wake_races_and_lifetime();puts("PASS 10000 IRQ wake-vs-schedule races and TLS/notifier drain");
    struct task_struct *task=current;lwp_setspecific(task_key,NULL);linux_task_owner_exit(task);
    assert(!linux_task_system_busy());test_atomic_admission();
    assert(linux_task_system_fini()==0);puts("PASS owner references and native-lifetime delegation model");
    return 0;
}

/* SPDX-License-Identifier: BSD-2-Clause */
/* Native boundary delegates only. Production FILE/FD/POLL C and headers are
 * included unchanged by the fixture; this is not a native kernel ABI model. */
#ifndef NATIVE_FILE_LIFECYCLE_MODEL_H
#define NATIVE_FILE_LIFECYCLE_MODEL_H
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <sys/types.h>
#include <sys/queue.h>
#include <assert.h>
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <pthread.h>
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
typedef uint64_t voff_t;
typedef unsigned int gfp_t;
typedef struct { int counter; } atomic_t;
static inline int atomic_read(const atomic_t *a) { return a->counter; }
#define KASSERT(c) assert(c)
#define KASSERTMSG(c,...) assert(c)
#define panic(...) do { fprintf(stderr,__VA_ARGS__);fputc('\n',stderr);abort(); } while(0)
#define MIN(a,b) ((a)<(b)?(a):(b))
#define MUTEX_DEFAULT 0
#define IPL_HIGH 2
#define KM_SLEEP 0
#define KM_NOSLEEP 1
#define PRI_NONE 0
#define WQ_MPSAFE 1
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define membar_sync() __atomic_thread_fence(__ATOMIC_SEQ_CST)
#define membar_acquire() __atomic_thread_fence(__ATOMIC_ACQUIRE)
#define membar_release() __atomic_thread_fence(__ATOMIC_RELEASE)
#define atomic_load_acquire(p) __atomic_load_n((p),__ATOMIC_ACQUIRE)
#define atomic_load_relaxed(p) __atomic_load_n((p),__ATOMIC_RELAXED)
#define atomic_store_release(p,v) __atomic_store_n((p),(v),__ATOMIC_RELEASE)
#define atomic_store_relaxed(p,v) __atomic_store_n((p),(v),__ATOMIC_RELAXED)
#define atomic_inc_uint(p) ((void)__atomic_add_fetch((p),1,__ATOMIC_SEQ_CST))
#define atomic_dec_uint(p) ((void)__atomic_sub_fetch((p),1,__ATOMIC_SEQ_CST))
static unsigned int atomic_cas_uint(volatile unsigned int *p,unsigned int old,unsigned int value)
{ __atomic_compare_exchange_n(p,&old,value,false,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST);return old; }
static unsigned long atomic_cas_ulong(volatile unsigned long *p,unsigned long old,unsigned long value)
{ __atomic_compare_exchange_n(p,&old,value,false,__ATOMIC_SEQ_CST,__ATOMIC_SEQ_CST);return old; }
static void atomic_or_ulong(volatile unsigned long *p,unsigned long bits)
{ (void)__atomic_fetch_or(p,bits,__ATOMIC_SEQ_CST); }
static void atomic_and_ulong(volatile unsigned long *p,unsigned long bits)
{ (void)__atomic_fetch_and(p,bits,__ATOMIC_SEQ_CST); }
static _Thread_local bool model_irq,model_rcu_callback;
static _Thread_local unsigned int model_lock_depth;
#define ASSERT_SLEEPABLE() assert(!model_irq&&model_lock_depth==0)
typedef struct { pthread_mutex_t lock;bool held; } kmutex_t;
typedef struct { kmutex_t sl_lock; } spinlock_t;
struct mutex { kmutex_t native; };
struct rw_semaphore { unsigned int readers;bool writer; };
typedef struct { unsigned int unused; } kcondvar_t;
static void mutex_init(kmutex_t *m,int type,int ipl)
{ (void)type;(void)ipl;assert(pthread_mutex_init(&m->lock,NULL)==0);m->held=false; }
static void mutex_enter(kmutex_t *m)
{ assert(pthread_mutex_lock(&m->lock)==0);assert(!m->held);m->held=true;model_lock_depth++; }
static void mutex_exit(kmutex_t *m)
{ assert(m->held&&model_lock_depth);m->held=false;model_lock_depth--;assert(pthread_mutex_unlock(&m->lock)==0); }
static bool mutex_owned(kmutex_t *m) { return m->held; }
static void mutex_destroy(kmutex_t *m) { assert(!m->held);assert(pthread_mutex_destroy(&m->lock)==0); }
static void spin_lock_init(spinlock_t *m) { mutex_init(&m->sl_lock,0,IPL_HIGH); }
static void spin_lock_destroy(spinlock_t *m) { mutex_destroy(&m->sl_lock); }
static void linux_mutex_init(struct mutex *m) { mutex_init(&m->native,0,0); }
static void linux_mutex_destroy(struct mutex *m) { mutex_destroy(&m->native); }
static void mutex_lock(struct mutex *m) { mutex_enter(&m->native); }
static void mutex_unlock(struct mutex *m) { mutex_exit(&m->native); }
static void down_read(struct rw_semaphore *s) { assert(!s->writer);s->readers++; }
static void up_read(struct rw_semaphore *s) { assert(s->readers);s->readers--; }
static void down_write(struct rw_semaphore *s) { assert(!s->readers&&!s->writer);s->writer=true; }
static void up_write(struct rw_semaphore *s) { assert(s->writer);s->writer=false; }
static int down_read_trylock(struct rw_semaphore *s) { if(s->writer)return 0;down_read(s);return 1; }
#define spin_lock_irqsave(m,f) do { (f)=0;mutex_enter(&(m)->sl_lock); } while(0)
#define spin_unlock_irqrestore(m,f) do { (void)(f);mutex_exit(&(m)->sl_lock); } while(0)
static void cv_init(kcondvar_t *c,const char *name) { (void)c;(void)name; }
static void cv_destroy(kcondvar_t *c) { (void)c; }
static void cv_broadcast(kcondvar_t *c) { (void)c; }
static void cv_wait(kcondvar_t *c,kmutex_t *m) { (void)c;(void)m;panic("model: unexpected blocking CV wait"); }
struct model_alloc { struct model_alloc *next;void *pointer;size_t bytes; };
static struct model_alloc *model_allocations;
static int model_fail_alloc_after=-1;
static void *model_watch_shell;
static bool model_shell_freed;
static unsigned int model_alloc_count,model_free_count;
static void model_shell_free_event(void);
static void *kmem_zalloc(size_t bytes,int flags)
{ assert(!model_irq);(void)flags;if(model_fail_alloc_after==0)return NULL;
  if(model_fail_alloc_after>0)model_fail_alloc_after--;
  struct model_alloc *record=calloc(1,sizeof(*record));assert(record);
  record->pointer=calloc(1,bytes);assert(record->pointer);record->bytes=bytes;
  record->next=model_allocations;model_allocations=record;model_alloc_count++;return record->pointer; }
static void kmem_free(void *pointer,size_t bytes)
{ assert(!model_irq);struct model_alloc **link=&model_allocations;
  while(*link&&(*link)->pointer!=pointer)link=&(*link)->next;
  assert(*link&&(*link)->bytes==bytes);struct model_alloc *record=*link;*link=record->next;
  if(pointer==model_watch_shell){model_shell_freed=true;model_shell_free_event();}
  free(pointer);free(record);model_free_count++; }
struct rcu_head { struct rcu_head *next;void(*callback)(struct rcu_head *); };
static struct rcu_head *model_rcu_head,*model_rcu_tail;
static unsigned int model_rcu_readers,model_rcu_pending;
static void rcu_read_lock(void) { model_rcu_readers++; }
static void rcu_read_unlock(void) { assert(model_rcu_readers);model_rcu_readers--; }
#define rcu_dereference_raw(p) __atomic_load_n(&(p),__ATOMIC_ACQUIRE)
static void call_rcu(struct rcu_head *h,void(*callback)(struct rcu_head *))
{ h->next=NULL;h->callback=callback;if(model_rcu_tail)model_rcu_tail->next=h;else model_rcu_head=h;
  model_rcu_tail=h;model_rcu_pending++; }
static unsigned int model_run_rcu(void)
{ unsigned int count=0;if(model_rcu_readers)return 0;
  while(model_rcu_head){struct rcu_head *h=model_rcu_head;model_rcu_head=h->next;
    if(!model_rcu_head)model_rcu_tail=NULL;
    model_rcu_pending--;model_rcu_callback=true;
    h->callback(h);model_rcu_callback=false;count++;}return count; }
static void rcu_barrier(void) { assert(!model_rcu_readers);(void)model_run_rcu(); }
struct task_struct { unsigned int refs; };
struct work { void *wk_dummy; };
struct workqueue { void(*callback)(struct work *,void *);void *cookie;
    struct work *work[128];unsigned int count;struct task_struct *task; };
static struct workqueue *model_running_queue;
static struct task_struct *model_main_task;
static unsigned int model_task_live,model_queue_created,model_queue_destroyed;
static struct task_struct *linux_task_alloc(void)
{ ASSERT_SLEEPABLE();struct task_struct *t=calloc(1,sizeof(*t));assert(t);t->refs=1;model_task_live++;return t; }
static void put_task_struct(struct task_struct *t)
{ assert(t&&t->refs);if(--t->refs==0){free(t);model_task_live--;} }
static struct task_struct **model_current_task_slot(void)
{ return model_running_queue?&model_running_queue->task:&model_main_task; }
static void linux_task_entry_enter_preallocated(struct task_struct **handle,struct task_struct **spare)
{ ASSERT_SLEEPABLE();assert(handle&&!*handle&&spare&&*spare&&(*spare)->refs==1);
  struct task_struct **current=model_current_task_slot();
  if(*current){(*current)->refs++;put_task_struct(*spare);*handle=*current;}
  else{*current=*spare;(*current)->refs++;*handle=*spare;}*spare=NULL; }
static int linux_task_entry_enter(struct task_struct **handle)
{ struct task_struct *spare=linux_task_alloc();linux_task_entry_enter_preallocated(handle,&spare);return 0; }
static void linux_task_entry_leave(struct task_struct **handle)
{ assert(handle&&*handle);put_task_struct(*handle);*handle=NULL; }
static int linux_task_system_quiesce_retained(struct task_struct *retained)
{ return model_task_live==(retained?1U:0U)?0:EBUSY; }
static int workqueue_create(struct workqueue **out,const char *name,
    void(*callback)(struct work *,void *),void *cookie,int pri,int ipl,int flags)
{ ASSERT_SLEEPABLE();(void)name;assert(pri==PRI_NONE&&ipl==IPL_HIGH&&flags==WQ_MPSAFE);
  *out=calloc(1,sizeof(**out));assert(*out);(*out)->callback=callback;(*out)->cookie=cookie;
  model_queue_created++;return 0; }
static void workqueue_enqueue(struct workqueue *q,struct work *work,void *cpu)
{ assert(q&&cpu==NULL&&q->count<128);for(unsigned int i=0;i<q->count;i++)assert(q->work[i]!=work);
  q->work[q->count++]=work; }
static void model_run_work(struct workqueue *q)
{ assert(q&&q->count&&model_running_queue==NULL);struct work *work=q->work[0];
  memmove(q->work,q->work+1,--q->count*sizeof(q->work[0]));model_running_queue=q;
  q->callback(work,q->cookie);model_running_queue=NULL; }
static void workqueue_destroy(struct workqueue *q)
{ ASSERT_SLEEPABLE();assert(q&&q->count==0);if(q->task)put_task_struct(q->task);
  free(q);model_queue_destroyed++; }
struct module { unsigned int refs,holds,releases; };
static void module_hold(struct module *m) { assert(!model_irq&&!model_rcu_callback);m->refs++;m->holds++; }
static void module_rele(struct module *);
/* Genuine Native sys/types.h owns kauth_cred_t = struct kauth_cred *.
 * Complete only the delegated object's model fields; do not redefine alias. */
struct kauth_cred { unsigned int refs; };
static kauth_cred_t kauth_cred_hold(kauth_cred_t c) { assert(c);c->refs++;return c; }
static void kauth_cred_free(kauth_cred_t c) { assert(c&&c->refs);c->refs--; }
struct linux_file;
struct file;
struct knote;
struct fileops { struct linux_file *(*fo_linux_file)(struct file *); };
struct file { unsigned int f_flag;int f_type;const struct fileops *f_ops;void *f_data; };
typedef struct file file_t;
#define DTYPE_MISC 5
#ifndef FREAD
#define FREAD 1U
#endif
#ifndef FWRITE
#define FWRITE 2U
#endif
#ifndef FNONBLOCK
#define FNONBLOCK O_NONBLOCK
#endif
struct model_fd_slot { file_t *native;bool reserved,installed,exclose;unsigned int borrowed; };
typedef struct filedesc { struct model_fd_slot slots[16]; } filedesc_t;
struct proc { unsigned int unused; };
struct lwp { filedesc_t *l_fd;kauth_cred_t l_cred; };
static struct proc model_proc;
static filedesc_t model_fd_table;
static struct kauth_cred model_credential={1};
static struct lwp model_lwp={&model_fd_table,&model_credential};
#define curlwp (&model_lwp)
#define curproc (&model_proc)
static int model_fd_alloc_error;
static bool model_close_on_borrow_drop;
static unsigned int model_fd_aborts,model_fd_affixes,model_fd_borrows,model_fd_drops;
static int fd_allocfile(file_t **out,int *fd)
{ ASSERT_SLEEPABLE();if(model_fd_alloc_error)return model_fd_alloc_error;
  for(unsigned int i=0;i<16;i++)if(!model_fd_table.slots[i].native){file_t *fp=calloc(1,sizeof(*fp));assert(fp);
    model_fd_table.slots[i]=(struct model_fd_slot){.native=fp,.reserved=true};*out=fp;*fd=(int)i;return 0;}return EMFILE; }
static void fd_set_exclose(struct lwp *l,int fd,bool exclose) { l->l_fd->slots[fd].exclose=exclose; }
static void fd_abort(struct proc *p,file_t *fp,unsigned int fd)
{ (void)p;assert(fd<16&&model_fd_table.slots[fd].reserved&&model_fd_table.slots[fd].native==fp);
  free(fp);memset(model_fd_table.slots+fd,0,sizeof(model_fd_table.slots[fd]));model_fd_aborts++; }
static void fd_affix(struct proc *p,file_t *fp,unsigned int fd)
{ (void)p;assert(fd<16&&model_fd_table.slots[fd].reserved&&model_fd_table.slots[fd].native==fp);
  model_fd_table.slots[fd].reserved=false;model_fd_table.slots[fd].installed=true;model_fd_affixes++; }
static file_t *fd_getfile(unsigned int fd)
{ if(fd>=16||!model_fd_table.slots[fd].installed)return NULL;
  model_fd_table.slots[fd].borrowed++;model_fd_borrows++;return model_fd_table.slots[fd].native; }
static void fd_putfile(unsigned int);
struct linux_file *fd_get_linux_file(unsigned int);
struct list_head { struct list_head *next,*prev; };
#define INIT_LIST_HEAD(h) do { (h)->next=(h);(h)->prev=(h); } while(0)
static bool list_empty(const struct list_head *h) { return h->next==h; }
static void list_del_init(struct list_head *n)
{ n->prev->next=n->next;n->next->prev=n->prev;INIT_LIST_HEAD(n); }
struct wait_queue_entry;
typedef struct wait_queue_entry { struct list_head entry;
    int(*func)(struct wait_queue_entry *,unsigned int,int,void *); } wait_queue_entry_t;
typedef struct { spinlock_t lock;struct list_head head; } wait_queue_head_t;
static void init_waitqueue_func_entry(wait_queue_entry_t *w,int(*fn)(wait_queue_entry_t *,unsigned int,int,void *))
{ w->func=fn;INIT_LIST_HEAD(&w->entry); }
static void add_wait_queue(wait_queue_head_t *h,wait_queue_entry_t *w)
{ unsigned long f;spin_lock_irqsave(&h->lock,f);w->entry.prev=h->head.prev;w->entry.next=&h->head;
  h->head.prev->next=&w->entry;h->head.prev=&w->entry;spin_unlock_irqrestore(&h->lock,f); }
struct filterops { unsigned int f_flags;void(*f_detach)(struct knote *);int(*f_event)(struct knote *,long); };
struct knote { SLIST_ENTRY(knote) link;void *kn_hook;const struct filterops *kn_fop;int kn_filter,kn_flags;int64_t kn_data; };
struct selinfo { SLIST_HEAD(,knote) sel_klist;unsigned int records,resets,notifies;int last_events; };
#define NOTE_SUBMIT 0x01000000U
#define EVFILT_READ 0U
#define EVFILT_WRITE 1U
#define EV_EOF 0x8000
#define FILTEROP_ISFD 1
#define FILTEROP_MPSAFE 2
static void selinit(struct selinfo *s) { memset(s,0,sizeof(*s));SLIST_INIT(&s->sel_klist); }
static void seldestroy(struct selinfo *s) { assert(SLIST_EMPTY(&s->sel_klist)); }
static void selrecord(struct lwp *l,struct selinfo *s) { (void)l;s->records++; }
static void selnotify(struct selinfo *s,int events,long hint)
{ assert(hint==NOTE_SUBMIT);s->notifies++;s->last_events=events;if(events==0)s->resets++;
  struct knote *kn;SLIST_FOREACH(kn,&s->sel_klist,link)(void)kn->kn_fop->f_event(kn,hint); }
static void selrecord_knote(struct selinfo *s,struct knote *kn) { SLIST_INSERT_HEAD(&s->sel_klist,kn,link); }
static bool selremove_knote(struct selinfo *s,struct knote *kn)
{ SLIST_REMOVE(&s->sel_klist,kn,knote,link);return true; }
#define IS_ERR(p) ((uintptr_t)(p)>=(uintptr_t)-4095)
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define PTR_ERR(p) ((long)(intptr_t)(p))
static int linux_page_system_init(void) { return 0; }
static void linux_page_system_fini(void) { }
static void linux_shmem_commit_init(void) { }
static void linux_shmem_commit_fini(void) { }
static int linux_anon_inode_init(void) { return 0; }
static void linux_anon_inode_fini(void) { }
static bool model_anon_busy;
static bool linux_anon_inode_busy(void) { return model_anon_busy; }
#endif

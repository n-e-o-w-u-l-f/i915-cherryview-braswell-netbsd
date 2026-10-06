/* SPDX-License-Identifier: BSD-2-Clause */
/* Complete actual task C and actual native DRM shim; delegated OS primitives. */
#include <wait_test_model.h>
#include "linux_task.c"
#include <stdatomic.h>

int linux_kthread_wake_locked(struct task_struct *task)
{
    assert(mutex_owned(&task->lt_lock.rsl_lock));
    return 0;
}
struct file {void *f_data;};
struct drm_driver {int (*ioctl_override)(struct file *,unsigned long,void *);};
struct drm_device {struct drm_driver *driver;};
struct drm_minor {struct drm_device *dev;};
struct drm_file {struct drm_minor *minor;};
static _Thread_local unsigned int driver_calls;
static _Thread_local struct task_struct *driver_identity;
static _Thread_local unsigned int nested;
static _Thread_local unsigned int expected_refs;
static atomic_uint checks;
static unsigned int scenarios;
#define CHECK(x) do {++checks;assert(x);}while(0)
static int driver(struct file *fp,unsigned long cmd,void *data);
static int drm_ioctl(struct file *fp,unsigned long cmd,void *data)
{
    return driver(fp,cmd,data);
}
#include "drm_ioctl_shim.inc"
static int driver(struct file *fp,unsigned long cmd,void *data)
{
    struct task_struct *task=current;(void)data;++driver_calls;
    CHECK(task!=NULL&&task->lt_lwp==curlwp&&!task->lt_exited);
    CHECK(task->lt_refs==expected_refs);
    if(driver_identity==NULL)driver_identity=task;
    CHECK(task==driver_identity);
    if(cmd==1&&nested==0){++nested;++expected_refs;
        CHECK(drm_ioctl_shim(fp,0,NULL)==0);--expected_refs;--nested;
        CHECK(task==current&&task->lt_refs==expected_refs);}
    if(cmd==2)return EIO;
    if(cmd==3)return ERESTARTSYS;
    return 0;
}
static void prepare_lwp(void)
{
    test_proc.p_pid=getpid();strcpy(test_proc.p_comm,"entry-fixture");
    test_lwp.l_proc=curproc;mutex_init(&test_lwp.lock,0,0);
    driver_calls=0;driver_identity=NULL;nested=0;expected_refs=2;
}
static struct task_struct *retained;
static void *ioctls(void *arg)
{
    struct drm_driver d={driver};struct drm_device dev={&d};
    struct drm_minor minor={&dev};struct drm_file priv={&minor};struct file fp={&priv};
    prepare_lwp();CHECK(drm_ioctl_shim(&fp,0,NULL)==0);CHECK(driver_calls==1);
    CHECK(current==driver_identity&&current->lt_refs==1);
    CHECK(drm_ioctl_shim(&fp,1,NULL)==0);CHECK(driver_calls==3&&current->lt_refs==1);
    CHECK(drm_ioctl_shim(&fp,2,NULL)==EIO);CHECK(driver_calls==4&&current->lt_refs==1);
    CHECK(drm_ioctl_shim(&fp,3,NULL)==ERESTART);CHECK(driver_calls==5&&current->lt_refs==1);
    d.ioctl_override=NULL;CHECK(drm_ioctl_shim(&fp,0,NULL)==0);
    CHECK(driver_calls==6&&current==driver_identity&&current->lt_refs==1);
    CHECK(linux_task_system_quiesce()==EBUSY);
    if(arg){retained=current;get_task_struct(retained);CHECK(retained->lt_refs==2);}
    mutex_destroy(&test_lwp.lock);return NULL; /* natural LWP/TLS owner exit */
}
static void *nested_entry(void *arg)
{
    struct task_struct *a=NULL,*b=NULL,*again=NULL;(void)arg;prepare_lwp();
    CHECK(!linux_task_entry_enter(&a));CHECK(a==current&&a->lt_refs==2);
    CHECK(!linux_task_entry_enter(&b));CHECK(a==b&&a->lt_refs==3);
    CHECK(linux_task_entry_enter(&b)==EINVAL);CHECK(a->lt_refs==3);
    linux_task_entry_leave(&b);CHECK(b==NULL&&a->lt_refs==2);
    linux_task_entry_leave(&a);CHECK(a==NULL&&current->lt_refs==1&&!current->lt_exited);
    CHECK(!linux_task_entry_enter(&again));CHECK(again==current&&again->lt_refs==2);
    linux_task_entry_leave(&again);CHECK(again==NULL&&current->lt_refs==1);
    mutex_destroy(&test_lwp.lock);return NULL;
}
static void allocation_hook(void)
{
    CHECK(test_raw_depth==0);CHECK(linux_task_system_busy());
    CHECK(linux_task_system_quiesce()==EBUSY);
}
static void *allocation_failure(void *arg)
{
    struct drm_driver d={driver};struct drm_device dev={&d};
    struct drm_minor minor={&dev};struct drm_file priv={&minor};struct file fp={&priv};
    struct task_struct *task=NULL;(void)arg;prepare_lwp();
    CHECK(linux_task_entry_enter(NULL)==EINVAL);CHECK(!linux_task_system_busy());
    test_softint_fail=true;test_alloc_hook=allocation_hook;
    CHECK(drm_ioctl_shim(&fp,0,NULL)==ENOMEM);CHECK(driver_calls==0);
    CHECK(lwp_getspecific(task_key)==NULL&&!linux_task_system_busy());
    CHECK(linux_task_entry_enter(&task)==ENOMEM&&task==NULL);
    CHECK(!linux_task_system_busy());test_alloc_hook=NULL;test_softint_fail=false;
    mutex_destroy(&test_lwp.lock);return NULL;
}
static void *closed_admission(void *arg)
{
    struct drm_driver d={driver};struct drm_device dev={&d};
    struct drm_minor minor={&dev};struct drm_file priv={&minor};struct file fp={&priv};
    (void)arg;prepare_lwp();CHECK(drm_ioctl_shim(&fp,0,NULL)==EBUSY);
    CHECK(driver_calls==0&&lwp_getspecific(task_key)==NULL&&!linux_task_system_busy());
    mutex_destroy(&test_lwp.lock);return NULL;
}
static void thread(void *(*fn)(void *),void *arg)
{
    pthread_t t;CHECK(!pthread_create(&t,NULL,fn,arg));CHECK(!pthread_join(t,NULL));++scenarios;
}
int main(void)
{
    CHECK(!linux_task_system_init());thread(ioctls,NULL);
    CHECK(!linux_task_system_busy());thread(nested_entry,NULL);CHECK(!linux_task_system_busy());
    thread(allocation_failure,NULL);CHECK(!linux_task_system_busy());
    CHECK(!linux_task_system_quiesce());thread(closed_admission,NULL);linux_task_system_resume();
    thread(ioctls,(void *)1);CHECK(retained&&retained->lt_exited&&retained->lt_lwp==NULL&&retained->lt_refs==1);
    CHECK(linux_task_system_busy()&&linux_task_system_quiesce()==EBUSY);
    put_task_struct(retained);retained=NULL;CHECK(!linux_task_system_busy());
    /* Parallel user LWPs keep independent task identity, with balanced TLS
     * destruction and no resource admission after final quiescence. */
    {
        pthread_t t[8];unsigned int i;
        for(i=0;i<8;++i) {CHECK(!pthread_create(&t[i],NULL,ioctls,NULL));}
        for(i=0;i<8;++i) {CHECK(!pthread_join(t[i],NULL));}
        scenarios+=8;
    }
    CHECK(!linux_task_system_busy());CHECK(!linux_task_system_fini());
    printf("DRM_TASK_ENTRY_SCENARIOS=%u CHECKS=%u\n",scenarios,(unsigned int)checks);return 0;
}

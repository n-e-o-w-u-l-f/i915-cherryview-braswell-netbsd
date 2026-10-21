
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>
#include <stdatomic.h>
#include <stdbool.h>
#define __NetBSD__ 1
#define HP_I915_DIAG_CONNECTOR_ONESHOT 1
#define EXPORT_SYMBOL(x)
#define DRM_ERROR(...) do { diagnostic_logs++; } while (0)
#define DRM_DEBUG_KMS(...) do {} while (0)
#ifndef __UNCONST
#define __UNCONST(x) ((void *)(x))
#endif
#define kfree(x) free(x)
#define DRM_CONNECTOR_INITIALIZING 1
#define DRM_CONNECTOR_REGISTERED 2
#define DRM_CONNECTOR_UNREGISTERED 3
typedef struct { atomic_int v; } atomic_t;
#define ATOMIC_INIT(n) { .v = ATOMIC_VAR_INIT(n) }
static inline int atomic_cmpxchg(atomic_t *a,int expected,int desired) {
    atomic_compare_exchange_strong(&a->v,&expected,desired);
    return expected;
}
struct drm_device;
struct drm_connector;
struct intel_dp;
struct intel_connector;
struct drm_connector_funcs {
    int (*late_register)(struct drm_connector *);
    void (*early_unregister)(struct drm_connector *);
};
struct dp_aux { char *name; void *dev; int hw_initialized; int hw_registered; };
struct intel_dp { struct dp_aux aux; int aux_initialized; int aux_registered; };
struct drm_mode_object { int registered; };
struct drm_connector {
    struct drm_device *dev;
    struct drm_connector_funcs *funcs;
    struct drm_mode_object base;
    int mutex;
    int registration_state;
    int id, backlight_on, sysfs_on, debugfs_on, debugfs_i915;
    void *kdev;
    const char *name;
    struct intel_connector *owner;
};
struct intel_connector {struct drm_connector *connector; struct intel_dp *dp;};
struct drm_device {
    int registered, n, plane_on, crtc_on, encoder_on;
    struct drm_connector *items[4];
};
struct drm_connector_list_iter { struct drm_device *dev; int index; };
#define drm_connector_list_iter_begin(dev, it) do {(it)->dev=(dev);(it)->index=0;} while (0)
#define drm_connector_list_iter_end(it) do {} while (0)
#define drm_for_each_connector_iter(conn,it) for ( ; (it)->index < (it)->dev->n && ((conn)=(it)->dev->items[(it)->index])!=NULL ; (it)->index++ )
static int diagnostic_logs, late_aux_fail, backlight_fail_id=-1, i915_fail_at, i915_call_count;
static int backlight_start,backlight_stop,backlight_double,sysfs_add,sysfs_remove,debugfs_add,debugfs_remove,early_unreg_calls;
static int aux_init, aux_register, aux_unregister, aux_finish, cec_reg, cec_unreg;
static int mode_unregister_plane,mode_unregister_crtc,mode_unregister_encoder;
static atomic_t hp_i915_diag_connector_once=ATOMIC_INIT(1);
static struct intel_connector *to_intel_connector(struct drm_connector *c){return c->owner;}
static struct intel_dp *intel_attached_dp(struct intel_connector *c){return c->dp;}
static void *to_i915(struct drm_device *d){return (void *)d;}
static int i915_inject_probe_failure(void *x){(void)x;return i915_fail_at>0 && ++i915_call_count == i915_fail_at;}
static int intel_backlight_device_register(struct intel_connector *ic) {
    struct drm_connector *c=ic->connector;
    if(c->id==backlight_fail_id)return -ENOMEM;
    if(c->backlight_on)abort();
    c->backlight_on=1; backlight_start++; return 0;
}
static void intel_backlight_device_unregister(struct intel_connector *ic) {
    struct drm_connector *c=ic->connector;
    if(!c->backlight_on){backlight_double++;return;}
    c->backlight_on=0;backlight_stop++;
}
static void mutex_lock(int *p){(void)p;}
static void mutex_unlock(int *p){(void)p;}
static int drm_sysfs_connector_add(struct drm_connector *c){c->sysfs_on=1;sysfs_add++;return 0;}
static void drm_sysfs_connector_remove(struct drm_connector *c){if(!c->sysfs_on)abort();c->sysfs_on=0;sysfs_remove++;}
static void drm_debugfs_connector_add(struct drm_connector *c){c->debugfs_on=1;debugfs_add++;}
static void drm_debugfs_connector_remove(struct drm_connector *c){if(!c->debugfs_on)abort();c->debugfs_on=0;debugfs_remove++;}
static void drm_mode_object_register(struct drm_device *d,struct drm_mode_object *o){(void)d;o->registered=1;}
static void i915_debugfs_connector_add(struct drm_connector *c){c->debugfs_i915++;}
static void drm_dp_aux_init(struct dp_aux *a){aux_init++;a->hw_initialized=1;}
static void drm_dp_aux_fini(struct dp_aux *a){aux_finish++;a->hw_initialized=0;}
static int drm_dp_aux_register(struct dp_aux *a) {
    aux_register++;
    if(late_aux_fail)return -EIO;
    a->hw_registered=1;return 0;
}
static void drm_dp_aux_unregister(struct dp_aux *a) {
    if(!a->hw_registered)abort();
    aux_unregister++;a->hw_registered=0;drm_dp_aux_fini(a);
}
static void drm_dp_cec_register_connector(struct dp_aux *a,struct drm_connector *c){(void)a;(void)c;cec_reg++;}
static void drm_dp_cec_unregister_connector(struct dp_aux *a){(void)a;cec_unreg++;}
static int drm_plane_register_all(struct drm_device *d){d->plane_on=1;return 0;}
static int drm_crtc_register_all(struct drm_device *d){d->crtc_on=1;return 0;}
static int drm_encoder_register_all(struct drm_device *d){d->encoder_on=1;return 0;}
static void drm_plane_unregister_all(struct drm_device *d){d->plane_on=0;mode_unregister_plane++;}
static void drm_crtc_unregister_all(struct drm_device *d){d->crtc_on=0;mode_unregister_crtc++;}
static void drm_encoder_unregister_all(struct drm_device *d){d->encoder_on=0;mode_unregister_encoder++;}

/* VERBATIM FROM: dist/drm/i915/display/intel_connector.c */
int intel_connector_register(struct drm_connector *connector)
{
	struct intel_connector *intel_connector = to_intel_connector(connector);
	int ret;

	ret = intel_backlight_device_register(intel_connector);
	if (ret)
		goto err;

#if defined(__NetBSD__) && defined(HP_I915_DIAG_CONNECTOR_ONESHOT)
	/* Diagnostic-only, exactly one connector late_register failure per boot. */
	if (atomic_cmpxchg(&hp_i915_diag_connector_once, 1, 0) == 1) {
		DRM_ERROR("HP-I915-DIAG0064: one-shot connector failure -EFAULT\n");
		ret = -EFAULT;
		goto err_backlight;
	}
#endif

	if (i915_inject_probe_failure(to_i915(connector->dev))) {
		ret = -EFAULT;
		goto err_backlight;
	}

	return 0;

err_backlight:
	intel_backlight_device_unregister(intel_connector);
err:
	return ret;
}


/* VERBATIM FROM: dist/drm/i915/display/intel_connector.c */
void intel_connector_unregister(struct drm_connector *connector)
{
	struct intel_connector *intel_connector = to_intel_connector(connector);

	intel_backlight_device_unregister(intel_connector);
}


/* VERBATIM FROM: dist/drm/i915/display/intel_dp.c */
static void
intel_dp_aux_unregister(struct intel_dp *intel_dp)
{
#ifdef __NetBSD__
	if (!intel_dp->aux_registered)
		return;
#endif
	drm_dp_cec_unregister_connector(&intel_dp->aux);
	drm_dp_aux_unregister(&intel_dp->aux);
#ifdef __NetBSD__
	/* drm_dp_aux_unregister() invokes drm_dp_aux_fini() on NetBSD. */
	intel_dp->aux_registered = false;
	intel_dp->aux_initialized = false;
#endif
}


/* VERBATIM FROM: dist/drm/i915/display/intel_dp.c */
static void
intel_dp_aux_fini(struct intel_dp *intel_dp)
{
#ifdef __NetBSD__
	/* Encoder cleanup can precede connector_unregister on error. */
	intel_dp_aux_unregister(intel_dp);
	if (intel_dp->aux_initialized) {
		drm_dp_aux_fini(&intel_dp->aux);
		intel_dp->aux_initialized = false;
	}
#else
	drm_dp_aux_fini(&intel_dp->aux);
#endif
	kfree(__UNCONST(intel_dp->aux.name));
	intel_dp->aux.name = NULL;
}


/* VERBATIM FROM: dist/drm/i915/display/intel_dp.c */
static int
intel_dp_connector_register(struct drm_connector *connector)
{
	struct intel_dp *intel_dp = intel_attached_dp(to_intel_connector(connector));
	int ret;

#ifdef __NetBSD__
	/* A previous successful unregister already finalized the AUX locks. */
	if (!intel_dp->aux_initialized) {
		drm_dp_aux_init(&intel_dp->aux);
		intel_dp->aux_initialized = true;
	}
#endif

	ret = intel_connector_register(connector);
	if (ret)
		return ret;

	i915_debugfs_connector_add(connector);

#ifdef __NetBSD__
	DRM_DEBUG_KMS("registering %s bus for %s\n",
		      intel_dp->aux.name, connector->name);
#else
	DRM_DEBUG_KMS("registering %s bus for %s\n",
		      intel_dp->aux.name, connector->kdev->kobj.name);
#endif

	intel_dp->aux.dev = connector->kdev;
	ret = drm_dp_aux_register(&intel_dp->aux);
	if (ret) {
		/* AUX registration failed; the connector cannot be unregistered yet. */
		intel_connector_unregister(connector);
		return ret;
	}
#ifdef __NetBSD__
	intel_dp->aux_registered = true;
#endif
	drm_dp_cec_register_connector(&intel_dp->aux, connector);
	return 0;
}


/* VERBATIM FROM: dist/drm/i915/display/intel_dp.c */
static void
intel_dp_connector_unregister(struct drm_connector *connector)
{
	struct intel_dp *intel_dp = intel_attached_dp(to_intel_connector(connector));

	intel_dp_aux_unregister(intel_dp);
	intel_connector_unregister(connector);
}


/* VERBATIM FROM: dist/drm/drm_connector.c */
int drm_connector_register(struct drm_connector *connector)
{
	int ret = 0;

	if (!connector->dev->registered)
		return 0;

	mutex_lock(&connector->mutex);
	if (connector->registration_state != DRM_CONNECTOR_INITIALIZING)
		goto unlock;

	ret = drm_sysfs_connector_add(connector);
	if (ret)
		goto unlock;

	drm_debugfs_connector_add(connector);

	if (connector->funcs->late_register) {
		ret = connector->funcs->late_register(connector);
		if (ret)
			goto err_debugfs;
	}

	drm_mode_object_register(connector->dev, &connector->base);

	connector->registration_state = DRM_CONNECTOR_REGISTERED;
	goto unlock;

err_debugfs:
	drm_debugfs_connector_remove(connector);
	drm_sysfs_connector_remove(connector);
unlock:
	mutex_unlock(&connector->mutex);
	return ret;
}


/* VERBATIM FROM: dist/drm/drm_connector.c */
void drm_connector_unregister(struct drm_connector *connector)
{
	mutex_lock(&connector->mutex);
	if (connector->registration_state != DRM_CONNECTOR_REGISTERED) {
		mutex_unlock(&connector->mutex);
		return;
	}

	if (connector->funcs->early_unregister)
		connector->funcs->early_unregister(connector);

	drm_sysfs_connector_remove(connector);
	drm_debugfs_connector_remove(connector);

	connector->registration_state = DRM_CONNECTOR_UNREGISTERED;
	mutex_unlock(&connector->mutex);
}


/* VERBATIM FROM: dist/drm/drm_connector.c */
void drm_connector_unregister_all(struct drm_device *dev)
{
	struct drm_connector *connector;
	struct drm_connector_list_iter conn_iter;

	drm_connector_list_iter_begin(dev, &conn_iter);
	drm_for_each_connector_iter(connector, &conn_iter)
		drm_connector_unregister(connector);
	drm_connector_list_iter_end(&conn_iter);
}


/* VERBATIM FROM: dist/drm/drm_connector.c */
int drm_connector_register_all(struct drm_device *dev)
{
	struct drm_connector *connector;
	struct drm_connector_list_iter conn_iter;
	int ret = 0;

	drm_connector_list_iter_begin(dev, &conn_iter);
	drm_for_each_connector_iter(connector, &conn_iter) {
		ret = drm_connector_register(connector);
		if (ret)
			break;
	}
	drm_connector_list_iter_end(&conn_iter);

	if (ret)
		drm_connector_unregister_all(dev);
	return ret;
}


/* VERBATIM FROM: dist/drm/drm_mode_config.c */
int drm_modeset_register_all(struct drm_device *dev)
{
	int ret;

	ret = drm_plane_register_all(dev);
	if (ret)
		goto err_plane;

	ret = drm_crtc_register_all(dev);
	if  (ret)
		goto err_crtc;

	ret = drm_encoder_register_all(dev);
	if (ret)
		goto err_encoder;

	ret = drm_connector_register_all(dev);
	if (ret)
		goto err_connector;

	return 0;

err_connector:
	drm_encoder_unregister_all(dev);
err_encoder:
	drm_crtc_unregister_all(dev);
err_crtc:
	drm_plane_unregister_all(dev);
err_plane:
	return ret;
}


static struct drm_connector_funcs plain_funcs={intel_connector_register,intel_connector_unregister};
static struct drm_connector_funcs dp_funcs={intel_dp_connector_register,intel_dp_connector_unregister};
static int checks=0, fail=0, cases=0;
#define CHECK(x) do {checks++;if(!(x)){fail++;fprintf(stderr,"FAIL:%s:%d %s\n",__FILE__,__LINE__,#x);}}while(0)
static void reset(void){
    atomic_store(&hp_i915_diag_connector_once.v,1);
    diagnostic_logs=0;late_aux_fail=0;backlight_fail_id=-1;i915_fail_at=0;i915_call_count=0;
    backlight_start=backlight_stop=backlight_double=0;
    sysfs_add=sysfs_remove=debugfs_add=debugfs_remove=early_unreg_calls=0;
    aux_init=aux_register=aux_unregister=aux_finish=cec_reg=cec_unreg=0;
    mode_unregister_plane=mode_unregister_crtc=mode_unregister_encoder=0;
}
static void init(struct drm_device *dev,struct drm_connector *cs,
                 struct intel_connector *ics,int n) {
    memset(dev,0,sizeof(*dev));dev->registered=1;dev->n=n;
    for(int i=0;i<n;i++){
        memset(&cs[i],0,sizeof(cs[i]));memset(&ics[i],0,sizeof(ics[i]));
        cs[i].id=i;cs[i].dev=dev;cs[i].funcs=&plain_funcs;
        cs[i].owner=&ics[i];cs[i].registration_state=DRM_CONNECTOR_INITIALIZING;
        ics[i].connector=&cs[i];dev->items[i]=&cs[i];
    }
}
static void case_report(const char *name,int before) {
    printf("%s %s assertions=%d\n",fail==before?"PASS":"FAIL",name,checks);
    cases++;
}
int main(void){
    struct drm_device dev;
    struct drm_connector cs[3];
    struct intel_connector ics[3];
    struct intel_dp dp;
    int err,n;
    reset();init(&dev,cs,ics,2);n=fail;
    err=drm_connector_register(&cs[0]);
    CHECK(err==-EFAULT && diagnostic_logs==1);
    CHECK(cs[0].registration_state==DRM_CONNECTOR_INITIALIZING && !cs[0].sysfs_on && !cs[0].debugfs_on);
    CHECK(backlight_start==1 && backlight_stop==1 && !cs[0].backlight_on && backlight_double==0);
    err=drm_connector_register(&cs[1]);
    CHECK(err==0 && cs[1].registration_state==DRM_CONNECTOR_REGISTERED && cs[1].backlight_on);
    drm_connector_unregister(&cs[1]);
    CHECK(backlight_stop==2 && backlight_double==0 && !cs[1].sysfs_on && !cs[1].debugfs_on);
    case_report("one-shot-first-error-second-success",n);
    reset();init(&dev,cs,ics,2);n=fail;
    backlight_fail_id=0;
    err=drm_connector_register(&cs[0]);
    CHECK(err==-ENOMEM && backlight_start==0 && backlight_stop==0);
    CHECK(atomic_load(&hp_i915_diag_connector_once.v)==1 && diagnostic_logs==0);
    backlight_fail_id=-1;
    err=drm_connector_register(&cs[1]);
    CHECK(err==-EFAULT && backlight_start==1 && backlight_stop==1);
    case_report("backlight-failure-before-once",n);
    reset();init(&dev,cs,ics,2);n=fail;
    i915_fail_at=1;
    CHECK(drm_connector_register(&cs[0])==-EFAULT);
    CHECK(drm_connector_register(&cs[1])==-EFAULT);
    CHECK(backlight_start==2 && backlight_stop==2 && backlight_double==0);
    CHECK(i915_call_count==1 && diagnostic_logs==1);
    case_report("existing-i915-failure-after-once",n);
    reset();init(&dev,cs,ics,2);n=fail;
    CHECK(drm_modeset_register_all(&dev)==-EFAULT);
    CHECK(!dev.plane_on && !dev.crtc_on && !dev.encoder_on);
    CHECK(mode_unregister_plane==1 && mode_unregister_crtc==1 && mode_unregister_encoder==1);
    CHECK(cs[0].registration_state==DRM_CONNECTOR_INITIALIZING && !cs[0].backlight_on);
    CHECK(!cs[0].sysfs_on && !cs[0].debugfs_on && backlight_double==0);
    case_report("modeset-top-level-negative-cleanup",n);
    reset();init(&dev,cs,ics,2);n=fail;
    atomic_store(&hp_i915_diag_connector_once.v,0);i915_fail_at=2;
    CHECK(drm_connector_register_all(&dev)==-EFAULT);
    CHECK(cs[0].registration_state==DRM_CONNECTOR_UNREGISTERED);
    CHECK(cs[1].registration_state==DRM_CONNECTOR_INITIALIZING);
    CHECK(backlight_start==2 && backlight_stop==2 && backlight_double==0);
    CHECK(!cs[0].sysfs_on && !cs[1].sysfs_on && !cs[0].debugfs_on && !cs[1].debugfs_on);
    case_report("second-connector-fails-rollback-first",n);
    reset();init(&dev,cs,ics,1);n=fail;
    memset(&dp,0,sizeof(dp));dp.aux.name=strdup("AUX-test");
    CHECK(dp.aux.name!=NULL);
    ics[0].dp=&dp;cs[0].funcs=&dp_funcs;cs[0].name="eDP";
    CHECK(drm_connector_register(&cs[0])==-EFAULT);
    CHECK(aux_init==1 && dp.aux_initialized && !dp.aux_registered && aux_finish==0);
    CHECK(backlight_start==1 && backlight_stop==1 && !cs[0].sysfs_on && !cs[0].debugfs_on);
    /* Mimic a later driver error-unwind invoking the real source intel_dp_aux_fini */
    intel_dp_aux_fini(&dp);
    CHECK(aux_finish==1 && !dp.aux_initialized && dp.aux.name==NULL);
    CHECK(aux_unregister==0 && backlight_double==0);
    case_report("dp-fault-deferred-aux-lifetime",n);
    reset();init(&dev,cs,ics,1);n=fail;
    atomic_store(&hp_i915_diag_connector_once.v,0);
    memset(&dp,0,sizeof(dp));dp.aux.name=strdup("AUX-test");
    ics[0].dp=&dp;cs[0].funcs=&dp_funcs;cs[0].name="eDP";late_aux_fail=1;
    CHECK(drm_connector_register(&cs[0])==-EIO);
    CHECK(aux_init==1 && aux_register==1 && aux_finish==0);
    CHECK(backlight_start==1 && backlight_stop==1 && !dp.aux_registered && dp.aux_initialized);
    intel_dp_aux_fini(&dp);
    CHECK(aux_finish==1 && !dp.aux_initialized && dp.aux.name==NULL);
    CHECK(backlight_double==0);
    case_report("dp-aux-register-negative-deferred-finalize",n);
    reset();init(&dev,cs,ics,1);n=fail;
    atomic_store(&hp_i915_diag_connector_once.v,0);
    memset(&dp,0,sizeof(dp));dp.aux.name=strdup("AUX-test");
    ics[0].dp=&dp;cs[0].funcs=&dp_funcs;cs[0].name="eDP";
    CHECK(drm_connector_register(&cs[0])==0);
    CHECK(aux_init==1 && aux_register==1 && dp.aux_initialized && dp.aux_registered && cec_reg==1);
    drm_connector_unregister(&cs[0]);
    CHECK(aux_unregister==1 && aux_finish==1 && !dp.aux_registered && !dp.aux_initialized);
    CHECK(backlight_stop==1 && backlight_double==0);
    intel_dp_aux_fini(&dp);
    CHECK(aux_finish==1 && dp.aux.name==NULL);
    case_report("dp-normal-unregister-one-finalize",n);
    reset();init(&dev,cs,ics,1);n=fail;
    dev.registered=0;
    CHECK(drm_connector_register(&cs[0])==0);
    CHECK(atomic_load(&hp_i915_diag_connector_once.v)==1 && backlight_start==0);
    case_report("not-yet-device-registered",n);
    printf("SUMMARY cases=%d assertions=%d failures=%d\n",cases,checks,fail);
    return fail?2:0;
}

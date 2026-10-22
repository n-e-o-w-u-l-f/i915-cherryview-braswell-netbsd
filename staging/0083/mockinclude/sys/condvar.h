#ifndef TEST_SYS_CONDVAR_H
#define TEST_SYS_CONDVAR_H
#include <pthread.h>
#include <sys/mutex.h>
typedef pthread_cond_t kcondvar_t;
static inline void cv_init(kcondvar_t *p, const char *name) { (void)name; (void)pthread_cond_init(p, NULL); }
static inline void cv_destroy(kcondvar_t *p) { (void)pthread_cond_destroy(p); }
static inline void cv_wait(kcondvar_t *p, kmutex_t *m) { (void)pthread_cond_wait(p, m); }
static inline void cv_broadcast(kcondvar_t *p) { (void)pthread_cond_broadcast(p); }
#endif

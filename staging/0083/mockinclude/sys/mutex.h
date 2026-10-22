#ifndef TEST_SYS_MUTEX_H
#define TEST_SYS_MUTEX_H
#include <pthread.h>
typedef pthread_mutex_t kmutex_t;
#define MUTEX_DEFAULT 0
#define IPL_NONE 0
static inline void mutex_init(kmutex_t *p, int type, int ipl) { (void)type; (void)ipl; (void)pthread_mutex_init(p, NULL); }
static inline void mutex_destroy(kmutex_t *p) { (void)pthread_mutex_destroy(p); }
static inline void mutex_enter(kmutex_t *p) { (void)pthread_mutex_lock(p); }
static inline void mutex_exit(kmutex_t *p) { (void)pthread_mutex_unlock(p); }
#endif

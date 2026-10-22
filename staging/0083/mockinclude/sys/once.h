#ifndef TEST_SYS_ONCE_H
#define TEST_SYS_ONCE_H
#include <pthread.h>
typedef pthread_once_t once_t;
#define ONCE_DECL(o) once_t o = PTHREAD_ONCE_INIT
/* Equivalent success-only simplified model. */
#define RUN_ONCE(o, fn) (pthread_once((o), (void (*)(void))(fn)), 0)
#endif

#ifndef TEST_SYS_KMEM_H
#define TEST_SYS_KMEM_H
#include <stddef.h>
void *test_kmem_zalloc(size_t, int);
void test_kmem_free(void *, size_t);
#define KM_SLEEP 1
#define kmem_zalloc test_kmem_zalloc
#define kmem_free test_kmem_free
#endif

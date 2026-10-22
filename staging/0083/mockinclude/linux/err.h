#ifndef TEST_LINUX_ERR_H
#define TEST_LINUX_ERR_H
#include <stdint.h>
#define ERR_PTR(err) ((void *)(intptr_t)(err))
#define PTR_ERR(ptr) ((long)(intptr_t)(ptr))
#define IS_ERR(ptr) ((uintptr_t)(ptr) >= (uintptr_t)-4095)
#endif

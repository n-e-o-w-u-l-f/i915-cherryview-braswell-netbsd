/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */
#ifndef _LINUX_MM_NETBSD_H_
#define _LINUX_MM_NETBSD_H_
#include <sys/types.h>
#include <linux/vma_netbsd.h>
#include <linux/mapping_netbsd.h>
struct uvm_object;
struct uvm_mmap_request;
/* Native positive errno; successful output transfers one real UVM object
 * reference and one exactly-once request transaction to the Native caller. */
int linux_uvm_mmap_prepare(struct linux_file *, off_t *, size_t, int,
    int *, int *, struct uvm_object **, int *, struct uvm_mmap_request **);
unsigned long vm_mmap(struct linux_file *, unsigned long, unsigned long,
    unsigned long, unsigned long, unsigned long);
int linux_shmem_mmap(struct linux_file *, struct vm_area_struct *);
unsigned long linux_shmem_get_unmapped_area(struct linux_file *, unsigned long,
    unsigned long, unsigned long, unsigned long);
struct vm_area_struct *find_vma(struct mm_struct *, unsigned long);
#endif

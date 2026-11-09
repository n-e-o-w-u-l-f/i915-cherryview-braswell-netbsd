/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef _LINUX_NATIVE_RUNTIME_OWNER_NETBSD_H_
#define _LINUX_NATIVE_RUNTIME_OWNER_NETBSD_H_
/* Lifecycle declarations only; no modern VFS types enter legacy clients. */
int linux_file_system_init(void);
int linux_file_system_fini(void);
int linux_mm_identity_init(void);
int linux_mm_identity_quiesce(void);
void linux_mm_identity_resume(void);
int linux_mm_identity_fini(void);
#endif

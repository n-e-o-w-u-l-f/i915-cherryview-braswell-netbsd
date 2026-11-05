/* SPDX-License-Identifier: BSD-2-Clause */
/* Copyright (c) 2026 n-e-o-w-u-l-f */

#include <sys/param.h>
#include <uvm/uvm_extern.h>
#include <uvm/uvm_pmap.h>
#include <linux/fs_netbsd.h>
#include <linux/file_api_netbsd.h>
#include <linux/vma_netbsd.h>

/* Source VM flags retain their Linux numeric meaning; protections passed to
 * the actual pmap producer use native access and cache encodings explicitly.
 */
__CTASSERT(VM_READ == VM_PROT_READ);
__CTASSERT(VM_WRITE == VM_PROT_WRITE);
__CTASSERT(VM_EXEC == VM_PROT_EXECUTE);

void
vma_set_file(struct vm_area_struct *vma, struct linux_file *file)
{
	struct linux_file *previous = vma->vm_file;

	/* Taking the new reference first also makes self-assignment safe. */
	if (file != NULL)
		get_file(file);
	vma->vm_file = file;
	if (previous != NULL)
		fput(previous);
}

pgprot_t
vm_get_page_prot(unsigned long flags)
{
	vm_prot_t access = flags & VM_ACCESS_FLAGS;

	/* Linux PAGE_COPY starts private writable mappings read-only.  Granting
	 * direct write here would mutate the shared backing before a COW fault.
	 */
	if ((flags & VM_SHARED) == 0)
		access &= ~VM_PROT_WRITE;
	return access | PMAP_WRITE_BACK;
}

pgprot_t
vma_get_page_prot(const struct vm_area_struct *vma)
{
	return vm_get_page_prot(vma->vm_flags);
}

static void
linux_pgprot_validate(pgprot_t protection)
{
	if (__predict_false((protection & ~(VM_PROT_ALL | PMAP_CACHE_MASK)) != 0))
		panic("untranslated Linux hardware PTE bits in native pgprot");
}

pgprot_t
pgprot_writecombine(pgprot_t protection)
{
	linux_pgprot_validate(protection);
	return (protection & ~PMAP_CACHE_MASK) | PMAP_WRITE_COMBINE;
}

pgprot_t
pgprot_noncached(pgprot_t protection)
{
	linux_pgprot_validate(protection);
	return (protection & ~PMAP_CACHE_MASK) | PMAP_NOCACHE;
}

pgprot_t
pgprot_decrypted(pgprot_t protection)
{
	/* This is a native access/cache descriptor, not a Linux hardware PTE.
	 * Encryption attributes belong to the actual machine pmap producer;
	 * there is no synthetic Linux C-bit to clear in this source adapter.
	 */
	linux_pgprot_validate(protection);
	return protection;
}

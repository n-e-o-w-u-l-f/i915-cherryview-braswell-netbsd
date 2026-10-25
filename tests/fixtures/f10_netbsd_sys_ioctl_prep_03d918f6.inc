		if (com&IOC_IN) {
			if (size) {
				error = copyin(SCARG(uap, data), data, size);
				if (error) {
					goto out;
				}
				/*
				 * The data between size and alloc_size has
				 * not been overwritten.  It shouldn't matter
				 * but let's clear that anyway.
				 */
				if (__predict_false(size < alloc_size)) {
					memset((char *)data+size, 0,
					    alloc_size - size);
				}
				ktrgenio(SCARG(uap, fd), UIO_WRITE,
				    SCARG(uap, data), size, 0);
			} else {
				*(void **)data = SCARG(uap, data);
			}
		} else if ((com&IOC_OUT) && size) {
			/*
			 * Zero the buffer so the user always
			 * gets back something deterministic.
			 */
			memset(data, 0, zero_size(size));
		} else if (com&IOC_VOID) {
			*(void **)data = SCARG(uap, data);
		}

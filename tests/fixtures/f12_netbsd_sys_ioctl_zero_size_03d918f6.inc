	if ((com >> IOCPARM_SHIFT) == 0)  {
		/* UNIX-style ioctl. */
		data = SCARG(uap, data);
	} else {

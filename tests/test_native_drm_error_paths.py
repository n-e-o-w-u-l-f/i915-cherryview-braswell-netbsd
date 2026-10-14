#!/usr/bin/env python3
"""Source-bound error-path regressions; no native C compilation/runtime claim."""
from pathlib import Path
import unittest

SOURCE = (Path(__file__).resolve().parents[1] / 'compat/native-drm/drm_cdevsw.c').read_text()


class NativeDRMErrors(unittest.TestCase):
    def test_iovec_multiply_follows_range_check(self):
        body = SOURCE.split('drm_native_read_events(struct linux_file *file, struct uio *uio)')[1].split('static int\ndrm_native_read(')[0]
        self.assertLess(body.index('SIZE_MAX / sizeof(*saved_iov)'), body.index('allocation_size = (size_t)uio->uio_iovcnt'))

    def test_all_errors_preserve_already_delivered_events(self):
        body = SOURCE.split('drm_native_read_events(struct linux_file *file, struct uio *uio)')[1].split('static int\ndrm_native_read(')[0]
        tail = body.split('out:')[1]
        self.assertIn('if (original_resid != uio->uio_resid)', tail)
        self.assertIn('return 0;', tail)
        self.assertLess(tail.index('return 0;'), tail.index('return drm_native_error(error);'))

    def test_open_cleanup_has_one_owner_per_acquisition(self):
        body = SOURCE.split('drm_native_open(dev_t devno')[1].split('static int\ndrm_native_close(')[0]
        cleanup = body.split('out_file:')[1]
        for call in ('fput(file);', 'fd_abort(curproc, native, fd);',
                     'drm_minor_release(dminor);', 'linux_task_entry_leave(&task);'):
            self.assertEqual(cleanup.count(call), 1)
        self.assertLess(body.index('ops->open('), body.index('file->netbsd_opened = true;'))
        self.assertLess(body.index('file->netbsd_opened = true;'), body.index('linux_file_poll_init(file)'))
        # fd_clone at the pinned NetBSD revision affixes the fd and returns
        # EMOVEFD unconditionally. It has no recoverable failure branch.
        self.assertIn('KASSERT(error == EMOVEFD);', body)

    def test_failed_copy_restores_uio_and_requeues_event(self):
        body = SOURCE.split('error = -uiomove(')[1].split('kfree(event);')[0]
        self.assertLess(body.index('*uio = saved_uio;'), body.index('drm_native_put_back(priv, event);'))


if __name__ == '__main__':
    unittest.main()

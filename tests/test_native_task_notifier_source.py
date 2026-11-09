"""Source-only composition guards. Actual lifecycle C runs exclusively on HP."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'compat/native-task-notifier'
spec = importlib.util.spec_from_file_location('native_task_notifier', PACKAGE / 'generate.py')
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


class TaskNotifierSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before, cls.after, cls.diff, cls.metadata = generator.sources()

    def test_exact_frozen_before_and_deterministic_after(self):
        self.assertEqual({p: hashlib.sha256(v).hexdigest() for p, v in self.before.items()}, generator.BEFORE)
        self.assertEqual((self.before, self.after, self.diff, self.metadata), generator.sources())
        self.assertEqual(set(self.after), {generator.TASK, generator.HEADER})

    def test_coherent_real_native_queue_owner(self):
        task = self.after[generator.TASK].decode()
        header = self.after[generator.HEADER].decode()
        self.assertNotIn('softint_', task)
        self.assertNotIn('lt_softint', header)
        self.assertEqual(task.count('workqueue_create('), 1)
        self.assertIn('NULL, PRI_NONE, IPL_HIGH, WQ_MPSAFE)', task)
        self.assertIn('struct work lt_notify_work;', header)
        self.assertIn('if (task->lt_notify_again)', task)
        self.assertLess(task.index('kmem_free(task, sizeof(*task));'), task.index('linux_task_unreserve();', task.index('kmem_free(task, sizeof(*task));')))

    def test_irq_last_put_does_not_sleep_or_free(self):
        task = self.after[generator.TASK].decode()
        put = task.split('void\nlinux_put_task_struct(', 1)[1].split('struct lwp *\nlinux_task_lwp', 1)[0]
        self.assertIn('linux_task_notify_locked(task);', put)
        for forbidden in ('workqueue_wait(', 'kmem_', 'ASSERT_SLEEPABLE()', 'cv_destroy('):
            self.assertNotIn(forbidden, put)

    def test_internal_owner_clone_does_not_open_or_use_external_admission(self):
        task = self.after[generator.TASK].decode()
        owner = task.split('linux_task_alloc_owner_wait(', 1)[1].split('void\nlinux_task_attach_current', 1)[0]
        for forbidden in ('linux_task_reserve(', 'TASK_SYSTEM_OPEN', 'task_system_state ='):
            self.assertNotIn(forbidden, owner)
        self.assertIn('task_count == UINT_MAX', owner)
        self.assertIn('parent_spare->lt_refs == 1', owner)
        self.assertIn('atomic_inc_uint(&task_count);', owner)

    def test_fini_drain_does_not_replace_busy_gate(self):
        task = self.after[generator.TASK].decode()
        fini = task.split('linux_task_system_fini(void)', 1)[1].split('static struct task_struct *', 1)[0]
        self.assertLess(fini.index('workqueue_wait('), fini.index('linux_task_system_quiesce();'))
        self.assertLess(fini.index('if (error != 0)'), fini.index('workqueue_destroy('))
        self.assertLess(fini.index('workqueue_destroy('), fini.index('lwp_specific_key_delete('))

    def test_nonunique_source_anchor_is_rejected(self):
        with self.assertRaises(ValueError):
            generator.once('anchor anchor', 'anchor', 'changed')

    def test_same_shape_tampered_baseline_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            for rel in ('compat/native-runtime/task/linux_task.c', 'compat/native-runtime/task/task_netbsd.h',
                        'compat/native-fatal/task-runtime.patch', 'patches/0037-netbsd-linux-drm-ioctl-task-entry.patch'):
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / rel).read_bytes().replace(b'\r\n', b'\n'))
            target = root / 'compat/native-runtime/task/linux_task.c'
            data = target.read_bytes()
            self.assertEqual(data.count(b'candidate, not installed'), 1)
            target.write_bytes(data.replace(b'candidate, not installed', b'candidate, now installed'))
            with patch.object(generator, 'ROOT', root), self.assertRaisesRegex(ValueError, 'frozen0037 mismatch'):
                generator.sources()


if __name__ == '__main__':
    unittest.main()

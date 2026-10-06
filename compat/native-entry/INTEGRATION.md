# Native task references at DRM ioctl entry

Apply `patches/0037-netbsd-linux-drm-ioctl-task-entry.patch` after0032 and
0035, preserving the real0035 kernel backend. Its generator validates the
source hashes and adds the shared enter/leave declarations before the
actual native driver call. The full HP stage preparation and regression
runners include the patch and test.

`tools/verify_linux_task_entry_chain.py` verifies the entire actual0037
source contract and reverses the generated patch in a disposable snapshot.
Historical0032 and current fatal regression fixtures then validate their
exact prior source contracts without changing the actual shared stage.

Run only on HP:

```sh
python3 tests/test_linux_task_entry.py --netbsd-tree /root/netbsd-src-ref
python3 tools/build_hp_task_entry.py --output /root/hp-driver-port-20261005/new-native-entry-proof
```

The build helper requires a fresh proof directory and the exact before
hashes in the isolated `netbsd-full-linux` stage; it preserves its applied
source and FAILED report on an adapter compilation failure. Do not rerun
it against already changed sources or hide the modern-header failure with
an older DRM header prefix. The original kernel and reference remain intact.

Every accepted entry owns one handle reference. Enter/leave must occur in
sleepable current-LWP context, before/after driver locks. Leave retains the
LWP owner until actual exit; nested entries preserve identical task identity.
Calls after quiescence return EBUSY. Module/code owners must separately
exclude new calls before deleting keys or unloading callback code.

Only the native ioctl shim is wired in this patch. Other native driver/file,
system-workqueue and PM/attach entries, modern file/poll/UVM bridges and
complete code-owner rundown remain open. See
[the exact native compilation limits](../../docs/DRM_TASK_ENTRY_NETBSD_20261006.md).

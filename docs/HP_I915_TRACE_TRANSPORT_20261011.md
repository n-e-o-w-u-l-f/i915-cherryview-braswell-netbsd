# HP i915 trace transport — 2026-10-11

## IST

- F77 uses `wsdisplay0 at genfb0` as its console; i915drmkms is disabled.
- The boot log contains no attached `comN` console. Generic `/dev/tty00` …
  `/dev/tty03` nodes alone do not establish a usable physical serial console.
- `kern.debug` is configured to write to `/var/log/messages`.
- The persistent Remote Desktop Commander agent is alive in the F77
  multi-user environment, but F83 previously failed before that agent and
  local syslog returned. It is therefore not an independent early-KMS trace
  transport.
- F83 and F84 both reached the same black-panel/backlight symptom; there is
  still no boundary trace for G04–G09.

## ÄNDERUNGEN

No kernel, boot-menu, i915 register, firmware or syslog configuration was
changed. The result above is a read-only transport audit of the recovered F77
system.

## NEXT

1. Provide an off-box syslog receiver reachable before i915 takeover, or a
   physically attached serial console. A generic `/dev/tty00` node is not
   sufficient evidence.
2. From F77, send and receive a tagged `kern.debug` test record through that
   transport before building any graphics candidate.
3. Add only G01–G09 boundary markers to a new isolated trace kernel and
   preserve the off-box trace. No display register ordering changes belong in
   that candidate.
4. Add exactly one new manual boot entry with F77 as default and return to
   F77 after the test. Never boot F16.0; F83 and F84 remain removed.

Until step 2 is proved, a further i915 test would repeat an unobservable
failure and cannot identify the black-screen root cause.

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
- The HP and a separate Tailnet host can reach one another directly. This
  proves only post-boot IP connectivity: Tailscale and ordinary `syslogd` are
  userland services, so their availability during the built-in i915 attach is
  not established.
- NetBSD 11 forwards ordinary UDP syslog only to the standard syslog port.
  Its alternate-port syntax applies to TLS forwarding, not UDP. A temporary
  unprivileged UDP receiver therefore could not form a valid NetBSD receiver;
  it was stopped and removed, and the F77 syslog configuration was restored
  byte-for-byte.
- F83 and F84 both reached the same black-panel/backlight symptom; there is
  still no boundary trace for G04–G09.

## ÄNDERUNGEN

No kernel, boot-menu, i915 register or firmware configuration was changed.
The one temporary syslog-receiver experiment was reverted immediately after
its NetBSD UDP-port limitation was established; it left no listener, log file,
or syslog configuration change on either machine.

## NEXT

1. Provide and configure a physically attached serial console as the
   bootloader and kernel console. A generic `/dev/tty00` node is not
   sufficient evidence. This is the only currently justified early-attach
   transport; ordinary Tailscale, RDC, and post-boot syslog alone do not meet
   this gate.
2. Capture a tagged F77 boot marker on that independent console before
   building any graphics candidate. An optional network receiver is useful
   only after a candidate's G01 marker proves it is live before display
   takeover.
3. Add only short G01–G09 boundary markers to a new isolated trace kernel and
   preserve the off-box trace. No display register ordering changes belong in
   that candidate.
4. Add exactly one new manual boot entry with F77 as default and return to
   F77 after the test. Never boot F16.0; F83 and F84 remain removed.

Until step 2 is proved, a further i915 test would repeat an unobservable
failure and cannot identify the black-screen root cause.

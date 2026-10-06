# Frozen PWM consumer and complete-type dependency checkpoint

The selected CONFIG_PWM-disabled consumer profile retains the actual Linux
types, state/duty helpers, errors and release bodies. Enabled PWM/LPSS lookup,
provider/owner lifetimes remain OPEN and are explicitly rejected at compilation.
No enabled provider is replaced with the disabled profile. Native PWM identifiers
coexist through three private Linux bindings. OF is an opaque prototype tag only;
no device_node fields or OF provider are invented. Modern drm_atomic.h includes
the actual native completion dependency for its three embedded completion fields.
All compiler/test execution is restricted to HP. Full410/kernel/runtime and
physical backlight/OF-provider acceptance remain OPEN.

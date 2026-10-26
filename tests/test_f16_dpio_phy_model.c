#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"CHECK_FAILED %s\n",#x); abort(); } } while (0)
typedef uint32_t u32;
enum dpio_phy { DPIO_PHY0, DPIO_PHY1 };
#define IOSF_PORT_DPIO 0x12
#define IOSF_PORT_DPIO_2 0x1a
#define DPIO_DEVFN 0x20
#define SB_MRD_NP 0
#define SB_MWR_NP 1
struct drm_i915_private { int platform, dpio_phy_iosf_port[2], calls, last_port, last_opcode, last_reg; };
#define IS_CHERRYVIEW(d) ((d)->platform == 2)
#define IS_VALLEYVIEW(d) ((d)->platform == 1)
#define WARN(cond, ...) do { (void)(cond); } while (0)
static int vlv_sideband_rw(struct drm_i915_private *i915, u32 devfn,u32 port,u32 opcode,u32 addr,u32 *val) {
    CHECK(devfn == DPIO_DEVFN);CHECK(port==IOSF_PORT_DPIO || port==IOSF_PORT_DPIO_2);
    i915->calls++; i915->last_port=(int)port; i915->last_opcode=(int)opcode; i915->last_reg=(int)addr;
    if (opcode==SB_MRD_NP) *val=0xabcde000u|port;
    return 0;
}
/* BEGIN PUBLISHED F16 ADDED CODE */
static int
vlv_dpio_port_for_phy(struct drm_i915_private *i915, enum dpio_phy phy)
{
	int expected = -1;

	if (IS_CHERRYVIEW(i915)) {
		if (phy == DPIO_PHY0)
			expected = IOSF_PORT_DPIO_2;
		else if (phy == DPIO_PHY1)
			expected = IOSF_PORT_DPIO;
	} else if (IS_VALLEYVIEW(i915) && phy == DPIO_PHY0) {
		expected = IOSF_PORT_DPIO;
	}

	if (expected < 0) {
		WARN(1, "unsupported DPIO PHY %d\n", phy);
		return -1;
	}
	if (i915->dpio_phy_iosf_port[phy] != expected) {
		WARN(1, "DPIO PHY %d IOSF port not initialised\n", phy);
		return -1;
	}
	return expected;
}

u32
vlv_dpio_phy_read(struct drm_i915_private *i915, enum dpio_phy phy, int reg)
{
	int port = vlv_dpio_port_for_phy(i915, phy);
	u32 val = 0;

	if (port < 0)
		return 0xffffffff;

	vlv_sideband_rw(i915, DPIO_DEVFN, port, SB_MRD_NP, reg, &val);
	WARN(val == 0xffffffff, "DPIO PHY%d read reg 0x%x == 0x%x\n",
	    phy, reg, val);
	return val;
}

void
vlv_dpio_phy_write(struct drm_i915_private *i915, enum dpio_phy phy,
    int reg, u32 val)
{
	int port = vlv_dpio_port_for_phy(i915, phy);

	if (port < 0)
		return;

	vlv_sideband_rw(i915, DPIO_DEVFN, port, SB_MWR_NP, reg, &val);
}
/* END PUBLISHED F16 ADDED CODE */
int main(void) {
 struct drm_i915_private chv={.platform=2,.dpio_phy_iosf_port={0x1a,0x12}};
 CHECK(vlv_dpio_phy_read(&chv,DPIO_PHY0,0x51)==(0xabcde000u|0x1a));
 CHECK(chv.calls==1 && chv.last_port==0x1a && chv.last_opcode==SB_MRD_NP && chv.last_reg==0x51);
 vlv_dpio_phy_write(&chv,DPIO_PHY1,0x52,0x12345678);
 CHECK(chv.calls==2 && chv.last_port==0x12 && chv.last_opcode==SB_MWR_NP && chv.last_reg==0x52);
 struct drm_i915_private vlv={.platform=1,.dpio_phy_iosf_port={0x12,0x12}};
 CHECK(vlv_dpio_phy_read(&vlv,DPIO_PHY0,0x62)==(0xabcde000u|0x12));
 CHECK(vlv.calls==1 && vlv.last_port==0x12);
 CHECK(vlv_dpio_phy_read(&vlv,DPIO_PHY1,0x63)==0xffffffff && vlv.calls==1);
 vlv_dpio_phy_write(&vlv,DPIO_PHY1,0x63,0);
 CHECK(vlv.calls==1);
 CHECK(vlv_dpio_phy_read(&chv,(enum dpio_phy)-1,0)==0xffffffff && chv.calls==2);
 CHECK(vlv_dpio_phy_read(&chv,(enum dpio_phy)2,0)==0xffffffff && chv.calls==2);
 struct drm_i915_private uninit={.platform=2,.dpio_phy_iosf_port={0,0}};
 CHECK(vlv_dpio_phy_read(&uninit,DPIO_PHY0,0)==0xffffffff && uninit.calls==0);
 vlv_dpio_phy_write(&uninit,DPIO_PHY1,0,0); CHECK(uninit.calls==0);
 struct drm_i915_private unsupported={.platform=3,.dpio_phy_iosf_port={0x1a,0x12}};
 CHECK(vlv_dpio_phy_read(&unsupported,DPIO_PHY0,0)==0xffffffff && unsupported.calls==0);
 puts("F16_EXPLICIT_DPIO_PHY_SOURCE_BASELINE_PASS");
}

/* Source-derived F17 CHV signal level mock harness, NOT NetBSD kernel. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
typedef uint32_t u32;
#define CHECK(e) do { if (!(e)) { fprintf(stderr,"CHECK_FAILED %s\n",#e); abort(); } } while (0)
enum dpio_phy { DPIO_PHY0=0, DPIO_PHY1=1 };
enum dpio_channel { DPIO_CH0=0, DPIO_CH1=1 };
enum { PORT_B=1, PORT_C=2, PORT_D=3 };
struct drm_i915_private { int active,lock,gets,puts,reads,writes,port,phy,ch; };
struct intel_digital_port { struct {int port;} base; };
struct intel_crtc_config { int lane_count; };
struct intel_crtc { int pipe; struct intel_crtc_config *config; };
struct intel_encoder {
    struct { struct drm_i915_private *dev; struct intel_crtc *crtc; } base;
    struct intel_digital_port *digital;
};
static struct drm_i915_private *to_i915(struct drm_i915_private *d) {return d;}
static struct intel_crtc *to_intel_crtc(struct intel_crtc *c) {return c;}
static struct intel_digital_port *enc_to_dig_port(struct intel_encoder *e) {return e->digital;}
static enum dpio_channel vlv_dport_to_channel(struct intel_digital_port *d) {
    CHECK(d->base.port==PORT_B || d->base.port==PORT_C || d->base.port==PORT_D);
    return d->base.port==PORT_C ? DPIO_CH1 : DPIO_CH0;
}
static enum dpio_phy vlv_dport_to_phy(struct intel_digital_port *d) {
    CHECK(d->base.port==PORT_B || d->base.port==PORT_C || d->base.port==PORT_D);
    return d->base.port==PORT_D ? DPIO_PHY1 : DPIO_PHY0;
}
static void vlv_dpio_get(struct drm_i915_private *d) {
    CHECK(!d->lock);d->lock=1;d->gets++;
}
static void vlv_dpio_put(struct drm_i915_private *d) {
    CHECK(d->lock);d->lock=0;d->puts++;
}
#define REG(ch,num) (1000+(((int)(ch))<<8)+(num))
#define VLV_PCS01_DW10(ch) REG(ch,10)
#define VLV_PCS23_DW10(ch) REG(ch,11)
#define VLV_PCS01_DW9(ch) REG(ch,12)
#define VLV_PCS23_DW9(ch) REG(ch,13)
#define CHV_TX_DW4(ch,i) REG(ch,30+(i))
#define CHV_TX_DW2(ch,i) REG(ch,40+(i))
#define CHV_TX_DW3(ch,i) REG(ch,50+(i))
#define DPIO_PCS_SWING_CALC_TX0_TX2 (1u<<0)
#define DPIO_PCS_SWING_CALC_TX1_TX3 (1u<<1)
#define DPIO_PCS_TX1DEEMP_MASK (1u<<2)
#define DPIO_PCS_TX2DEEMP_MASK (1u<<3)
#define DPIO_PCS_TX1DEEMP_9P5 (1u<<4)
#define DPIO_PCS_TX2DEEMP_9P5 (1u<<5)
#define DPIO_PCS_TX1MARGIN_MASK (1u<<6)
#define DPIO_PCS_TX2MARGIN_MASK (1u<<7)
#define DPIO_PCS_TX1MARGIN_000 (1u<<8)
#define DPIO_PCS_TX2MARGIN_000 (1u<<9)
#define DPIO_SWING_DEEMPH9P5_MASK (1u<<10)
#define DPIO_SWING_DEEMPH9P5_SHIFT 12
#define DPIO_SWING_MARGIN000_MASK (1u<<11)
#define DPIO_SWING_MARGIN000_SHIFT 13
#define DPIO_UNIQ_TRANS_SCALE_SHIFT 16
#define DPIO_TX_UNIQ_TRANS_SCALE_EN (1u<<27)
static u32 vlv_dpio_phy_read(struct drm_i915_private *d,enum dpio_phy phy,int reg) {
    CHECK(d->lock && d->active);CHECK((int)phy==d->phy);
    CHECK(((reg-1000)>>8)==d->ch);d->reads++;
    return 0x00400001u;
}
static void vlv_dpio_phy_write(struct drm_i915_private *d,enum dpio_phy phy,int reg,u32 value) {
    CHECK(d->lock && d->active);CHECK((int)phy==d->phy);
    CHECK(((reg-1000)>>8)==d->ch);(void)value;d->writes++;
}

/* BEGIN F17 EXACT PATCHED NATIVE FUNCTION */
void chv_set_phy_signal_level(struct intel_encoder *encoder,
			      u32 deemph_reg_value, u32 margin_reg_value,
			      bool uniq_trans_scale)
{
	struct drm_i915_private *dev_priv = to_i915(encoder->base.dev);
	struct intel_digital_port *dport = enc_to_dig_port(encoder);
	struct intel_crtc *intel_crtc = to_intel_crtc(encoder->base.crtc);
	enum dpio_channel ch = vlv_dport_to_channel(dport);
	enum dpio_phy phy = vlv_dport_to_phy(dport);
	u32 val;
	int i;

	vlv_dpio_get(dev_priv);

	/* Clear calc init */
	val = vlv_dpio_phy_read(dev_priv, phy, VLV_PCS01_DW10(ch));
	val &= ~(DPIO_PCS_SWING_CALC_TX0_TX2 | DPIO_PCS_SWING_CALC_TX1_TX3);
	val &= ~(DPIO_PCS_TX1DEEMP_MASK | DPIO_PCS_TX2DEEMP_MASK);
	val |= DPIO_PCS_TX1DEEMP_9P5 | DPIO_PCS_TX2DEEMP_9P5;
	vlv_dpio_phy_write(dev_priv, phy, VLV_PCS01_DW10(ch), val);

	if (intel_crtc->config->lane_count > 2) {
		val = vlv_dpio_phy_read(dev_priv, phy, VLV_PCS23_DW10(ch));
		val &= ~(DPIO_PCS_SWING_CALC_TX0_TX2 | DPIO_PCS_SWING_CALC_TX1_TX3);
		val &= ~(DPIO_PCS_TX1DEEMP_MASK | DPIO_PCS_TX2DEEMP_MASK);
		val |= DPIO_PCS_TX1DEEMP_9P5 | DPIO_PCS_TX2DEEMP_9P5;
		vlv_dpio_phy_write(dev_priv, phy, VLV_PCS23_DW10(ch), val);
	}

	val = vlv_dpio_phy_read(dev_priv, phy, VLV_PCS01_DW9(ch));
	val &= ~(DPIO_PCS_TX1MARGIN_MASK | DPIO_PCS_TX2MARGIN_MASK);
	val |= DPIO_PCS_TX1MARGIN_000 | DPIO_PCS_TX2MARGIN_000;
	vlv_dpio_phy_write(dev_priv, phy, VLV_PCS01_DW9(ch), val);

	if (intel_crtc->config->lane_count > 2) {
		val = vlv_dpio_phy_read(dev_priv, phy, VLV_PCS23_DW9(ch));
		val &= ~(DPIO_PCS_TX1MARGIN_MASK | DPIO_PCS_TX2MARGIN_MASK);
		val |= DPIO_PCS_TX1MARGIN_000 | DPIO_PCS_TX2MARGIN_000;
		vlv_dpio_phy_write(dev_priv, phy, VLV_PCS23_DW9(ch), val);
	}

	/* Program swing deemph */
	for (i = 0; i < intel_crtc->config->lane_count; i++) {
		val = vlv_dpio_phy_read(dev_priv, phy, CHV_TX_DW4(ch, i));
		val &= ~DPIO_SWING_DEEMPH9P5_MASK;
		val |= deemph_reg_value << DPIO_SWING_DEEMPH9P5_SHIFT;
		vlv_dpio_phy_write(dev_priv, phy, CHV_TX_DW4(ch, i), val);
	}

	/* Program swing margin */
	for (i = 0; i < intel_crtc->config->lane_count; i++) {
		val = vlv_dpio_phy_read(dev_priv, phy, CHV_TX_DW2(ch, i));

		val &= ~DPIO_SWING_MARGIN000_MASK;
		val |= margin_reg_value << DPIO_SWING_MARGIN000_SHIFT;

		/*
		 * Supposedly this value shouldn't matter when unique transition
		 * scale is disabled, but in fact it does matter. Let's just
		 * always program the same value and hope it's OK.
		 */
		val &= ~(0xff << DPIO_UNIQ_TRANS_SCALE_SHIFT);
		val |= 0x9a << DPIO_UNIQ_TRANS_SCALE_SHIFT;

		vlv_dpio_phy_write(dev_priv, phy, CHV_TX_DW2(ch, i), val);
	}

	/*
	 * The document said it needs to set bit 27 for ch0 and bit 26
	 * for ch1. Might be a typo in the doc.
	 * For now, for this unique transition scale selection, set bit
	 * 27 for ch0 and ch1.
	 */
	for (i = 0; i < intel_crtc->config->lane_count; i++) {
		val = vlv_dpio_phy_read(dev_priv, phy, CHV_TX_DW3(ch, i));
		if (uniq_trans_scale)
			val |= DPIO_TX_UNIQ_TRANS_SCALE_EN;
		else
			val &= ~DPIO_TX_UNIQ_TRANS_SCALE_EN;
		vlv_dpio_phy_write(dev_priv, phy, CHV_TX_DW3(ch, i), val);
	}

	/* Start swing calculation */
	val = vlv_dpio_phy_read(dev_priv, phy, VLV_PCS01_DW10(ch));
	val |= DPIO_PCS_SWING_CALC_TX0_TX2 | DPIO_PCS_SWING_CALC_TX1_TX3;
	vlv_dpio_phy_write(dev_priv, phy, VLV_PCS01_DW10(ch), val);

	if (intel_crtc->config->lane_count > 2) {
		val = vlv_dpio_phy_read(dev_priv, phy, VLV_PCS23_DW10(ch));
		val |= DPIO_PCS_SWING_CALC_TX0_TX2 | DPIO_PCS_SWING_CALC_TX1_TX3;
		vlv_dpio_phy_write(dev_priv, phy, VLV_PCS23_DW10(ch), val);
	}

	vlv_dpio_put(dev_priv);
}
/* END F17 EXACT PATCHED NATIVE FUNCTION */
static void one(int port,int pipe,int lanes,bool uniq) {
    struct drm_i915_private d={.active=1,.port=port,
        .phy=port==PORT_D?DPIO_PHY1:DPIO_PHY0,
        .ch=port==PORT_C?DPIO_CH1:DPIO_CH0};
    struct intel_digital_port digital={.base={port}};
    struct intel_crtc_config config={.lane_count=lanes};
    struct intel_crtc crtc={.pipe=pipe,.config=&config};
    struct intel_encoder e={.base={&d,&crtc},.digital=&digital};
    chv_set_phy_signal_level(&e,2,3,uniq);
    int count=3*lanes+3+(lanes>2?3:0);
    CHECK(d.gets==1 && d.puts==1 && !d.lock);
    CHECK(d.reads==count && d.writes==count);
}
int main(void) {
    one(PORT_B,0,2,false);
    one(PORT_C,2,4,true);  /* pipe >> 1 = PHY1; physical port C = PHY0 */
    one(PORT_D,0,2,true);  /* pipe >> 1 = PHY0; physical port D = PHY1 */
    one(PORT_B,2,4,true);
    one(PORT_D,2,4,false);
    puts("F17_EXACT_CHV_SIGNAL_PHY_ROUTING_PASS");
    return 0;
}

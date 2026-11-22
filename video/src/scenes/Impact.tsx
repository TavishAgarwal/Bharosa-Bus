import React from "react";
import {AbsoluteFill, useCurrentFrame} from "remotion";
import {C, fontFamily} from "../theme";
import {FadeUp, Logo, rise} from "../ui";
import {sectionRange} from "../timeline";

const Card: React.FC<{at: number; title: string; color: string; children: React.ReactNode}> = ({at, title, color, children}) => (
  <FadeUp at={at} style={{flex: 1}}>
    <div style={{background: "#fff", borderRadius: 28, border: `2px solid ${C.line}`, borderTop: `10px solid ${color}`, padding: "34px 36px", height: 560}}>
      <div style={{fontSize: 44, fontWeight: 800}}>{title}</div>
      <div style={{marginTop: 24, fontSize: 31, lineHeight: 1.4, color: "#333"}}>{children}</div>
    </div>
  </FadeUp>
);

export const Impact: React.FC = () => {
  const f = useCurrentFrame();
  const {start, beats} = sectionRange("impact");
  const [i1, i2, i3] = beats.map((b) => b.start - start);
  const steps = ["Pink Saheli card data: women ride free and are missing from e-tickets", "Same-day estimates from live ticket feeds", "In-bus counts to calibrate", "A home in Delhi's official transit apps"];
  return (
    <AbsoluteFill style={{background: C.paper, fontFamily, color: C.ink, padding: "80px 110px"}}>
      <div style={{display: "flex", justifyContent: "space-between", alignItems: "center"}}>
        <Logo size={64} />
        <div style={{fontSize: 30, color: C.mute, fontWeight: 600}}>Impact and next steps</div>
      </div>
      <div style={{display: "flex", gap: 30, marginTop: 60}}>
        <Card at={i1 + 6} title="Commuters" color={C.seats}>
          See <b>seats / standing / crowded</b> next to travel time, in English or हिन्दी.
          <div style={{marginTop: 22, color: C.mute}}>Women, older riders and parents with children can pick the trip that suits them, often for a few extra minutes.</div>
        </Card>
        <Card at={i2 + 4} title="DTC & operators" color={C.crowded}>
          A ranked “+1 bus” list, with a cautious estimate.
          <div style={{marginTop: 24, display: "flex", alignItems: "baseline", gap: 14}}>
            <span style={{fontSize: 76, fontWeight: 800, color: C.seats}}>4,938</span><span style={{color: C.mute}}>standing min / day saved</span>
          </div>
          <div style={{color: C.mute}}>route 188 DOWN, weekday AM peak (cautious: 2,843)</div>
        </Card>
        <Card at={i3 + 4} title="Next steps" color={C.live}>
          {steps.map((s, k) => (
            <div key={s} style={{display: "flex", gap: 16, marginTop: k ? 18 : 0, opacity: rise(f, i3 + 14 + k * 30)}}>
              <span style={{color: C.live, fontWeight: 800}}>{k + 1}</span><span>{s}</span>
            </div>
          ))}
        </Card>
      </div>
    </AbsoluteFill>
  );
};

export const End: React.FC = () => (
  <AbsoluteFill style={{background: C.night, fontFamily, color: "#fff", justifyContent: "center", alignItems: "center", gap: 30}}>
    <FadeUp at={2}><Logo size={120} dark /></FadeUp>
    <FadeUp at={14}><div style={{fontSize: 56, fontWeight: 800}}>Crowding you can trust.</div></FadeUp>
    <FadeUp at={30}><div style={{fontSize: 32, color: "#bbb"}}>github.com/TavishAgarwal/Bharosa-Bus</div></FadeUp>
    <FadeUp at={44}><div style={{fontSize: 30, color: "#888", marginTop: 20}}>Team Ctrl Alt Elite · Tavish Agarwal · Nikunj Kaushik</div></FadeUp>
  </AbsoluteFill>
);

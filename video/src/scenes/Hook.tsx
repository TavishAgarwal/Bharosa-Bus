import React from "react";
import {AbsoluteFill, interpolate, useCurrentFrame} from "remotion";
import {C, devaFamily, fontFamily, INTRO} from "../theme";
import {FadeUp, Logo, Pill, rise} from "../ui";
import {sectionRange} from "../timeline";

// Title card, then "every app answers WHEN; nobody answers WILL I GET ON IT".
export const Hook: React.FC = () => {
  const f = useCurrentFrame();
  const {beats} = sectionRange("hook");
  const h2 = beats[1].start;
  const titleOut = interpolate(f, [INTRO - 12, INTRO], [1, 0], {extrapolateLeft: "clamp", extrapolateRight: "clamp"});
  return (
    <AbsoluteFill style={{background: C.night, fontFamily, color: "#fff"}}>
      {f < INTRO + 2 && (
        <AbsoluteFill style={{justifyContent: "center", alignItems: "center", gap: 26, opacity: titleOut}}>
          <FadeUp at={4}><Logo size={120} dark /></FadeUp>
          <FadeUp at={16}><div style={{fontSize: 44, color: "#bdbdbd", fontWeight: 600}}>
            <span style={{fontFamily: devaFamily}}>भरोसा</span> = trust · Delhi bus crowding you can check</div></FadeUp>
        </AbsoluteFill>
      )}
      {f >= INTRO - 2 && (
        <AbsoluteFill style={{padding: "150px 170px", gap: 70}}>
          <FadeUp at={INTRO}>
            <div style={{display: "flex", alignItems: "center", gap: 34}}>
              <div style={{fontSize: 92, fontWeight: 800, letterSpacing: -1.5}}>“When does my bus come?”</div>
            </div>
            <div style={{display: "flex", alignItems: "center", gap: 18, marginTop: 18, fontSize: 40, color: "#9fd4ae", fontWeight: 600,
              opacity: rise(f, INTRO + 30)}}>
              <span style={{fontSize: 46}}>✓</span> Every app answers this.
            </div>
          </FadeUp>
          <FadeUp at={h2}>
            <div style={{fontSize: 92, fontWeight: 800, letterSpacing: -1.5, color: "#ffd27a"}}>“Will I even get a seat?”</div>
            <div style={{display: "flex", gap: 22, marginTop: 30}}>
              {[["seats", "Seats"], ["standing", "Standing"], ["crowded", "Crowded"]].map(([k, l], i) => (
                <div key={k} style={{opacity: rise(f, h2 + 30 + i * 12), translate: `0px ${(1 - rise(f, h2 + 30 + i * 12)) * 20}px`}}>
                  <Pill color={(C as Record<string, string>)[k]} label={l} size={40} />
                </div>
              ))}
              <div style={{alignSelf: "center", marginLeft: 20, fontSize: 40, color: "#ff8a80", fontWeight: 600, opacity: rise(f, h2 + 80)}}>
                ✗ No app tells you this.
              </div>
            </div>
          </FadeUp>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};

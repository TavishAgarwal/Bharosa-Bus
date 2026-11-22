import React from "react";
import {AbsoluteFill, useCurrentFrame} from "remotion";
import {C, fontFamily} from "../theme";
import {FadeUp, Logo, Pill, rise, StretchBar} from "../ui";
import {sectionRange} from "../timeline";

const Box: React.FC<{at: number; big: string; small: string; accent?: string}> = ({at, big, small, accent = C.ink}) => (
  <FadeUp at={at} style={{flex: 1}}>
    <div style={{background: "#fff", border: `2px solid ${C.line}`, borderRadius: 26, padding: "30px 30px", height: 220, display: "flex", flexDirection: "column", justifyContent: "center"}}>
      <div style={{fontSize: 54, fontWeight: 800, color: accent, letterSpacing: -1}}>{big}</div>
      <div style={{fontSize: 30, color: C.mute, marginTop: 10, lineHeight: 1.25}}>{small}</div>
    </div>
  </FadeUp>
);
const Arrow: React.FC<{at: number}> = ({at}) => {
  const f = useCurrentFrame();
  return <div style={{fontSize: 60, color: C.mute, opacity: rise(f, at), alignSelf: "center"}}>→</div>;
};

export const Solution: React.FC = () => {
  const f = useCurrentFrame();
  const {start, beats} = sectionRange("solution");
  const [s1, s2, s3] = beats.map((b) => b.start - start);
  const s3len = beats[2].frames;
  const lv = ["seats", "seats", "standing", "standing", "crowded", "crowded", "crowded", "standing", "seats", "unknown", "seats", "seats", "standing", "crowded", "standing", "seats"];
  const trust = [
    ["±", "A range on every number", "day-to-day spread + stated scale-up assumptions"],
    ["?", "“Not enough data”", "below 30 tickets we show grey, not a guess"],
    ["9 m / 12 m", "Bus size per route", "short D-routes run smaller DEVI buses"],
    ["κ 0.71", "Tested against baselines", "beats “always seats” and a route × hour average"],
  ];
  return (
    <AbsoluteFill style={{background: C.paper, fontFamily, color: C.ink, padding: "90px 130px"}}>
      <div style={{display: "flex", justifyContent: "space-between", alignItems: "center"}}>
        <Logo size={70} />
        <div style={{fontSize: 30, color: C.mute, fontWeight: 600, opacity: rise(f, s1 + 10)}}>Solution overview</div>
      </div>
      {f < s3 ? (
        <div style={{marginTop: 70}}>
          <div style={{display: "flex", gap: 26}}>
            <Box at={s1 + 20} big="2.56 M" small="October 2026 e-tickets: route, stops, time, fare" />
            <Arrow at={s1 + 50} />
            <Box at={s1 + 60} big="+ GTFS" small="Delhi bus timetable: stops, trips, shapes" />
            <Arrow at={s2} />
            <Box at={s2 + 10} big="80 %" small="of tickets matched to their boarding and alighting stops" accent={C.seats} />
          </div>
          <FadeUp at={s2 + 70} style={{marginTop: 70}}>
            <div style={{fontSize: 36, fontWeight: 700}}>People on board, for every stretch · route · direction · hour</div>
            <div style={{marginTop: 24}}><StretchBar levels={lv} at={s2 + 85} width={1660} height={44} per={4} /></div>
            <div style={{display: "flex", gap: 18, marginTop: 28}}>
              <Pill color={C.seats} label="Seats likely" size={30} /><Pill color={C.standing} label="Standing room" size={30} />
              <Pill color={C.crowded} label="Crowded" size={30} /><Pill color={C.unknown} label="Not enough data" size={30} />
            </div>
          </FadeUp>
        </div>
      ) : (
        <div style={{marginTop: 80, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 30}}>
          {trust.map(([k, t, d], i) => {
            const at = s3 + 12 + (i * s3len * 0.8) / 4;
            const on = rise(f, at, 14);
            return (
              <div key={t} style={{opacity: 0.25 + 0.75 * on, translate: `0px ${(1 - on) * 24}px`, background: "#fff", borderRadius: 26,
                border: `3px solid ${on > 0.5 ? C.ink : C.line}`, padding: "34px 38px", display: "flex", gap: 34, alignItems: "center"}}>
                <div style={{minWidth: 250, whiteSpace: "nowrap", fontSize: i === 2 ? 46 : 56, fontWeight: 800, color: [C.standing, C.unknown, C.live, C.seats][i]}}>{k}</div>
                <div><div style={{fontSize: 38, fontWeight: 800}}>{t}</div><div style={{fontSize: 29, color: C.mute, marginTop: 8}}>{d}</div></div>
              </div>
            );
          })}
        </div>
      )}
    </AbsoluteFill>
  );
};

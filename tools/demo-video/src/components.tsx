import React from "react";
import {Img, staticFile} from "remotion";
import {COLORS} from "./config";

export type Actor = "henrique" | "cris" | "dan";

export const ACTORS = {
  henrique: {
    name: "henriquebastos",
    avatar: "avatars/henrique.png",
    color: COLORS.henrique,
  },
  cris: {
    name: "crisbastos",
    avatar: "avatars/cris.png",
    color: COLORS.cris,
  },
  dan: {
    name: "hamster-dan",
    avatar: "avatars/dan.png",
    color: COLORS.dan,
  },
} as const;

const cardBase: React.CSSProperties = {
  background: COLORS.surface,
  border: `1px solid ${COLORS.border}`,
  borderRadius: 14,
  boxShadow: "0 18px 50px rgba(0,0,0,.28)",
  color: COLORS.text,
};

export const Presentation: React.FC<{
  act: number;
  actTitle: string;
  dashboard?: React.ReactNode;
  children: React.ReactNode;
}> = ({act, actTitle, dashboard, children}) => (
  <div
    style={{
      width: "100%",
      height: "100%",
      padding: "54px 64px",
      boxSizing: "border-box",
      color: COLORS.text,
      fontFamily: "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
      background:
        "radial-gradient(circle at 16% 15%, rgba(35,75,115,.22), transparent 28%), radial-gradient(circle at 85% 90%, rgba(35,100,60,.13), transparent 30%), #070b12",
      overflow: "hidden",
    }}
  >
    <header style={{height: 92, display: "flex", justifyContent: "space-between"}}>
      <div>
        <div style={{fontSize: 34, fontWeight: 760, letterSpacing: "-.03em"}}>
          Three collaborators take a pull request from change to readiness
        </div>
        <div style={{fontSize: 17, color: COLORS.muted, marginTop: 8}}>
          Henrique · Cris · Dan — one GitHub-native collaboration
        </div>
      </div>
      <div style={{textAlign: "right"}}>
        <div style={{fontSize: 15, color: COLORS.muted, letterSpacing: ".13em"}}>ACT {act} / 6</div>
        <div style={{fontSize: 23, fontWeight: 700, marginTop: 7}}>{actTitle}</div>
      </div>
    </header>
    <div style={{display: "grid", gridTemplateColumns: dashboard ? "1fr 458px" : "1fr", gap: 38, height: 862}}>
      <main style={{position: "relative", minWidth: 0}}>{children}</main>
      {dashboard ? <aside style={{position: "relative"}}>{dashboard}</aside> : null}
    </div>
  </div>
);

export const Dashboard: React.FC<{
  generation: number;
  actions: string;
  review: string;
  findings: string;
  base: string;
  approval: string;
  readiness: string;
  accent?: string;
}> = ({generation, actions, review, findings, base, approval, readiness, accent = COLORS.warning}) => {
  const rows = [
    ["Required checks", actions],
    ["Code review", review],
    ["Open findings", findings],
    ["Latest main", base],
    ["Required approval", approval],
  ];
  return (
    <div style={{...cardBase, height: "100%", overflow: "hidden", borderTop: `4px solid ${accent}`}}>
      <div style={{padding: "24px 25px 20px", borderBottom: `1px solid ${COLORS.border}`}}>
        <div style={{display: "flex", justifyContent: "space-between", alignItems: "center"}}>
          <strong style={{fontSize: 20}}>Hamsterdan dashboard</strong>
          <div style={{display: "flex", alignItems: "center", gap: 9}}>
            <span style={{width: 12, height: 12, borderRadius: "50%", background: accent, boxShadow: `0 0 14px ${accent}`}} />
            <span
              style={{
                color: accent,
                background: `${accent}1f`,
                padding: "5px 9px",
                borderRadius: 20,
                fontSize: 13,
                fontWeight: 700,
              }}
            >
              VERSION {generation}
            </span>
          </div>
        </div>
        <div style={{fontSize: 14, color: COLORS.muted, marginTop: 9}}>Updates in place as evidence arrives</div>
      </div>
      <div style={{padding: "12px 25px"}}>
        {rows.map(([name, value]) => (
          <div
            key={name}
            style={{display: "grid", gridTemplateColumns: "134px 1fr", gap: 14, padding: "17px 0", borderBottom: `1px solid ${COLORS.border}`}}
          >
            <span style={{fontSize: 14, color: COLORS.muted}}>{name}</span>
            <strong style={{fontSize: 15, lineHeight: 1.35}}>{value}</strong>
          </div>
        ))}
      </div>
      <div style={{position: "absolute", left: 25, right: 25, bottom: 25}}>
        <div style={{fontSize: 13, color: COLORS.muted, marginBottom: 10}}>OVERALL STATUS</div>
        <div
          style={{
            border: `1px solid ${accent}`,
            background: `${accent}17`,
            borderRadius: 10,
            padding: "16px 17px",
            color: accent,
            fontWeight: 750,
            fontSize: 18,
            lineHeight: 1.35,
          }}
        >
          {readiness}
        </div>
      </div>
    </div>
  );
};

export const ActorHeader: React.FC<{actor: Actor; action: string}> = ({actor, action}) => {
  const value = ACTORS[actor];
  return (
    <div style={{display: "flex", alignItems: "center", gap: 12}}>
      <Img
        src={staticFile(value.avatar)}
        style={{
          width: 44,
          height: 44,
          borderRadius: "50%",
          objectFit: "cover",
          border: `3px solid ${value.color}`,
          boxSizing: "border-box",
        }}
      />
      <div style={{lineHeight: 1.25}}>
        <div style={{fontSize: 16}}>
          <strong>{value.name}</strong> <span style={{color: COLORS.muted}}>{action}</span>
        </div>
      </div>
    </div>
  );
};

export const MessageCard: React.FC<{
  actor: Actor;
  action?: string;
  children: React.ReactNode;
  width?: number | string;
  style?: React.CSSProperties;
}> = ({actor, action = "commented", children, width = 970, style}) => {
  const value = ACTORS[actor];
  return (
    <div style={{...cardBase, width, overflow: "hidden", borderLeft: `4px solid ${value.color}`, ...style}}>
      <div style={{padding: "16px 20px", background: COLORS.surfaceRaised, borderBottom: `1px solid ${COLORS.border}`}}>
        <ActorHeader actor={actor} action={action} />
      </div>
      <div style={{padding: "21px 23px", fontSize: 20, lineHeight: 1.5}}>{children}</div>
    </div>
  );
};

export const PRCard: React.FC = () => (
  <div style={{...cardBase, width: 1040, overflow: "hidden", borderTop: `4px solid ${COLORS.henrique}`}}>
    <div style={{padding: "25px 30px", borderBottom: `1px solid ${COLORS.border}`, background: COLORS.surfaceRaised}}>
      <div style={{fontSize: 15, color: COLORS.muted}}>PULL REQUEST #47 · OPENED</div>
      <div style={{fontSize: 30, fontWeight: 740, marginTop: 10}}>Hamsterdan demo: hero-review</div>
    </div>
    <div style={{padding: "27px 30px"}}>
      <ActorHeader actor="henrique" action="wants to merge into main" />
      <div style={{display: "flex", gap: 12, marginTop: 25, fontSize: 15}}>
        {["+60 −1", "3 files", "Cris requested", "hero-review"].map((tag) => (
          <span key={tag} style={{padding: "8px 12px", borderRadius: 20, border: `1px solid ${COLORS.border}`, color: COLORS.muted}}>
            {tag}
          </span>
        ))}
      </div>
    </div>
  </div>
);

export const ReviewCard: React.FC<{
  index: number;
  total?: number;
  title: string;
  path: string;
  body: string;
  code?: {before: string; after: string};
  related?: string;
}> = ({index, total = 3, title, path, body, code, related}) => (
  <div style={{...cardBase, width: 1040, overflow: "hidden", borderLeft: `4px solid ${COLORS.dan}`}}>
    <div style={{padding: "16px 21px", background: COLORS.surfaceRaised, borderBottom: `1px solid ${COLORS.border}`}}>
      <ActorHeader actor="dan" action="started a native review thread" />
    </div>
    <div style={{padding: "20px 24px"}}>
      <div style={{display: "flex", justifyContent: "space-between", color: COLORS.muted, fontSize: 14}}>
        <span>{path}</span>
        <span>FINDING {index} / {total}</span>
      </div>
      <div style={{fontSize: 24, fontWeight: 730, marginTop: 15}}>{title}</div>
      <div style={{fontSize: 17, lineHeight: 1.5, marginTop: 12, color: "#c9d1d9"}}>{body}</div>
      {code ? (
        <div style={{marginTop: 18, border: `1px solid ${COLORS.border}`, borderRadius: 8, overflow: "hidden", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 15}}>
          <div style={{padding: "10px 14px", background: "rgba(248,81,73,.12)", color: "#ff7b72"}}>− {code.before}</div>
          <div style={{padding: "10px 14px", background: "rgba(63,185,80,.12)", color: "#7ee787"}}>+ {code.after}</div>
        </div>
      ) : null}
      {related ? (
        <div style={{marginTop: 17, color: COLORS.cris, fontSize: 15}}>↳ Related location: {related}</div>
      ) : null}
    </div>
  </div>
);

export const SystemCard: React.FC<{title: string; subtitle: string; accent?: string; children?: React.ReactNode}> = ({
  title,
  subtitle,
  accent = COLORS.system,
  children,
}) => (
  <div style={{...cardBase, width: 1040, padding: "24px 28px", borderLeft: `4px solid ${accent}`}}>
    <div style={{fontSize: 14, color: accent, fontWeight: 700, letterSpacing: ".08em"}}>GITHUB EVENT</div>
    <div style={{fontSize: 25, fontWeight: 740, marginTop: 9}}>{title}</div>
    <div style={{fontSize: 16, color: COLORS.muted, marginTop: 7}}>{subtitle}</div>
    {children}
  </div>
);

export const Checks: React.FC = () => (
  <div style={{display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginTop: 20}}>
    {["scenario-control", "lint", "type", "unit", "build", "integration"].map((name) => (
      <div key={name} style={{padding: "13px 14px", border: `1px solid ${COLORS.border}`, borderRadius: 8, color: "#7ee787", background: "rgba(63,185,80,.08)", fontSize: 15}}>
        ✓ <span style={{color: COLORS.text, marginLeft: 7}}>{name}</span>
      </div>
    ))}
  </div>
);

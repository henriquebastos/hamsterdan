import React from "react";
import {Easing, interpolate, spring, useCurrentFrame} from "remotion";
import {COLORS, VIDEO} from "../config";
import {
  ActorHeader,
  Dashboard,
  MessageCard,
  PRCard,
  Presentation,
  ReviewCard,
  SystemCard,
} from "../components";

const F = VIDEO.fps;
const S = (seconds: number) => Math.round(seconds * F);
const starts = {
  opening: 0,
  review: VIDEO.acts.opening * F,
  conversation: (VIDEO.acts.opening + VIDEO.acts.review) * F,
  repair: (VIDEO.acts.opening + VIDEO.acts.review + VIDEO.acts.conversation) * F,
  recovery:
    (VIDEO.acts.opening + VIDEO.acts.review + VIDEO.acts.conversation + VIDEO.acts.repair) * F,
  approval:
    (VIDEO.acts.opening +
      VIDEO.acts.review +
      VIDEO.acts.conversation +
      VIDEO.acts.repair +
      VIDEO.acts.recovery) *
    F,
} as const;

const actAt = (frame: number) => {
  if (frame < starts.review) return [1, "A PR ENTERS"] as const;
  if (frame < starts.conversation) return [2, "DAN REVIEWS"] as const;
  if (frame < starts.repair) return [3, "CONVERSATION"] as const;
  if (frame < starts.recovery) return [4, "CONFIRM & REPAIR"] as const;
  if (frame < starts.approval) return [5, "RECOVER & UPDATE BASE"] as const;
  return [6, "APPROVED & READY"] as const;
};

const guideCues = [
  {start: 0, label: "CONTEXT", text: "Henrique opens PR #47 and asks Cris to take a look."},
  {start: S(1.8), label: "HAPPENING NOW", text: "Dan joins the pull request and creates one live dashboard to track its progress."},
  {start: S(6), label: "WHAT CHANGED", text: "The dashboard moves to the sidebar and stays current as the collaborators continue working."},
  {start: starts.review, label: "CONTEXT", text: "Dan examines the changed files and comments on the exact lines that need attention."},
  {start: starts.review + S(1.8), label: "HAPPENING NOW", text: "The first GitHub review thread identifies a lease that lasts 60 times longer than requested."},
  {start: starts.review + S(10.8), label: "HAPPENING NOW", text: "A second thread shows that rejected reviews are incorrectly counted as approvals."},
  {start: starts.review + S(19.8), label: "HAPPENING NOW", text: "A third thread connects two code locations that disagree about repository-name capitalization."},
  {start: starts.review + S(28), label: "WHAT CHANGED", text: "Three review conversations now need attention, so the pull request remains blocked."},
  {start: starts.conversation, label: "CONTEXT", text: "Henrique asks Dan to fix the findings. Changing the branch requires an exact confirmation first."},
  {start: starts.conversation + S(10.8), label: "HAPPENING NOW", text: "Dan prepares only the requested repair and waits behind the confirmation lock."},
  {start: starts.conversation + S(18.8), label: "WHY IT MATTERS", text: "The confirmation code connects Henrique’s approval to this request and this exact commit."},
  {start: starts.conversation + S(26.8), label: "WHAT CHANGED", text: "The confirmation matches, so Dan can begin the requested repair."},
  {start: starts.repair, label: "CONTEXT", text: "Dan makes only the confirmed changes and records the result in a new commit."},
  {start: starts.repair + S(5.8), label: "HAPPENING NOW", text: "Dan begins the confirmed repair on the exact latest commit."},
  {start: starts.repair + S(11.8), label: "HAPPENING NOW", text: "Three requested fixes change three lines across two files."},
  {start: starts.repair + S(18.8), label: "WHY IT BLOCKED", text: "The fixes are correct, but a required demo check still expects the original broken behavior."},
  {start: starts.repair + S(25.8), label: "WHAT CHANGED", text: "The same failure happens again, identifying a separate problem in the scenario validator."},
  {start: starts.recovery, label: "CONTEXT", text: "Dan reports the validator mismatch as a fourth review finding on the affected code."},
  {start: starts.recovery + S(8.8), label: "HAPPENING NOW", text: "Another pull request corrects that validator on the main branch."},
  {start: starts.recovery + S(13.8), label: "WHY CONFIRM", text: "Bringing the correction into PR #47 changes its branch, so Dan asks for confirmation again."},
  {start: starts.recovery + S(19.8), label: "HAPPENING NOW", text: "Dan prepares the exact branch update and waits for confirmation."},
  {start: starts.recovery + S(26.8), label: "WHY IT MATTERS", text: "The confirmation matches the requested update and the latest commit."},
  {start: starts.recovery + S(30.8), label: "HAPPENING NOW", text: "The repaired code and corrected validator are now tested together."},
  {start: starts.recovery + S(35), label: "WHAT CHANGED", text: "All six checks pass. Only approval of the latest commit remains."},
  {start: starts.approval, label: "CONTEXT", text: "Because the branch changed, Cris examines the exact latest commit before approving it."},
  {start: starts.approval + S(7.8), label: "HAPPENING NOW", text: "Cris verifies the fixes and resolves every review conversation."},
  {start: starts.approval + S(12.8), label: "HAPPENING NOW", text: "Cris approves the exact latest commit."},
  {start: starts.approval + S(18.8), label: "WHAT CHANGED", text: "Every observed gate is satisfied. Dan reports readiness, and the team keeps the merge decision."},
  {start: starts.approval + S(26.8), label: "EPILOGUE", text: "Henrique closes the reusable demo pull request. Dan observes the closure and the collaboration ends cleanly."},
] as const;

const dashboardState = (frame: number) => {
  if (frame < starts.review + S(3)) {
    return {
      generation: 1,
      actions: "Collecting",
      review: "Queued",
      findings: "—",
      base: "Current",
      approval: "Cris requested",
      readiness: "WAITING · collecting evidence",
      accent: COLORS.warning,
    };
  }
  if (frame < starts.conversation) {
    const count = frame < starts.review + S(12) ? 1 : frame < starts.review + S(21) ? 2 : 3;
    return {
      generation: 1,
      actions: "Green · first run",
      review: "Blocking",
      findings: `${count} new`,
      base: "Current",
      approval: "Pending",
      readiness: "BLOCKED · review findings",
      accent: COLORS.danger,
    };
  }
  if (frame < starts.repair) {
    return {
      generation: 1,
      actions: "Green",
      review: "Blocking",
      findings: "3 new",
      base: "Current",
      approval: "Pending",
      readiness: frame >= starts.conversation + S(20) ? "WAITING · branch confirmation" : "BLOCKED · review findings",
      accent: frame >= starts.conversation + S(20) ? COLORS.warning : COLORS.danger,
    };
  }
  if (frame < starts.repair + S(20)) {
    return {
      generation: 2,
      actions: "Running",
      review: "Clear",
      findings: "3 resolved",
      base: "Current",
      approval: "Pending",
      readiness: "WORKING · confirmed repair",
      accent: COLORS.warning,
    };
  }
  if (frame < starts.recovery + S(21)) {
    const findingPublished = frame >= starts.recovery + S(2.5);
    return {
      generation: 2,
      actions: "Reproduced",
      review: findingPublished ? "Blocking" : "Clear",
      findings: findingPublished ? "f04 new · 3 resolved" : "3 resolved",
      base: frame >= starts.recovery ? "Stale" : "Current",
      approval: "Pending",
      readiness: "BLOCKED · scenario validator",
      accent: COLORS.danger,
    };
  }
  if (frame < starts.approval) {
    const updateRunning = frame >= starts.recovery + S(32) && frame < starts.recovery + S(35);
    const checksGreen = frame >= starts.recovery + S(35);
    return {
      generation: 3,
      actions: checksGreen ? "Green · first run" : updateRunning ? "Running" : "Reproduced",
      review: checksGreen ? "Clear" : "Blocking",
      findings: checksGreen ? "4 resolved" : "f04 new · 3 resolved",
      base: checksGreen ? "Current" : "Stale",
      approval: "Awaiting latest commit",
      readiness: checksGreen ? "WAITING · required approval" : updateRunning ? "WORKING · branch update" : "WAITING · branch confirmation",
      accent: COLORS.warning,
    };
  }
  if (frame < starts.approval + S(20)) {
    return {
      generation: 3,
      actions: "Green · first run",
      review: "Clear",
      findings: "4 resolved",
      base: "Current",
      approval: frame < starts.approval + S(14) ? "Cris reviewing" : "Cris · latest commit",
      readiness: frame < starts.approval + S(14) ? "WAITING · required approval" : "WAITING · readiness update",
      accent: COLORS.warning,
    };
  }
  return {
    generation: 3,
    actions: "Green · first run",
    review: "Clear",
    findings: "4 resolved",
    base: "Current",
    approval: "Cris · latest commit",
    readiness: "READY · all observed gates satisfied",
    accent: COLORS.success,
  };
};

const FadeLayer: React.FC<{
  start: number;
  end: number;
  children: React.ReactNode;
}> = ({start, end, children}) => {
  const frame = useCurrentFrame();
  const enter = spring({frame: frame - start, fps: F, config: {damping: 18, stiffness: 140, mass: 0.85}});
  const exit = interpolate(frame, [end - 18, end], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  if (frame < start || frame >= end) return null;
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        opacity: enter * exit,
        transform: `translateY(${interpolate(enter, [0, 1], [38, 0]) - (1 - exit) * 45}px)`,
      }}
    >
      {children}
    </div>
  );
};

const StoryGuide: React.FC<{frame: number}> = ({frame}) => (
  <div
    style={{
      position: "absolute",
      left: 0,
      right: 0,
      top: 0,
      height: 70,
      border: `1px solid ${COLORS.border}`,
      borderRadius: 12,
      background: "rgba(13,17,23,.94)",
      boxShadow: "0 12px 34px rgba(0,0,0,.22)",
      overflow: "hidden",
      zIndex: 20,
    }}
  >
    {guideCues.map((cue, index) => {
      const end = guideCues[index + 1]?.start ?? VIDEO.targetDurationSeconds * F;
      if (frame < cue.start - 10 || frame >= end + 10) return null;
      const opacity =
        interpolate(frame, [cue.start - 8, cue.start + 8], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"}) *
        interpolate(frame, [end - 8, end + 8], [1, 0], {extrapolateLeft: "clamp", extrapolateRight: "clamp"});
      const x = interpolate(frame, [cue.start - 8, cue.start + 8], [18, 0], {extrapolateLeft: "clamp", extrapolateRight: "clamp"});
      return (
        <div key={cue.start} style={{position: "absolute", inset: 0, display: "flex", alignItems: "center", gap: 20, padding: "0 24px", opacity, transform: `translateX(${x}px)`}}>
          <div style={{fontSize: 12, fontWeight: 800, letterSpacing: ".12em", color: COLORS.henrique, minWidth: 126}}>{cue.label}</div>
          <div style={{width: 1, height: 30, background: COLORS.border}} />
          <div style={{fontSize: 18, lineHeight: 1.35, color: "#d7dee7"}}>{cue.text}</div>
        </div>
      );
    })}
  </div>
);

const Spotlight: React.FC<{
  start: number;
  end: number;
  children: React.ReactNode;
}> = ({start, end, children}) => (
  <FadeLayer start={start} end={end}>
    <div style={{height: "100%", display: "grid", placeItems: "center"}}>{children}</div>
  </FadeLayer>
);

type FeedItem = {
  start: number;
  height: number;
  node: React.ReactNode;
};

const Feed: React.FC<{items: FeedItem[]; bottom?: number}> = ({items, bottom = 640}) => {
  const frame = useCurrentFrame();
  const progress = items.map((item) =>
    spring({frame: frame - item.start, fps: F, config: {damping: 18, stiffness: 145, mass: 0.8}}),
  );
  const gestures = items.map((item, index) => {
    const age = frame - item.start;
    const seed = Math.abs(Math.sin((item.start + index * 97) * 12.9898)) * 43758.5453;
    const direction = seed % 1 < 0.5 ? -1 : 1;
    const sway = age >= 0 && age < 26 ? Math.sin(age * 0.47 + seed) * (1 - age / 26) : 0;
    const pulse = interpolate(age, [0, 7, 18], [1, 1.006, 1], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.inOut(Easing.quad),
    });
    return {sway, pulse, direction};
  });
  return (
    <div style={{position: "absolute", inset: 0, overflow: "hidden"}}>
      {items.map((item, index) => {
        if (frame < item.start) return null;
        const own = progress[index];
        const laterPush = progress
          .slice(index + 1)
          .reduce((sum, value, laterIndex) => sum + value * (items[index + laterIndex].height + 18), 0);
        const y = bottom - laterPush + interpolate(own, [0, 1], [54, 0]);
        const topFade = interpolate(y, [-140, 20], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"});
        return (
          <div
            key={item.start}
            style={{
              position: "absolute",
              left: 35,
              top: y,
              opacity: own * topFade,
              transform: `translateX(${gestures[index].sway * gestures[index].direction}px) rotate(${gestures[index].sway * 0.025}deg) scale(${interpolate(own, [0, 1], [0.97, 1]) * gestures[index].pulse})`,
            }}
          >
            {item.node}
          </div>
        );
      })}
    </div>
  );
};

const CompactChecks: React.FC<{failed?: boolean}> = ({failed = false}) => (
  <div style={{display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10, marginTop: 17}}>
    {["scenario-control", "lint", "type", "unit", "build", "integration"].map((name, index) => {
      const state = failed ? (index === 0 ? "failed" : "skipped") : "passed";
      const color = state === "passed" ? COLORS.success : state === "failed" ? COLORS.danger : COLORS.muted;
      return (
        <div key={name} style={{padding: "11px 12px", border: `1px solid ${color}66`, borderRadius: 8, color, fontSize: 14}}>
          {state === "passed" ? "✓" : state === "failed" ? "×" : "–"} {name}
        </div>
      );
    })}
  </div>
);

const DashboardRail: React.FC<{frame: number}> = ({frame}) => {
  if (frame < S(2.8)) return null;
  const arrival = spring({frame: frame - S(2.8), fps: F, config: {damping: 18, stiffness: 145, mass: 0.8}});
  const morph = interpolate(frame, [S(6.5), S(7)], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"});
  const messageOpacity = interpolate(morph, [0, 0.72], [1, 0], {extrapolateRight: "clamp"});
  const railOpacity = interpolate(morph, [0.42, 1], [0, 1], {extrapolateLeft: "clamp"});
  const transitions = [
    starts.review + S(3), starts.review + S(12), starts.review + S(21), starts.conversation + S(20),
    starts.repair, starts.repair + S(20), starts.recovery, starts.recovery + S(2.5),
    starts.recovery + S(21), starts.recovery + S(32), starts.recovery + S(35),
    starts.approval, starts.approval + S(14), starts.approval + S(20),
  ];
  const latestTransition = transitions.filter((transition) => transition <= frame).at(-1);
  const transitionAge = latestTransition === undefined ? Number.POSITIVE_INFINITY : frame - latestTransition;
  const statusPulse = interpolate(transitionAge, [0, 8, 20], [1, 1.007, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.quad),
  });
  const state = dashboardState(frame);
  return (
    <div
      style={{
        position: "absolute",
        left: interpolate(morph, [0, 1], [330, 1334]),
        top: interpolate(morph, [0, 1], [390, 82]),
        width: interpolate(morph, [0, 1], [1040, 458]),
        height: interpolate(morph, [0, 1], [270, 780]),
        opacity: arrival,
        transform: `translateY(${interpolate(arrival, [0, 1], [58, 0])}px) scale(${interpolate(arrival, [0, 1], [0.97, 1]) * statusPulse})`,
        filter: `blur(${Math.sin(morph * Math.PI) * 3}px)`,
        border: `1px solid ${COLORS.border}`,
        borderLeft: `4px solid ${COLORS.dan}`,
        borderRadius: 14,
        background: COLORS.surface,
        overflow: "hidden",
        boxShadow: `0 18px 50px rgba(0,0,0,.3), 0 0 ${Math.max(0, (statusPulse - 1) * 2600)}px ${state.accent}55`,
      }}
    >
      <div style={{opacity: messageOpacity}}>
        <div style={{padding: "16px 20px", background: COLORS.surfaceRaised, borderBottom: `1px solid ${COLORS.border}`}}>
          <ActorHeader actor="dan" action="created the readiness dashboard" />
        </div>
        <div style={{padding: "22px 24px"}}>
          <div style={{fontSize: 23, fontWeight: 740}}>Hamsterdan PR readiness dashboard</div>
          <div style={{display: "flex", gap: 14, marginTop: 18, color: COLORS.muted, fontSize: 16}}>
            <span>Checks: collecting</span><span>·</span><span>Review: queued</span><span>·</span><span>Status: waiting</span>
          </div>
          <div style={{fontSize: 14, color: COLORS.muted, marginTop: 17}}>I’ll keep this dashboard current as the collaboration progresses.</div>
        </div>
      </div>
      <div style={{position: "absolute", inset: 0, opacity: railOpacity}}>
        <Dashboard {...state} />
      </div>
    </div>
  );
};

export const FullMotion: React.FC = () => {
  const frame = useCurrentFrame();
  const [act, actTitle] = actAt(frame);
  const dashboardArrival = spring({frame: frame - S(2.8), fps: F, config: {damping: 18, stiffness: 145, mass: 0.8}});
  const openingMorph = interpolate(frame, [S(6.5), S(7)], [0, 1], {extrapolateLeft: "clamp", extrapolateRight: "clamp"});
  const reviewItems: FeedItem[] = [
    {start: starts.review + S(3), height: 360, node: <ReviewCard index={1} title="Lease lasts 60× longer than requested" path="scenario-fixtures/hero_review/gate.py · line 10" body="The duration is supplied in seconds but applied as minutes." code={{before: "timedelta(minutes=ttl_seconds)", after: "timedelta(seconds=ttl_seconds)"}} />},
    {start: starts.review + S(12), height: 275, node: <ReviewCard index={2} title="Rejected reviews count as approvals" path="scenario-fixtures/hero_review/gate.py · line 16" body="The code counts every recorded review, including values explicitly marked false." />},
    {start: starts.review + S(21), height: 305, node: <ReviewCard index={3} title="Cache lookup changes with capitalization" path="scenario-fixtures/hero_review/cache.py · line 11" body="Storage normalizes the repository name, but lookup does not, so the same repository can produce different keys." related="Related location · cache.py · line 6" />},
  ];
  const conversationItems: FeedItem[] = [
    {start: starts.conversation + S(3), height: 148, node: <MessageCard actor="henrique" width={1040} style={{height: 148, boxSizing: "border-box"}}><strong>@hamster-dan status</strong></MessageCard>},
    {start: starts.conversation + S(6.5), height: 178, node: <MessageCard actor="dan" width={1040} style={{height: 178, boxSizing: "border-box"}}>Waiting for finding disposition or change. That's the next gate; I'm keeping watch.</MessageCard>},
    {start: starts.conversation + S(12), height: 178, node: <MessageCard actor="henrique" width={1040} style={{height: 178, boxSizing: "border-box"}}>Fix the three review findings: use seconds for the lease, count only true approvals, and normalize repository names during cache lookup.</MessageCard>},
    {start: starts.conversation + S(20), height: 208, node: <MessageCard actor="dan" width={1040} style={{height: 208, boxSizing: "border-box"}}>The change mutation is staged, not authorized. Reply with the exact digest to confirm. I keep the wheel behind a lock for a reason.</MessageCard>},
    {start: starts.conversation + S(28), height: 178, node: <MessageCard actor="henrique" width={1040} style={{height: 178, boxSizing: "border-box"}}>@hamster-dan confirm the pending change mutation with digest <span style={{fontFamily: "monospace", color: COLORS.muted}}>0be20c78…</span></MessageCard>},
  ];
  const repairItems: FeedItem[] = [
    {start: starts.repair + S(2.5), height: 158, node: <MessageCard actor="dan" width={1040} style={{height: 158, boxSizing: "border-box"}}>Confirmed change mutation. Authorization matches; execution can proceed.</MessageCard>},
    {start: starts.repair + S(7), height: 164, node: <SystemCard title="Dan begins the confirmed repair" subtitle="Bound to the requested work and the exact latest commit" accent={COLORS.dan} />},
    {start: starts.repair + S(13), height: 204, node: <SystemCard title="Fix hero review lease, approval, and cache behavior" subtitle="New commit · 3 changed lines · 2 files" accent={COLORS.dan}><div style={{marginTop: 14, fontFamily: "monospace", color: COLORS.muted}}>seconds ✓ · true approvals ✓ · normalized lookup ✓</div></SystemCard>},
    {start: starts.repair + S(20), height: 258, node: <SystemCard title="One required check rejects the repair" subtitle="The scenario validator still expects the original broken behavior" accent={COLORS.danger}><CompactChecks failed /></SystemCard>},
    {start: starts.repair + S(27), height: 160, node: <SystemCard title="The rerun fails the same way" subtitle="The failure is reproduced, not temporary" accent={COLORS.danger} />},
  ];
  const recoveryItems: FeedItem[] = [
    {start: starts.recovery + S(2.5), height: 305, node: <ReviewCard index={4} total={4} title="The repaired code is rejected by the scenario validator" path="scenario-fixtures/hero_review/gate.py · line 10" body="The three fixes are correct, but the required validator still looks for the original defects." related="Related locations · validator, selector, and all repaired lines" />},
    {start: starts.recovery + S(10), height: 160, node: <SystemCard title="PR #48 corrects the validator on main" subtitle="The scenario can now recognize the repaired state" accent={COLORS.success} />},
    {start: starts.recovery + S(15), height: 168, node: <MessageCard actor="henrique" width={1040} style={{height: 168, boxSizing: "border-box"}}>@hamster-dan update the PR branch with the latest main.</MessageCard>},
    {start: starts.recovery + S(21), height: 208, node: <MessageCard actor="dan" width={1040} style={{height: 208, boxSizing: "border-box"}}>The update_base mutation is staged, not authorized. Reply with the exact digest to confirm.</MessageCard>},
    {start: starts.recovery + S(28), height: 178, node: <MessageCard actor="henrique" width={1040} style={{height: 178, boxSizing: "border-box"}}>@hamster-dan confirm the pending update_base mutation with digest <span style={{fontFamily: "monospace", color: COLORS.muted}}>3fab5165…</span></MessageCard>},
    {start: starts.recovery + S(32), height: 278, node: <SystemCard title="Latest main joins PR #47" subtitle="The corrected validator and repaired code are tested together" accent={COLORS.dan}><CompactChecks /></SystemCard>},
  ];
  const approvalItems: FeedItem[] = [
    {start: starts.approval + S(3), height: 178, node: <MessageCard actor="cris" width={1040} style={{height: 178, boxSizing: "border-box"}} action="verified the latest commit">Dan’s three repairs are correct, the validator now agrees with them, and all six checks are green.</MessageCard>},
    {start: starts.approval + S(9), height: 158, node: <SystemCard title="All four GitHub review threads are resolved" subtitle="The review conversations are complete" accent={COLORS.cris} />},
    {start: starts.approval + S(14), height: 158, node: <MessageCard actor="cris" width={1040} style={{height: 158, boxSizing: "border-box"}} action="approved the latest commit"><strong>The current version is reviewed and approved.</strong></MessageCard>},
    {start: starts.approval + S(20), height: 188, node: <MessageCard actor="dan" width={1040} style={{height: 188, boxSizing: "border-box"}} action="reported readiness"><strong>All observed gates are ready. Clean.</strong><br />The team keeps merge authority; Dan never merges pull requests.</MessageCard>},
    {start: starts.approval + S(28), height: 170, node: <MessageCard actor="henrique" width={1040} style={{height: 170, boxSizing: "border-box"}} action="closed this pull request">Demo complete. Closing unmerged so the repository remains reusable.</MessageCard>},
  ];

  return (
    <Presentation act={act} actTitle={actTitle}>
      <div style={{position: "absolute", inset: 0, overflow: "hidden"}}>
        <StoryGuide frame={frame} />
        {frame < starts.review ? (
          <div
            style={{
              position: "absolute",
              left: 330,
              top: 205 - dashboardArrival * 115,
              opacity: interpolate(openingMorph, [0.1, 0.8], [1, 0], {extrapolateLeft: "clamp", extrapolateRight: "clamp"}),
              transform: `scale(${interpolate(dashboardArrival, [0, 1], [1, 0.965])})`,
            }}
          >
            <PRCard />
          </div>
        ) : null}
        <DashboardRail frame={frame} />

        <FadeLayer start={starts.review} end={starts.conversation}>
          <Feed items={reviewItems} bottom={500} />
        </FadeLayer>

        <FadeLayer start={starts.conversation} end={starts.repair}>
          <Feed items={conversationItems} />
        </FadeLayer>
        <FadeLayer start={starts.repair} end={starts.recovery}>
          <Feed items={repairItems} bottom={630} />
        </FadeLayer>

        <FadeLayer start={starts.recovery} end={starts.approval}>
          <Feed items={recoveryItems} bottom={540} />
        </FadeLayer>
        {frame >= starts.approval ? <Feed items={approvalItems} bottom={625} /> : null}
      </div>
    </Presentation>
  );
};

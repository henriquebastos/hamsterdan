import React from "react";
import {useCurrentFrame} from "remotion";
import {MessageCard, Presentation, ReviewCard, SystemCard} from "../components";
import {eventAfterGuideFrame, nextBeatFrame} from "../timing";

// Copy this file when starting a scenario. Replace the copy below before
// changing motion. Main message text drives the initial timing estimate.
const copy = {
  openingGuide: "Explain who is collaborating and what changed in the pull request.",
  openingMessage: "State the first GitHub event in language a new viewer can understand.",
  findingTitle: "Describe one concrete problem",
  findingBody: "Explain the consequence before showing implementation detail.",
  outcome: "Explain what changed and why the next collaborator can proceed.",
} as const;

const guideAt = 0;
const openingAt = eventAfterGuideFrame(guideAt);
const findingAt = nextBeatFrame(openingAt, copy.openingMessage);
const outcomeAt = nextBeatFrame(findingAt, `${copy.findingTitle} ${copy.findingBody}`);

export const ScenarioTemplate: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <Presentation act={1} actTitle="NAME THIS ACT">
      {frame >= openingAt ? (
        <div style={{position: "absolute", left: 35, top: 180}}>
          <MessageCard actor="henrique" width={1040}>{copy.openingMessage}</MessageCard>
        </div>
      ) : null}
      {frame >= findingAt ? (
        <div style={{position: "absolute", left: 35, top: 410}}>
          <ReviewCard
            index={1}
            total={1}
            title={copy.findingTitle}
            path="path/to/file.py · line 1"
            body={copy.findingBody}
          />
        </div>
      ) : null}
      {frame >= outcomeAt ? (
        <div style={{position: "absolute", left: 35, top: 700}}>
          <SystemCard title="Outcome" subtitle={copy.outcome} />
        </div>
      ) : null}
    </Presentation>
  );
};

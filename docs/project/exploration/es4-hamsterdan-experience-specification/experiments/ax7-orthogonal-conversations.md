# AX7 — Conversations are orthogonal to the head machine

## Question

Navigator hunch: *why would quiescence hold a conversation at all?*
Any message to the agent looks at the current state of the repo and
answers — "why is this this way?", "who did it?" — regardless of head,
draft status, or even whether the PR is still open. Are conversations
orthogonal to the head-authority machine, and does the simplest scope
(a read-only conversation agent) make AX6's Hold unnecessary?

Spike: [ax7-orthogonal-conversations/](ax7-orthogonal-conversations/) —
10 tests, all passing; imports the AX6 machine unchanged.

## The inherited coupling

Production stamps **every** classified intent with the authority epoch
and head — including pure questions:

```python
# contracts/readiness.py:417-421 — the stamp exists for ALL 12 kinds:
class Intent(WorkflowModel):
    epoch: int          # ← a question inherits the generation…
    head: str           # ← …and the head it happened to arrive under
    kind: Literal["reply", "status", "acknowledge", "dismiss", "defer",
                  "snooze", "resume", "reassign", "change", "update_base",
                  "resolve_conflict", "recover_publication"]
```

A head-stamped question goes stale when authority does. That single
design choice is why a quiescent instance had to park conversations
(AX6's `Hold`) and why the replay-or-expire question existed at all.
The coupling is in the data, not in the domain.

## The model: three effect grades, one of which enters the machine

```text
read_only     reply, status
              answer from the repo as it is NOW; serviceable in ANY
              control state, Terminal included (GitHub accepts
              comments on closed PRs; "why did X do Y" outlives merge)

durable_note  acknowledge, dismiss, defer, snooze, resume, reassign
              act on finding/reminder LINEAGE, not on a head; need a
              live instance, indifferent to head currency

head_bound    change, update_base, resolve_conflict, recover_publication
              work on a specific head; require Running; the ONLY
              grade whose outcome carries an epoch/head stamp
```

The whole conversation service is a pure function that never touches
control state:

```python
def service(state: State, kind: str) -> Answer | Apply | Execute | Decline:
    match GRADE[kind], state:
        case "read_only", _:                      return Answer(kind)      # any state
        case _, Terminal(status=status):          return Decline(kind, f"the pull request is {status}")
        case "durable_note", (Running() | Quiescent()):  return Apply(kind)
        case "head_bound", Running(epoch=e, head=h):     return Execute(kind, e, h)
        case "head_bound", Quiescent(expected=x): return Decline(kind, ...)  # explains WHY
```

## Before/after: Hold disappears

```python
# AX6 (inherited coupling) — quiescence must park opaque conversations:
case Quiescent(), ConversationArrived():
    return state, (Hold(),)   # open question: replay on resume? expire?

# AX7 — classify by grade FIRST; the head machine never sees questions:
service(Quiescent(3, "h2"), "reply")   == Answer("reply")            # just answer
service(Quiescent(3, "h2"), "dismiss") == Apply("dismiss")           # lineage, not head
service(Quiescent(3, "h2"), "change")  == Decline("change",
    "the pull request is draft or its head was superseded; re-ask when it is active")
```

`Decline` is attempt-first (AX3: comments always land): the human gets
an immediate, specific explanation and re-asks when ready. No parking
queue exists, so *replay vs expire* is not answered — it is dissolved.

## Executed evidence

```text
10 tests, all passing:

orthogonality      reply/status answered in Running, Quiescent(draft),
                   Quiescent(expected=…), and Terminal — all four
durable notes      dismiss/snooze Apply in every live state including
                   both quiescent flavors; Decline("…is merged") after
                   Terminal
head_bound         change → Execute(epoch=3, head="h2") only while
                   Running; draft/superseded and awaiting-our-push each
                   get a DIFFERENT specific Decline reason; merged
                   declines
nothing parked     all 4 states × 12 kinds yield an immediate outcome;
                   none is a Hold; service never returns a state
one stamp          exactly the four head_bound kinds ever carry
                   epoch/head — production stamps all twelve
coverage           GRADE covers the production vocabulary verbatim
the seam           the AX6 Hold case still fires when fed an opaque
                   ConversationArrived — recorded as exactly what AX7
                   supersedes: the event should be classified before
                   it can reach that machine
```

## Findings

1. **Orthogonality holds; the coupling was in the data.** Nothing
   about answering a question needs authority. Removing the universal
   epoch/head stamp — keeping it only on `Execute` — is sufficient to
   detach the entire conversation concern from the head machine.

2. **AX6's open question is dissolved, not decided.** Hold, replay,
   and expiry were artifacts of parking; with immediate Answer/Decline
   there is nothing to park. The AX6 spike's `Hold` case remains as a
   recorded seam (its machine only sees opaque `ConversationArrived`);
   in a composed design, classification routes by grade before the
   head machine is consulted, and only `Execute` enters it.

3. **Read-only agent scope is the enabling simplification.** The
   conversation agent gets read-only repo access; write authority
   lives solely in the mutation subnet (AX1 shape M) that `Execute`
   routes into. That is what makes "answer in any state, even
   Terminal" safe — a wandering answer cannot push anything.
   (Navigator explicitly chose the reduced scope.)

4. **Classification is spendable work, runnable in any state.** The
   agent call that parses a comment into an intent is disposable
   (AX2's grade vocabulary): it reads, it costs money, it commits
   nothing — so even classification needs no authority fence.

5. **One nuance on durable notes.** The grade claim — dispositions key
   on lineage, not head — matches production's supersession path
   (findings and `finding_lineage` survive `GenerationStart`,
   `host/application.py:346-347`) but NOT its dormancy path: a dormant
   resume takes `prior is None` and starts with empty findings. So
   today, dismissing while draft acts on state that dormancy will
   discard. Under AX6+AX7 unification the natural behaviour is for
   lineage to survive quiescence like any supersession; recorded as a
   divergence for AX5 rather than silently assumed.

## For AX5 (divergence classification)

| Divergence from production | Provisional classification |
| --- | --- |
| Universal `Intent.epoch/head` stamp → stamp only `Execute` | ACCIDENTAL — the stamp does no work for 8 of 12 kinds |
| Quarantine/park of quiescent conversations → immediate Answer/Decline | ACCIDENTAL — parking existed because of the stamp |
| Findings dropped on dormant resume vs surviving quiescence | OPEN — leaning MISSED once quiescence is unified |
| Read-only conversation agent (no write capability) | OPEN — deliberate Navigator scope reduction, revisit if the agent should ever act |

## Verdict

**Promising; continue.** Conversations detach cleanly: three grades,
one pure `service` function, no held state, and only `head_bound`
work ever enters the head machine. Combined with AX6, the control
layer now has no quarantine, no provisional flag, no seed, and one
stopped state. AX4 (typed-port composition) gets simpler again: the
conversation subnet composes with control through exactly one port —
`Execute` — instead of a bidirectional hold/replay protocol.

# Missing canonical History finding

## Question

What happens when `runnable.sqlite3` or one established PR's `history.jsonl` is
lost while other durable state survives?

The investigation distinguishes process reconstruction from destructive file
loss. Hamsterdan reconstructs an Engine, timers, dispatch, and wake posture from
an intact canonical History after process death. It does not reconstruct a
missing canonical History from those projections.

## Runnable loss with intact History

`RunnableIndex` declares itself a disposable, noncanonical hint index. It
quarantines a corrupt database and creates a new one. Startup sweeps enumerate
persisted `history.jsonl` files, load each PR, settle canonical state, and restore
timer posture. Pending webhook custody and Activity terminals can also create
new wakes.

A new webhook is therefore one recovery trigger, not the only one. Intact
History tells Hamsterdan what the workflow has already accepted and what remains
unresolved.

## History loss with surviving hints

`binding.json` is written before the first History file. A binding-only root is
therefore a valid crash cut during first initialization. `ensure_instance_binding`
accepts that state, and `V5Runtime.open` creates a fresh Engine whenever
`history.jsonl` is absent.

The same shape can occur when an established History file is deleted. Current
code has no separate durable marker saying that this PR previously committed
workflow records. The two cases collapse:

- startup preflight accepts the binding-only root;
- startup and periodic sweeps skip it because they enumerate History files;
- the PR remains dormant without another trigger;
- a pending webhook, retained runnable wake, new webhook, or direct active-route
  lookup can open a fresh Engine under the existing binding;
- surviving ingress, dispatch, timer, agent-route, and provider-operation records
  can replay or protect individual operations, but they cannot reconstruct the
  prior marking, decisions, Activity lineage, lifecycle ordering, or timer
  generations.

The behavior is trigger-dependent rather than an exact reconstruction or one
consistent fail-closed disposition.

## Safety consequence

A fresh Engine may reason from current provider truth without knowledge of prior
internal decisions. Stable provider markers and current-authority fencing prevent
some duplicate or stale effects when exact operation identity survives. They do
not restore the workflow.

Old durable publication rows may also remain after their owning
`ActivityRequested` records disappear with History. The repository has no test
for dispatch occurrence reuse or terminal projection in that state.

## Existing evidence

Current recovery tests retain canonical History. They cover:

- process death before webhook acknowledgment;
- process death before a runnable timer hint is updated;
- inline and durable Activity ambiguity;
- timer and runnable reconstruction from accepted History facts;
- replay of one committed ingress or reconciliation manifest.

No current test deletes an established PR's `history.jsonl` while retaining its
binding and other stores.

Relevant implementation:

- `src/hamsterdan/host/binding.py` accepts an existing binding with absent
  History;
- `src/hamsterdan/host/v5/runtime.py` chooses `Engine.create` solely when the
  History path is absent;
- `src/hamsterdan/host/service.py` discovers persisted PRs by globbing for
  `history.jsonl`;
- `src/hamsterdan/host/runnable.py` identifies its database as a noncanonical,
  disposable wake index.

## Interpretation

The project phrase “reconstructible canonical History” is too broad if read as
recovery after History deletion. Current evidence supports reconstruction of
runtime state from intact canonical History after process loss. Torn or missing
canonical History remains an operator data-loss concern, but normal startup does
not consistently detect and fence the missing-file case.

This is an evidence-backed architecture and correctness finding. On 2026-08-24,
the Navigator kept it in ES-009 and chose to continue the broader codebase tour
before exploring a repair. A repair design and delivery classification remain
outside this record until a later candidate gate.

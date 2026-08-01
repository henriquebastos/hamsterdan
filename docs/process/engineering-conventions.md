# Engineering Conventions

1. Import Petrus concepts from their defining ownership modules; never from the
   empty `petrus` root and never from an `impetus` compatibility namespace.
2. The host is the only concrete composition root. Sibling provider and domain
   packages share neutral contracts but do not import one another.
3. The readiness Net owns routing and workflow state. Activities perform typed,
   Petri-agnostic work and return frozen JSON-faithful results.
4. Normalize provider data at the boundary. Do not let SDK or HTTP types cross
   into contracts, readiness, or the Net.
5. Effects are at-least-once. Spend operation identity at the provider call,
   fence current authority immediately before mutation, and recover uncertain
   outcomes lookup-first.
6. Credentials are opaque, redacted, host-owned values. Logs use identifiers,
   request IDs, rate-limit facts, and bounded error classes—not tokens, keys,
   authorization headers, or indiscriminate payloads.
7. Prefer coherent modules over one file per noun, but split responsibilities
   before a provider, workflow, and hosting concern accumulate in one module.

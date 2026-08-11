# Comment admission given one provider owner

Hamsterdan replaced duplicated service/application GitHub comment policy with
one provider-ingress admission function. Authenticated raw observations remain
durable webhook custody; accepted comments cross the host as strict frozen
`AdmittedConversation` values containing audit identity and mention-stripped
text. The application only reconciles current provider truth, binds epoch/head,
and delivers the workflow observation.

The owning policy covers event/action, bot exclusion, actor type, trusted
association, exact configured mention, whitespace, and malformed raw types.
Rejected or malformed comments become terminal without constructing an
application; retries reconstruct admission from raw custody under the same
stable delivery identity.

Focused evidence passed 162 tests. After integration with current `main`, the
full suite passed 574 tests with one external route deselected. Static,
formatting, type, package, and relay gates passed. Independent adversarial
review approved the final fail-closed custody
and security boundary. No Net, lifecycle, Activity, scheduler, storage schema,
or Petrus behavior changed.

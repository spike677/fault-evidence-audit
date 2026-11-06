# Issue / PR investigation handoff

Development draft on the 0.1.8 baseline (6eca253); not a published release.

`python -m faultaudit --state PATH investigation-plan --run RUN_ID --out investigation.json`

The command opens SQLite read-only and writes only the requested JSON outside
the state directory. It does not fetch pages, call a model, register references,
create tasks, change reviews or modify a library. Repeated execution against the
same state produces the same plan.

OpenChamber/OpenCode and Codex consume the same file. Every case is retained,
including cases with only a description. `resources` de-duplicates selected URLs;
`work_items` retain the existing work ID and exact applicable subproblem scope.
Read each supplied resource's body and discussion, relevant linked issue, and
necessary fix diff. Record incomplete components and blocked access honestly;
partial capture can supply observed facts but cannot establish absence.

Use `cases[].search_control.search_allowed` as the only permission to expand
search. The existing default stops expansion after one usable resource. Reading
an applicable issue linked from a selected PR is targeted source investigation,
not permission to keep searching for extra Wiki/DTS/PR types.

`linked_resource_candidates` are exact URLs observed in captured text, marked
`LINK_DISCOVERED` with their parent and citation. They are navigation leads, not
verified associations or root-cause evidence. The external agent first checks
relevance and uses the existing EvidencePackage/model file bridge to submit any
new capture, independent summary and comparison. Nothing is auto-registered.

`independent_technical_facts` contain current summary facts with rechecked exact
snapshot quotations. A case's `root_cause_candidates` additionally require a
current necessary judgment, resolved fact comparison, selected issue label and
quoted scope, plus root-cause support. Rejected, stale, other-event and mismatch
results cannot supply its root cause. Unknown causes explicitly remain
`ROOT_CAUSE_UNCONFIRMED`; titles, links and historical imported causes never fill
this field. Candidates remain model proposals and do not create human ACCEPT.

## Resource summary cards

This draft's six-column presentation was derived after manually reviewing
30 linked source rows and 29 public resources. The public code and tests retain
only synthetic examples, not the reviewed customer material.

`resource_summary_cards` present operator, symptom, root cause, trigger, fix and
verification separately for each current summary task and issue. Each populated
column retains the exact fact ID, original value and snapshot quotation, with
`CITED_MODEL_SUMMARY` as its basis. It does not infer that an older model fact was
an author statement, code analysis or a local test. New extraction instructions
ask the external agent to name those distinctions in the value text.

Missing columns remain `UNKNOWN_IN_CAPTURED_CONTENT` with no cited fact; this
does not assert absence from the full document. Other facts such as version or
build are preserved through `other_fact_ids`. Units, ordering direction and
execution phase stay as reported. Verification reports are not upgraded into
local reproduction, and every card keeps `case_root_cause_confirmed=false`.

Resources expose reading scope, required summary fields, current summary task
IDs and card IDs. Without a current checked summary, `summary_status` remains
`SUMMARY_REQUIRED`; no card is fabricated from the source title or imported
cause. Explicit issue scopes on work items restrict their card references.
Current summaries from different execution tasks or issues are never merged.

`priority_case_ids` and `suggested_execution_order` give a stable read-only hint
to inspect selected GitCode/GitHub URLs first. Other cases remain in the plan.
Resources use `read_priority=1` for those exact hosts and `2` otherwise. These
hints do not change necessary work, search stopping, evidence validity or event
confirmation; words in a title and lookalike hostnames do not confer priority.

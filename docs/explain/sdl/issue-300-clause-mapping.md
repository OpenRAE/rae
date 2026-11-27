# DSL-125 verification mapping

Issue: #300. Requirement state is proposed until merge.

| Clause or acceptance criterion | Implementation | Evidence |
| --- | --- | --- |
| Authored observations and exposure choices | Existing observation boundaries and compiled visibility relations | Existing SEM-226 and v2 runtime tests |
| Control-context, hidden, evaluator, benchmark and role scope | Existing pinned slots and sensitive boundary classes; authored exposure validator | DSL-118 role and reference tests; DSL-125 hidden and withheld tests |
| Compiled intent reaches v2 projection | `project_participant_decision_surface_v2` consumes `AuthoredParticipantExposureV2` | Compiled declaration test, direct and reusable selection variants |
| Initial and later decisions | Existing readiness and terminal-observation anchors | Compiled declaration test, both epoch variants |
| Current delivery authority | `deliver_authored_participant_decision_surface_v2` and ACT-620 records | Distinct delivery-cut policy test and revocation test |
| Unknown, stale or wrong-scope assets | Slot, immutable pin, source visibility and ACT-620 agreement checks | Unknown declaration, missing record, stale pin, episode and participant cases |
| Assurance stays separate | Existing participant-view and assurance contracts | Participant payload excludes raw authorization, provenance and anchor fields |
| Trial configuration selections | SDL owner validation over admitted configuration result | Sealed trial configuration test and existing DSL-118 trial tests |
| Source, result, delivery and provenance trace | Existing context transformation, exposure binding and view digest | Compiled declaration projection and delivery test |
| Content integrity and lifecycle | Existing ACT-620 bounded artifact validation | ACT-620 content, authority and publication tests |
| Compatibility and migration | V2 migration note and normative control-context specification | Existing v1 and v2 tests remain unchanged |

Local checks use explicit relevant test modules.
CI owns repository-wide checks.

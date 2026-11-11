# Evidence custody boundary assessment

Requirement: EXP-717. Scope clarified by the user on 2026-11-03.

RAE owns the path from SDL semantics to backend control through its interface.
The experimentalist owns evidence handling after the result handoff.
The old plan treated RAE as an evidence trust system.
That was outside its job.
The key policies, archive checks, schemas, and custody records have been removed.

The [execution boundary design](issue-273-evidence-custody-design.md) replaces the earlier design.
It maps the existing checks and the refusal gap.
The planner can accept a mode that the shared content proof cannot check.
Planning must reject that request before backend effects.
RAE must not weaken the authored rule or add a separate evidence trust system.

Keep the existing capture dimensions, scoped refinement, coherent backend offers, and shared task/run proof.
Keep RAE's protected execution records and failure accounting.
Do not infer external custody from source names, hashes, or capability flags.
Installed observation integrity providers remain governed by their existing runtime interface.
No new service, key infrastructure, archive implementation, or post-export guarantee is required.

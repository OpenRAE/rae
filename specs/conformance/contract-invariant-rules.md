# Published contract invariant rules

The [rule specification](contract-invariant-rules.json) states each published semantic rule.
Each row gives its host contract, schema location, invariant ID, inputs and rule text.
The schema location determines where the rule applies.
The input paths identify the records that the rule needs.

The specification covers all 180 rule IDs from review revision `036d1af96`.
This includes the 68 Python-only rules named in issue #1780.
Repeated rules retain each host and location.
The rule text preserves the published meaning.
Existing family specifications retain their detailed semantics.

The shared Go validator selects one registered rule for each applicable contract and invariant ID.
A missing rule or missing trusted context cannot produce semantic success.
The `contract/admission` package supplies the rule implementations.
Schema validation remains a separate result.

The [predicate crosswalk](contract-predicate-sources.json) links each invariant ID
to the Go registration, predicate and Python reference owner.
It is an implementation review aid; the published schema and family specification
remain the normative requirements.
Portable admission parity also inventories each recorded decision separately from
the complete CLI command, whose SDL behavior has a separate port owner.

Use a trusted owner for each rule.
Keep raw inputs out of error text.

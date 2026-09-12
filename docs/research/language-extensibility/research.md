# Research basis for issue 1198

Reviewed 2026-09-04. This is a targeted language-design review, not a systematic
literature review or a claim that a standard supplies RAE's domain semantics.
Sources were selected for partial information, structural refinement, open
vocabularies, extension negotiation, provenance, and maintainable DSL design.
Primary specifications, original research, and project/author documentation
support the recommendations below. Repository behavior is established by code
and probes, not inferred from the external literature.

Updated 2026-09-05 against the [maintainer's clarified intent](design-intent.md).
The Linux/Kali and abstract-model examples are product requirements supplied by
the maintainer, not conclusions established by the cited papers. The initial
review underemphasized delegated backend choice and independent observation
demand; this revision deliberately corrects that framing.

## Sources and their implications

| Source | Relevant result or design precedent | Application and limit in RAE |
|---|---|---|
| Mernik, Heering and Sloane, *When and How to Develop Domain-Specific Languages*, ACM Computing Surveys 37(4), 2005, [author manuscript](https://inkytonik.github.io/assets/papers/compsurv05.pdf), especially §§1.2–1.4 | DSLs can support different degrees of executability, including non-executable descriptions; domain analysis, reuse, tooling and maintenance matter. | Partial descriptions and capture documents can be useful without being immediately executable. Review several domain instances before standardizing a profile. This qualitative survey does not quantify RAE redesign cost. |
| Gaster and Jones, *A Polymorphic Type System for Extensible Records and Variants*, NOTTCS-TR-96-3, 1996, [original report](https://web.cecs.pdx.edu/~mpj/pubs/96-3.pdf), introduction and row construction | Typed record/variant extension need not require enumerating every label in a closed type. | A checked extensible record/profile can preserve typing and unknown domain identity. RAE need not adopt ML/Haskell inference or implement full row polymorphism. |
| CUE, [The Logic of CUE](https://cuelang.org/docs/concept/the-logic-of-cue/), type/value lattice, structs, defaults | Concrete values, types and constraints share a subsumption relation; conjunction combines constraints rather than replacing them by order. | Define progressive specificity and composition algebraically. A concrete sibling remains binding when another field is incomplete. This is a semantic precedent, not a recommendation to replace YAML or adopt the entire CUE evaluator. |
| CUE, [closed structs](https://cuelang.org/docs/tour/types/closed/) and [lists](https://cuelang.org/docs/tour/types/lists/) | Records and lists can have explicit local openness/closure. | Distinguish collection membership closure from constraints on existing members. RAE additionally needs stable identity for set-like collections and graph references. |
| W3C, [OWL 2 Primer](https://www.w3.org/TR/2012/REC-owl2-primer-20121211/), §2 | A missing assertion need not be false. | Unknown/unobserved is not absent or forbidden. An ontology's open-world reasoning is not permission for a backend to mutate state; do not equate the two. |
| W3C, [SHACL Recommendation](https://www.w3.org/TR/2017/REC-shacl-20170720/), §4.8.1 | `sh:closed` restricts properties at a selected shape. | Syntactic/shape closure can be local and explicit. Shape validation does not establish complete knowledge of the observed environment or execution support. |
| JSON Schema, [2020-12 Core](https://json-schema.org/draft/2020-12/json-schema-core), §§4.3.3 and 8.1.2; [object composition](https://json-schema.org/understanding-json-schema/reference/object) | Vocabularies identify required semantics; an implementation must refuse schemas requiring an unrecognized vocabulary. Object closure interacts with composition. | Retain checked extension schemas, dialect identity, and required-support negotiation. Do not claim that accepting a generic schema-shaped payload validates RAE's custom invariants. JSON Schema alone does not define realization permission. |
| OASIS, [STIX 2.1 Errata 01](https://docs.oasis-open.org/cti/stix/v2.1/stix-v2.1.html), §2.14 | Open vocabularies allow values outside the suggested list. Consumers may ignore unfamiliar values. | Actual external identity can be preserved without a core catalog release. Diverge from optional ignoring for binding scenario requirements: preserve the data, and reject unsupported execution/comparison semantics. |
| Carpenter, Aboba and Cheshire, [RFC 6709](https://www.rfc-editor.org/rfc/rfc6709.html), especially §§4.4 and 4.7 | Extension design must define namespace and unknown-extension handling. Silent discard can violate security expectations; mandatory extensions require explicit handling or refusal. | Distinguish opaque preservation, optional annotation and required semantic support. Choose extension handling before shipping syntax. The RFC is Informational guidance, not RAE's normative contract. |
| Gustafsson, [RFC 3597](https://www.rfc-editor.org/rfc/rfc3597.html), §§2–5 | Unknown DNS RR types can be transported with numeric identity and generic data representation. | RAE's DNS `other` plus `type_code` is an existing identity-preserving exception. Preserve that route and repair its interaction with realization classification; do not demand another core enum term for every RR type. |
| W3C, [PROV-DM](https://www.w3.org/TR/2013/REC-prov-dm-20130430/), §§2.1.2 and 5.5 | Derivation and specialization are different relations; specialization describes more aspects of the same thing. | Share descriptive structures while preserving authority, time and provenance. A capture may be derived from measurements or contradict intent; it is not automatically a valid specialization of an authored requirement. No PROV serialization compatibility is claimed. |

## Connection to the repository's intellectual lineage

The repository's [lineage map](../../explain/sdl/lineage.md) and
[precedents](../../explain/sdl/precedents.md) distinguish influence from syntax,
code, and artifact derivation. The revision-pinned
[lineage ledger](../../../contracts/provenance/sdl-lineage-ledger-v1.json) remains
the authority for those classifications; this review does not amend it.

The OCR/CyRIS/CACAO/STIX lineage supports declarative scenario structures,
references, and separation from execution. It does not require a universal list
of repository products. OCSF/UCO and SBOM influences help classify and identify
observations, but classifying an observation is different from constraining a
future realization. The bug appears at that transfer of meaning.

ADR-012 explicitly distinguishes closed enums from governed extensions and
warns against turning every local implementation detail into a standardized
term. ADR-033 classifies facts by semantic locus, allowing deep
participant-interactable runtime detail without adopting deployment syntax as
the language. Both support extension and granular author choice.

[ADR-070](../../decisions/adrs/adr-070-realization-envelope-semantics.md) and its
[prior-art review](../realization-envelope/prior-art-and-design-criteria.md)
already use CUE, JSON Schema, bounded domains and subsumption. Reuse that work;
the missing step is preserving the relation throughout nested authoring,
compilation and observations. Its intentionally restricted fragment is an
implementation boundary to extend carefully, not a reason to silently collapse
different declarations to one aggregate mode. Its universal subsumption claim
is not the same question as finding one supported completion for a delegated
request; #1201/#1204 must reconcile the admission boundary, not redefine set
inclusion or infer that one witness proves universal support.

The platform-application correction in #956, the OS/substrate corrections in
#1076/#1077, and the generic external bindings in #986 demonstrate that RAE can
correct an early abstraction while retaining useful typed domain affordances.
These are stronger local precedents than inventing an unrelated universal
configuration mechanism.

ADR-064/066 already separate capture specifications, authored evidence,
scenario-native telemetry, operational observability and derived outputs.
The 2026-09-05 demand-policy correction reuses those boundaries and the
delivered #127/#337/#338 work. It does not invent a sixth universal evidence
plane or replace #341's task/run/study refinement, #340's conformance or #342's
realized-source provenance ownership.

## Resulting design criteria

1. Adding an unfamiliar product, private repository instance or domain profile
   should not require adding a term to a core closed union.
2. A typed partial record must be representable without fabricating its missing
   facts. Its execution can still require more information or backend support.
3. Refining one field must not weaken other fields. Structure closure and value
   restrictions must compose independently and deterministically.
4. Undefined information, known absence, redaction and delegation must remain
   distinguishable at every supported depth and lifecycle boundary.
5. Private extensions must retain identity and payload offline; required
   semantics must be understood before the tool claims validation, equivalence,
   admission or realization.
6. Captures retain scope, coverage, time and evidence basis. Promotion of
   captured facts to requirements is deliberate and records a new authority.
7. The authoring surface remains concise, and the implementation has one
   normalization/comparison/admission substrate shared by standard profiles and
   extensions. Stronger completeness requirements live in selected profiles.
8. Conformance includes negative mutations, private profiles and a non-cyber
   example. Passing one known product fixture is not evidence of extensibility.
9. An inherited open scope delegates unspecified descendants while preserving
   explicit constraints. The backend resolves permitted materialization choices;
   authors do not fill an installation recipe or name every irrelevant field.
10. An abstract model may already be complete. Sparse authoring is not merely
    shorthand for a mandatory hidden concrete-machine model.
11. Realization reportability, measurement demand, collection, retention and
    export are separately scoped. Neither precise requirements nor rich types
    impose unrequested experimental data or independent corroboration.
12. Extensibility is available when detail matters; unmentioned private backend
    mechanisms need no author profile or registration. Selected verification
    claims still require an honest basis, whatever data mode was chosen.

The design proposal is an engineering synthesis of these sources and the
maintainer's requirements. No source proves it correct for RAE; the remediation
plan therefore includes algebraic properties, counterexamples, integration
checks and a usability rehearsal.

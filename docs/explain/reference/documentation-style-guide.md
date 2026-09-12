# Documentation Style Guide

This guide applies to prose documentation in this repository: root Markdown
files, `docs/`, `specs/`, `contracts/`, and `implementations/`.

The audience is technical and academic. Documentation describes the current
repository state. It is not a product page, roadmap, or funding document.

## Stripe Documentation Is The Editorial Exemplar

[Stripe Documentation](https://docs.stripe.com/) is the explicit editorial
exemplar for RAES public documentation. Stripe's docs are approachable because
they move a reader from a concrete task to a visible result with little
friction. RAES adopts that reader experience while retaining its own technical
voice, evidence boundaries, semantics, and visual identity.

Study these official examples:

- [Development environment](https://docs.stripe.com/get-started/development-environment?lang=python)
  leads with a task, states what the reader will achieve, and puts exact
  commands next to the step they complete.
- [Quickstarts](https://docs.stripe.com/quickstarts) helps readers choose a
  route before presenting detail.
- [Checkout quickstart](https://docs.stripe.com/checkout/quickstart) moves in
  small numbered steps from setup to a working result.
- [Create a customer](https://docs.stripe.com/api/customers/create) keeps the
  resource purpose, parameters, request example, and returned result close
  together.
- [Testing](https://docs.stripe.com/testing) places test values and cautions
  where readers use them instead of opening with a caveat wall.

These pages are examples of information design. Do not copy Stripe wording,
brand assets, theme code, product concepts, or API conventions. Do not imply
that Stripe has reviewed or endorsed RAES.

### Translate The Pattern Into RAES

| Stripe pattern | RAES rule |
| --- | --- |
| Task-oriented title | Name the action and its result: "Validate your first scenario." |
| Short outcome-led opening | Tell the reader what they will complete before explaining the system. |
| Early route choice | Offer separate routes for authors, Python users, CLI users, backend implementers, and researchers. |
| Working request or command | Use a current SDL file, Python call, or CLI command that a test executes. |
| Placeholder near first use | Explain each path, name, or value beside the step that introduces it. |
| Visible response or result | Show the output, created file, exit meaning, or next screen immediately after the action. |
| Contextual caution | Put limits beside the claim or command they constrain. |
| Progressive disclosure | Finish first success before linking to concepts, specifications, and full API reference. |

Public entry pages follow this order:

1. State the reader's task and outcome.
2. List only the prerequisites needed for that task.
3. Give exact steps with current commands or code.
4. Explain placeholders where they first appear.
5. Show the expected result.
6. State the boundary of that result.
7. Link to the next task and deeper reference material.

### Before And After

Avoid an abstract opening:

> The scenario validation capability facilitates the establishment of a
> structurally and semantically conformant authored artifact.

Lead with the task and result:

> Validate an SDL file from Python. If the file is valid, RAES returns a
> `Scenario` that your code can inspect.

Avoid separating a command from its meaning:

> Run the formatter. See the reference section for flags and exit behavior.

Keep the outcome with the command:

> Run `raes sdl format --check scenario.sdl.yaml`. Exit code `0` means the
> file parses and already uses the canonical format. The command does not
> provision infrastructure.

### Vale Enforcement

The repository-owned style under `styles/RAES/` enforces the objective part of
this guide on the root README, hosted public docs, and public community
entrypoints. It checks:

- plain words instead of formal substitutes such as "utilize" or "in order
  to";
- dismissive words such as "obviously", "trivial", "simply", and "just";
- promotional terms that replace evidence with praise;
- sentence-case headings without terminal punctuation;
- repeated words, sentence length, and a document-level Flesch-Kincaid target.

Vale does not decide whether a technical claim is true. The repository's
positioning, contract, schema, example, and link checks keep those
responsibilities. Run the complete documentation gate with:

```shell
uv run --project implementations/tooling/python --frozen --no-default-groups nox -f noxfile.py -s docs
```

## Required Stance

- Be accurate before being persuasive.
- State limits, exclusions, and uncertainty directly.
- Prefer short declarative sentences.
- Use present tense for current behavior.
- Use normative language only for repository rules, specifications, contracts,
  and policies.
- Treat prior art as evidence or lineage, not as authority for RAES semantics.

## Prohibited Content

Do not add:

- marketing language
- sales claims
- vague praise
- unexplained superlatives
- roadmap claims
- timelines
- promises about planned behavior
- unsupported maturity claims

Avoid terms such as "powerful", "seamless", "world-class", "production-ready",
"comprehensive", "permanent", and "state of the art" unless the sentence
defines a measurable property and cites evidence.

## Current-State Claims

Every factual claim must be grounded in one of these sources:

- repository source code
- tests
- contracts or schemas
- normative specs under `specs/`
- ADRs under `docs/decisions/adrs/`
- primary external literature or standards

If a feature is absent, say so plainly. Do not imply planned support. Prefer
"not implemented" or "outside the current scope".

## Utility For Readers

Documentation should help a reader decide whether and how to use the current
repository. State the supported task, the relevant entrypoint, and the known
boundary. Include commands only when they match the current CLI or Python API.
Do not hide prerequisites, partial implementations, or validation limits.

## Citations

Use citations for external technical claims, lineage claims, and terminology
borrowed from another system.

Prefer primary sources:

- standards and specifications from the maintaining body
- peer-reviewed papers or technical reports by the originating authors
- official project documentation or source repositories
- published schema catalogs from the maintaining project

Avoid secondary summaries when a primary source is available. If a secondary
source is the only available source, identify it as secondary.

Use inline Markdown links for short references. Use a `## References` section
when a document cites several sources.

## Primary Sources Already Used In This Repository

- [Open Cyber Range SDL](https://documentation.opencyberrange.ee/docs/sdl/)
- [CACAO Security Playbooks v2.0](https://docs.oasis-open.org/cacao/security-playbooks/v2.0/security-playbooks-v2.0.pdf)
- [STIX 2.1](https://docs.oasis-open.org/cti/stix/v2.1/stix-v2.1.html)
- [OCSF](https://ocsf.io/)
- [CybORG](https://arxiv.org/abs/2108.09118)
- [CALDERA planning and acting with unknowns](https://www.mitre.org/sites/default/files/2021-11/prs-18-0944-1-automated-adversary-emulation-planning-acting.pdf)
- [IEEE HLA 1516 family](https://standards.ieee.org/ieee/1516/3744/)
- [SISO Cyber DEM](https://cdn.ymaws.com/www.sisostandards.org/resource/resmgr/standards_products/siso-std-025-2023_cyberdem.pdf)

## Terminology

- Define terms at first use when they are RAES-specific or overloaded in the
  literature.
- Use RAES terms consistently with the current specs, contracts, and code.
- Do not rename an external concept when citing a source.
- Do not import semantics from cited systems unless the RAES document states
  the adopted subset or difference.
- Distinguish authored scenario meaning, processor behavior, backend behavior,
  runtime state, and evidence artifacts.

## Structure

- Put the main claim first.
- Keep sections short.
- Use tables only when comparison is clearer than prose.
- Use examples only when they match current parser, schema, or contract
  behavior.
- Link to the closest authoritative repository artifact instead of restating
  long rules.

## Review Checklist

- Does the document describe current repository behavior?
- Are external claims cited to primary sources?
- Are limits and exclusions explicit?
- Are RAES terms used consistently with the specs, contracts, and code?
- Is all promotional or forward-looking language removed?

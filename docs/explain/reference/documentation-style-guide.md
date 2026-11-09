# Documentation style guide

This reference gives the writing and review rules for maintained prose in this
repository. It includes root files, `docs/`, `specs/`, `contracts/`, `examples/`,
`implementations/`, and agent instructions. Use these rules for source comments
and generator prose too. Do not use the file extension alone to identify prose.

The readers do technical work and research. Give the behavior of the supported
release or specified commit. Give limits and uncertainty beside each claim.

## Stripe documentation is the editorial exemplar

[Stripe Documentation](https://docs.stripe.com/) is the example for RAES public
documentation. Its pages take the reader from a task to a visible result.
Keep RAES terms, evidence boundaries, semantics, and visual identity.

Read these official examples:

- [Development environment](https://docs.stripe.com/get-started/development-environment?lang=python)
  gives a task and its result first. It puts each command beside its step.
- [Quickstarts](https://docs.stripe.com/quickstarts) helps readers select a
  route before it gives detail.
- [Checkout quickstart](https://docs.stripe.com/checkout/quickstart) moves in
  small numbered steps from setup to a working result.
- [Create a customer](https://docs.stripe.com/api/customers/create) keeps the
  resource purpose, parameters, request example, and returned result close
  together.
- [Testing](https://docs.stripe.com/testing) places test values and cautions
  where readers use them. It does not put all cautions at the start.

Use these examples for the order of information. Do not copy text, brand assets,
theme code, product concepts, or API conventions. Do not suggest that Stripe
gives approval to RAES.

### Translate the pattern into RAES

| Stripe pattern | RAES rule |
| --- | --- |
| Task-oriented title | Give the action and its result: "Validate your first scenario." |
| Short outcome-led opening | Give the result first. Then explain the system. |
| Early route choice | Give separate routes for authors, Python users, CLI users, backend implementers, and researchers. |
| Working request or command | Use a current SDL file, Python call, or CLI command that a test executes. |
| Placeholder near first use | Explain each path, name, or value beside the step that introduces it. |
| Visible response or result | Show the output, created file, exit meaning, or next screen immediately after the action. |
| Contextual caution | Put each limit beside its claim or command. |
| Progressive disclosure | Complete the first task. Then link to concepts, specifications, and the full API reference. |

Routing pages help readers choose an existing destination. Use short task
descriptions and descriptive links. Keep setup steps and detailed explanations
at their destinations. Do not repeat the content tree under four labels.

Task pages follow this order:

1. Give the reader's task and result.
2. Give only the prerequisites for that task.
3. Give exact steps with current commands or code.
4. Explain placeholders where they first appear.
5. Show the expected result.
6. Give the boundary of that result.
7. Link to the next task and deeper reference material.

### Before and after

Do not start with an abstract description:

> The scenario validation capability facilitates the establishment of a
> structurally and semantically conformant authored artifact.

Start with the task and result:

> Validate an SDL file from Python. If the file is valid, RAES returns a
> `Scenario` that your code can inspect.

Do not put a command and its meaning in separate sections:

> Run the formatter. See the reference section for flags and exit behavior.

Keep the outcome with the command:

> Run `raes sdl format --check scenario.sdl.yaml`. Exit code `0` means the
> file parses and already uses the canonical format. The command does not
> provision infrastructure.

### Vale enforcement

Vale uses the RAES rules in `styles/RAES/` through `.vale.ini`.
It checks plain words, dismissive words, promotional claims, heading case,
heading punctuation, repeated words, sentence length, and a reading score.
Vale is a style linter. It does not check code accuracy, page purpose, or full
ASD-STE100 conformance. A reading score does not replace technical review.

The existing `docs` and `docs-local` lanes check root community pages and public
Markdown. Both also call the shared `docs-prose` stage for selected `.md` and
`.rst` files across the repository. This includes `docs/explain/` and
`examples/README.md`. Canonical CI gives this stage its verified base revision.
The full verification graph forwards the same base to the documentation lane.

The stage does not lint unchanged legacy pages or require a corpus rewrite.
It reports exact protected files from the existing ADR pin index and historical
catalog, and superseded or deprecated ADRs, for manual review. It also excludes root `CHANGELOG.md` and
`THIRD_PARTY_NOTICES.md`. These exclusions do not give permission to change
protected text. New maintained passages still need the checks below.

Issues [#1509](https://github.com/OpenRAE/rae/issues/1509) and
[#1562](https://github.com/OpenRAE/rae/issues/1562) describe these coverage gaps.
[#1931](https://github.com/OpenRAE/rae/issues/1931) delivers changed-path coverage.
The earlier issues stay open. This change does not claim a corpus cleanup.

#### Set up the existing tools

Run these commands from the repository root. Use the supported Python 3.14
and the locked uv version from the contributor setup. No personal skill is
needed. The frozen environments use the repository's existing package sources.

```shell
uv sync --project implementations/tooling/python --frozen --no-default-groups
uv sync --project implementations/python --frozen --extra docs
vale_bin="$(uv run --project implementations/tooling/python --frozen --no-default-groups python -c 'from tools.vale_tool import ensure_vale; print(ensure_vale())')"
export PATH="$PWD/implementations/python/.venv/bin:$PATH"
"$vale_bin" --version
rst2html --version
```

`ensure_vale()` uses the reviewed artifact lock and checks the downloaded bytes.
It installs a local binary. It does not send documentation to a service.
Do not replace it with an unpinned download or a personal installation.

| Component | Source and version | License and installation route |
| --- | --- | --- |
| Vale | [vale-cli/vale v3.15.2](https://github.com/vale-cli/vale/tree/v3.15.2) | MIT. Use `tools/vale_tool.py` and `implementations/tooling/artifacts.lock.json`. |
| RAES styles | `styles/RAES/` and `.vale.ini` at the checked-out revision | Repository MIT license. The checkout includes the styles. |
| docutils | 0.22.4 in `implementations/python/uv.lock` | Public domain with file-specific exceptions in `COPYING.rst`. Use the frozen docs environment. |
| Sphinx and MyST | 9.1.0 and 5.0.0 in the same lock | BSD-2-Clause and MIT. Use the frozen docs environment. |

The setup review included the existing local `documentation` skill.
Its `SKILL.md` digest is
`f2f56b93723c273fccea271e2622d292f5622ea2e9af23c00e2bfaa3eb4cfa8e`.
Its local license file gives MIT-licensed upstream guidance. It does not
give a public source for the complete skill. Do not copy a personal skill.
The public [ste-review v0.10.1](https://github.com/TudorAndrei/ste-cli/tree/v0.10.1/skill/ste-review)
has an MIT license, but its procedure needs a separate `ste` command.
This setup uses the existing tools and this maintained guide, as #1931 specifies.
It installs neither that analyzer nor a replacement skill.
Agents start with [AGENTS.md](../../../AGENTS.md).

#### Check explicit changed paths

Use the setup above. Give the shared nox stage the maintained files you changed.
These commands cover Markdown, reStructuredText, and repository-only prose:

```shell
uv run --project implementations/tooling/python --frozen --no-default-groups nox -s docs-prose -- docs/public/index.md
uv run --project implementations/tooling/python --frozen --no-default-groups nox -s docs-prose -- docs/public/api/index.rst
uv run --project implementations/tooling/python --frozen --no-default-groups nox -s docs-prose -- docs/explain/reference/documentation-style-guide.md AGENTS.md
```

For a comparison with the integration branch, use:

```shell
uv run --project implementations/tooling/python --frozen --no-default-groups nox -s docs-prose -- --base-rev origin/dev
```

With no arguments, the stage selects working-tree and untracked files.
Use `--staged` for staged files. It keeps spaces and newlines in filenames.
It refuses paths outside the repository and malformed protection catalogs.

Exit code `0` means that Vale found no enabled style errors.
If the result is nonzero, find the cause. Correct real prose errors.
Then run the same command again. If a proposed change changes the meaning, keep the accurate technical term. Record a narrow exception and its reason in the PR.

Vale 3.15.2 needs `rst2html` on `PATH` for `.rst` files.
The [Vale reStructuredText reference](https://docs.vale.sh/formats/restructuredtext)
gives this dependency. The pinned version cannot check every Sphinx
extension's generated text. Examine that text at its source and in rendered HTML.
Do not claim support for features documented only for newer Vale versions.

For `.adoc`, `.txt`, source comments, or another format, examine meaning and
style directly. Give the format and checks in the PR. Ask the documentation
maintainer to examine unsupported markup. Do not omit maintained prose.
Do not add another analyzer to bypass this review.

Full documentation checks run in CI. The existing build remains Sphinx/MyST.
The `docs-local` lane checks the source boundary, examples, HTML, and output
inventory. The `docs-links` lane checks external links. Keep local tests targeted
and pre-commit limited to hygiene and secrets.

Issue [#1799](https://github.com/OpenRAE/rae/issues/1799) owns the Go documentation guards.
Issue [#1803](https://github.com/OpenRAE/rae/issues/1803) owns the Go documentation build
and instruction migration. Keep equivalent changed-path checks at cutover.
Issue [#1804](https://github.com/OpenRAE/rae/issues/1804) owns publication.
Until cutover, published usage gives the behavior of the supported Python release.
Before you give an SDL, runtime, or backend artifact name, find its source owner.

## Select one reader purpose

Use the [Diataxis compass](https://diataxis.fr/compass/) to select the page's purpose.

| Reader need | Form | Content |
| --- | --- | --- |
| Learn by doing | Tutorial | Guide a safe exercise to a visible result. |
| Complete a known task | How-to guide | Give prerequisites, steps, success, failures, and recovery. |
| Find an exact fact | Reference | Give inputs, outputs, constraints, errors, and versions. |
| Understand a subject | Explanation | Explain reasons, relationships, evidence, and open questions. |

An entry page can link to these forms. Divide mixed material when this helps
the reader. Keep existing page addresses and useful heading links.
If a published page moves, add and test its redirect. Do not create empty
sections or four new directory trees to classify existing pages.

## Keep technical meaning

Use [ASD-STE100's official source](https://www.asd-ste100.org/) for definitive
rules and vocabulary. Do not copy its dictionary into this repository.
Use technical terms accurately. Examine a word's meaning and part of speech in
context. Do not accept a substitution only because a checker suggests it.

Keep facts, quantities, units, conditions, qualifiers, commands, and identifiers
unchanged. Keep obligations unchanged. Do not turn "may" into "must".
If a shorter word changes the meaning, restructure the sentence or keep the
technical term. Use one name for each thing. Give each paragraph one topic.

For procedures, put prerequisites and conditions before the affected action.
Use the imperative. Give one instruction per sentence. Use at most 20 words per
instruction and 25 words per descriptive sentence. Keep paragraphs to six
sentences. Use the active voice when the source gives the actor.
Do not invent an actor to remove passive voice.

## Compare each section with sources

Read the code, configuration, command help, tests, and applicable contracts.
Check current claims at the supported release or stated commit. Check historical
claims at their historical revision. Use primary sources for external claims.
If behavior is absent or unverified, give that limit.

Code shows observed usage behavior. Normative specifications and contracts
give required meaning. If they conflict, report the conflict and get a resolution.
Do not silently rewrite a normative obligation to match an implementation defect.

Record these facts in the delivery PR for each rewritten section:

- Page, purpose, source paths, and source revision.
- Commands, platform, versions, exit codes, and observed results.
- Corrected differences, unverified claims, and preserved exceptions.
- Rendered review, link checks, and any redirect test.

## Keep protected material

Use the writing rules for maintained prose at its source.
Use these narrow exclusions. Do not exclude an entire directory of maintained
pages because it contains historical material.

| Material | Treatment |
| --- | --- |
| Generated output | Keep output identity. Edit generator prose or source comments. Then regenerate through the existing build. |
| Pinned evidence and accepted decisions | Keep exact captured or pinned text. Add maintained context or use the required amendment process. |
| Legal notices | Keep license and notice text unchanged. Improve the surrounding introduction or navigation. |
| Quotations | Keep the source's exact words and citation. Revise surrounding prose. |
| Code blocks and inline literals | Keep literal commands, output, identifiers, and data intact. Test commands where applicable. |

Vale normally excludes code and inline literals. It may report a protected
quotation in an otherwise maintained page. A finding does not give permission
to rewrite protected text. Use a rule-specific Vale comment only when that
source permits an annotation. Set the rule to its initial value after the passage.
Record the rule, path, passage, and reason in the PR.

The shared stage reads exact identities from
`docs/decisions/adrs/adr-index.yaml` and
`tools/policy/historical_identity_records.json`. It also reports each superseded
or deprecated ADR, because ADR-059 freezes its text. It does not exclude whole
trees or exempt operational bindings. Existing pin and policy gates stay in force.

For each reported protected file, examine the source and meaning.
Do a separate Vale check of each new maintained introduction or amendment.
Use the existing stdin interface, with the source path and format:

```shell
"$vale_bin" --no-global --config=.vale.ini --ext=.md --path=docs/decisions/adrs/adr-014-nox-as-canonical-verification-graph.md <<'PROSE'
## Amendment

The command checks the file.
PROSE
```

Replace the sample with the actual maintained passage. Keep its markup,
conditions, terms, and obligations. Use `--ext=.rst` for reStructuredText.
Record the exact source path, passage, command, result, and manual review in the
PR. Do not rewrite or annotate pinned historical text to clear a style finding.

## Examine the rendered result

Render public pages with the existing build. Examine repository-only prose in
a local Markdown view. Check heading order, descriptive link text, and text
alternatives for diagrams. Test keyboard access when navigation or controls
change. Do not use color alone to convey meaning. Keep commands copyable and
explain placeholders beside their first use. Record the view and results in
the PR. A source-only review does not show rendered accessibility.

## Required stance

- Be accurate before being persuasive.
- Give limits, exclusions, and uncertainty directly.
- Use short declarative sentences.
- Use present tense for current behavior.
- Use normative language only for repository rules, specifications, contracts,
  and policies.
- Use prior art as evidence or lineage. Do not use it as authority for RAES semantics.

## Prohibited content

Do not add:

- marketing language
- sales claims
- vague praise
- unexplained superlatives
- roadmap claims
- timelines
- promises about planned behavior
- unsupported maturity claims

Do not use promotional adjectives unless the sentence gives a measurable
property and cites evidence. The rule tokens are in `styles/RAES/AvoidHype.yml`.

## Current-state claims

Every factual claim must have one of these sources:

- repository source code
- tests
- contracts or schemas
- normative specs under `specs/`
- ADRs under `docs/decisions/adrs/`
- primary external literature or standards

If a feature is absent, tell the reader. Do not suggest planned support.
Use "not implemented" or "outside the current scope".

## Utility for readers

The aim of documentation is to help a reader use the current repository.
Give the supported task, the applicable entrypoint, and the known boundary.
Include commands only when they match the current CLI or Python API.
Do not hide prerequisites, partial implementations, or validation limits.

## Citations

Use citations for external technical claims, lineage claims, and terminology
borrowed from another system.

Use primary sources when possible:

- standards and specifications from the maintaining body
- peer-reviewed papers or technical reports by the originating authors
- official project documentation or source repositories
- published schema catalogs from the maintaining project

Use a primary source when one is available. If only a secondary source is
available, give its status as a secondary source.

Use inline Markdown links for short references. Use a `## References` section
when a document cites several sources.

## Primary sources already used in this repository

- [Open Cyber Range SDL](https://documentation.opencyberrange.ee/docs/sdl/)
- [CACAO Security Playbooks v2.0](https://docs.oasis-open.org/cacao/security-playbooks/v2.0/security-playbooks-v2.0.pdf)
- [STIX 2.1](https://docs.oasis-open.org/cti/stix/v2.1/stix-v2.1.html)
- [OCSF](https://ocsf.io/)
- [CybORG](https://arxiv.org/abs/2108.09118)
- [CALDERA planning and acting with unknowns](https://www.mitre.org/sites/default/files/2021-11/prs-18-0944-1-automated-adversary-emulation-planning-acting.pdf)
- [IEEE HLA 1516 family](https://standards.ieee.org/ieee/1516/3744/)
- [SISO Cyber DEM](https://cdn.ymaws.com/www.sisostandards.org/resource/resmgr/standards_products/siso-std-025-2023_cyberdem.pdf)

## Terminology

- Explain RAES-specific terms at first use. Explain terms with more than one
  meaning in the literature.
- Use each RAES term with the same meaning as the specs, contracts, and code.
- When you cite a source, keep the external concept's name.
- Do not import semantics from cited systems unless the RAES document gives
  the adopted subset or difference.
- Keep authored scenario meaning, processor behavior, backend behavior,
  runtime state, and evidence artifacts separate.

## Structure

- Put the main claim first.
- Keep sections short.
- Use tables only when comparison is clearer than prose.
- Use examples only when they match current parser, schema, or contract
  behavior.
- Link to the closest authoritative repository artifact. Do not repeat long rules.

## Review checklist

- Does the document give current repository behavior?
- Does each external claim cite a primary source?
- Does the text give limits and exclusions?
- Does each RAES term have the same meaning as the specs, contracts, and code?
- Is the text free from promotional and forward-looking language?

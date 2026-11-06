# Documentation tools verification

This reference records the checks for issue #1931. It gives the source and
review evidence for its delivery PR. It does not replace the style guide.

## Revision and scope

The source revision is `665b747f882c1bfee717d15e266c9bb1db84ec07`.
The candidate adds changed-path Vale checks to shared nox stages and updates the
existing style guide and `AGENTS.md`. Product code, published pages, legal text,
pinned evidence, generated output, and pre-commit hooks are unchanged.

The style guide is reference. `AGENTS.md` remains an agent entry page.
This record is reference. No page path or published URL changes.

## Section and source review

All paths in the table are repository-relative. The source revision above
applies unless the row names the candidate.

| Rewritten section | Sources and observed result | Correction or review result |
| --- | --- | --- |
| Guide opening and Stripe exemplar | Existing guide and its linked official Stripe examples | Expanded the stated scope to examples and agent prose. Replaced praise with the visible reader outcome. Kept the prohibition on copying. |
| Vale enforcement | `tools/nox_support/test_lanes.py`, `noxfile.py`, `.vale.ini`, `styles/RAES/` and candidate canonical workflow | Corrected the coverage claim. The old reader-style check selects only Markdown. The shared prose stage selects maintained Markdown and reStructuredText across the repository. |
| Tool setup and explicit paths | `tools/vale_tool.py`, `tools/tool_versions.py`, `implementations/tooling/artifacts.lock.json`, `implementations/python/uv.lock` | Compared the source, version, license and installation route with the locked files. The commands below passed in fresh environments. |
| Skill availability | Examined local `documentation` skill and its license notice. Public `ste-review` v0.10.1 and its MIT license | The local skill has no verified public source for its complete text. The public skill needs another analyzer. Used the issue's tools-and-guidance fallback. Made no copy of skill content. |
| Reader purpose | [Diataxis compass](https://diataxis.fr/compass/) | Checked each of the four forms against its reader need. Kept entry-page routing and useful heading links. |
| Technical meaning | [Official STE Issue 9](https://www.asd-ste100.org/assets/files/ASD-STE100_ISSUE9.pdf) | Examined meaning in context. Used the existing local copy of official Issue 9. No standard text or dictionary enters the repository. |
| Source verification and normative conflicts | ADR-009 and its schema-authority amendment. Current code and contracts | Kept required meaning separate from observed behavior. A conflict needs resolution. It does not give permission for a silent contract change. |
| Protected material | ADR-059, ADR-096, `tools/policy/historical_identity_records.json`, release-please configuration | Kept protected text. Gave narrow exceptions and required examination of maintained surrounding prose. |
| Rendered review | Existing Markdown parser and local Chrome file views of all three changed prose pages | Heading order, heading anchors, link text, local targets and keyboard focus passed. See the rendered observations below. |
| Prohibited content | Existing guide and `styles/RAES/AvoidHype.yml` | Replaced the inline list of prohibited words with the owning rule path. Kept the measurable-evidence exception. |
| Agent entry | Existing `AGENTS.md` and candidate style guide | Added one route to the existing guide. Kept policy and targeted-test obligations. Changed heading case without changing anchors. |

The remaining guide sections keep their existing obligations and reference
links. No runtime, backend, schema, or normative specification changed.

## Language and meaning review

The language review used the existing local copy of official ASD-STE100 Issue 9,
dated 2025-01-15. The PDF SHA-256 is
`d1f4ea9e7cd6e46b47aa9057209f99e78c0e9cfc4e27a5b07895b05c1a166431`.
The official URL returned HTTP 403 during the web check. The local PDF supplied
the definitive rules and dictionary for this review. No copy enters the repository.

The review covered all maintained prose in the style guide, agent entry, and
this record. Code, paths, identifiers, product names and existing quotations
kept their exact text.

| Rules | Finding and correction |
| --- | --- |
| 1.1–1.4, 9.1–9.2 | The guide used `state`, `preserve`, `establish`, `verify` and `inspect` as general verbs. Changed those instructions to give information, keep meaning, compare sources or examine text. Each correction keeps the original condition and obligation. |
| 1.5–1.11 | Kept the subject terms Markdown, reStructuredText, normative contract, pinned evidence, heading anchor and STE conformance. They identify software or documentation concepts. Used the same term for each concept. |
| 1.12–1.13 | Kept `lint`, `render`, `parse`, `install`, `download` and `run` for their computer processes. Kept general instructions separate from these technical verbs. |
| 1.14 | Used American English in maintained prose. Kept exact external titles and identifiers. |
| 2.1–2.2 | Divided long noun groups. For example, the setup now gives an environment for each project, not an unexplained chain of modifiers. |
| 3.1–3.7 | Removed general verbal `-ing` forms, such as `before presenting detail`. The revised sentence gives the actor and uses `before it gives detail`. Kept the simple present, simple past and imperative forms. |
| 4.1–4.5 | Kept articles and connecting words. Divided clauses without removing conditions. Used lists and tables for related facts. |
| 5.1–5.5 | Kept one command in each instruction. Put the branch-name condition before the UID command in `AGENTS.md`. Separated the error correction from the command to repeat the check. |
| 6.1–6.6 | Kept descriptive sentences within 25 words and instructions within 20 words. Kept each paragraph to one topic and no more than six sentences. Put setup before the commands that need it. |
| 7.1–7.3 | No safety instruction or risk classification changed. Kept restrictions beside their affected material. |
| 8.1–8.7 | Removed semicolons from maintained prose. Kept punctuation in literal commands and identifiers. Counted each identifier as one item. |
| 9.3–9.4 | Replaced general phrasal constructions where they obscured the action. Kept one name for each tool and format. |

The review kept the distinction between observed behavior and normative meaning.
It did not turn permission into obligation. Vale supplied a separate style check,
not a substitute for this language and meaning review.

## Clean setup and commands

Platform: Linux x86_64. Interpreter: CPython 3.14.7. Installer: uv 0.13.4.
Used a new temporary HOME, empty uv cache, and new environments.
Set `UV_PROJECT_ENVIRONMENT` separately for each project to isolate its files.
No personal skills or existing Vale installation were available in that HOME.

| Command or check | Observed result |
| --- | --- |
| `uv sync --project implementations/tooling/python --frozen --no-default-groups` | Exit 0. Installed the frozen tooling environment. |
| `uv sync --project implementations/python --frozen --extra docs` | Exit 0. Installed the frozen project and docs environment. |
| `tools.vale_tool.ensure_vale()` with a new installation root | Exit 0. Acquired and verified the locked archive and installed binary. |
| `vale --version` | Exit 0. `vale version 3.15.2`. |
| `rst2html --version` | Exit 0. Docutils 0.22.4, Python 3.14.7, Linux. |
| Explicit Vale checks with `.vale.ini` | Exit 0. No findings in `docs/public/index.md`, `docs/public/api/index.rst`, the style guide, and `AGENTS.md`. |

Vale's MIT license and approved route are in the artifact lock, under ADR-106.
Read the upstream license at tag v3.15.2 too. Checked Sphinx's BSD-2-Clause
and MyST's MIT notices in the installed distributions. Checked docutils'
`COPYING.rst`, including its file-specific exceptions. No new dependency was added.

## Behavioral checks

Run the focused regression module with:

```shell
RAES_REQUIREMENT_UID=GOV-901 uv run --project implementations/python --frozen python -m pytest -q -m 'not fuzz' implementations/python/tests/test_issue_1931_documentation_tools.py
```

The tests execute the shared private nox stage with real pinned Vale.
A separate wiring test confirms that CI passes its verified base to the same
documentation lane. The full nox graph forwards the shared arguments too.
These fixtures replace only acquisition. The clean setup above tested actual
acquisition separately.

The initial tests failed because the changed-prose check was absent.
The independent review found two gaps in the first candidate: CI-only
orchestration and whole-file lint on protected records. Both needed repair.
The check then caught a real `RAES.PlainWords` violation in all three page forms.
Replacing the prohibited word with `Use` cleared the violation.
An unchanged page with known violations did not enter the selection.

Additional cases cover filenames with spaces, newlines, or an initial hyphen.
They also cover literal code, non-prose diffs, Git failures, staged and untracked
files, renames, deletions, malformed catalogs, and unsafe paths. A nested `docs/CHANGELOG.md`
case shows that root exclusions keep maintained nested pages covered.
The path specifications name the two excluded root files explicitly.

Three manual mutations of the first candidate each failed the relevant case:
omit reStructuredText, omit repository-only prose, and suppress Vale's failure
status. The repaired shared stage has the same behavioral coverage. Four further
mutations also failed: omit reStructuredText, omit ADR protection, bypass path
containment, and disconnect the shared documentation stage.
Restored the original command after each mutation.

The final focused prose module passed all 33 cases. Its pure CI wiring case
runs in fast feedback. The 32 cases that need installed Vale or subprocess
fixtures stay in the integration lane. The installer module
`implementations/python/tests/test_vale_tool.py` passed all three cases.
The existing nox tests and operational-binding consumer test passed 35 cases. File-local repository policy, Ruff and changed-document Vale
also passed. Full documentation, policy and test lanes remain in CI.

## Exclusions and preserved records

The shared stage excludes root `CHANGELOG.md`, which release-please generates,
and root `THIRD_PARTY_NOTICES.md`, which contains legal notices.
It also reports exact protected paths from the ADR pin index and historical
catalog. It does not exempt whole directories or operational bindings.
Malformed catalogs and unsafe paths fail. Existing policy pin gates stay in force.
The Ground Control configuration gained the required module mapping. Its
operational-binding digest was updated to match that current configuration.
The historical record digests and service project designations did not change.
For every reported protected file, new maintained passages need source/meaning
review and a Vale stdin check. The PR must record each path, passage and result.
No protected file changed in this delivery.

No preserved quotation, accepted ADR, pinned capture, code block or generated
artifact was rewritten. No maintained changed prose page was omitted.
Other formats have an explicit maintainer-review route in the style guide.

Issues #1509 and #1562 remain open. This delivery covers their changed-file
gaps. It does not claim to clear all legacy findings.
Issues #1799 and #1803 own equivalent Go checks and the Go build migration.
Issue #1804 owns publication. The supported Python site remains the default.


## Independent review repairs

The user authorized an independent read-only review after the automatic
acceptance reviewer could not observe required evidence in its sandbox.
The independent verdict was `ship-with-fixes`.

The repair structure is local commit
`1071f7f6862e917136291dd090c93cbb8761e250`. Python compilation, file-local
policy, and 34 existing nox tests passed. The new acceptance cases failed for
the safe refusing stub. An independent design review approved the structure
before implementation.

The existing nox module owns selection and Vale execution. It reuses the common
selector grammar, NUL-safe Git collection, catalog validators, and path guards.
`docs-prose` gives targeted feedback. `docs-local` and `docs` call the same stage.
Canonical CI passes the verified base through `docs-local`.
No new analyzer, dependency, service, or publication destination was added.
The actual `docs-prose` command passed on the five named Markdown and
reStructuredText pages in the retained clean HOME and frozen environments.
A protected ADR check reported the exact manual-review obligation. The guide's
Vale stdin example passed separately. `UV_PROJECT_ENVIRONMENT` selects the
docutils installation used by the linter.

## Rendered observations

Rendered all three changed prose pages with the existing Markdown parser and
examined their local HTML in headless Chrome. This includes this evidence
record. No page was hosted or uploaded.

| Check | Observed result |
| --- | --- |
| Heading order | One first-level heading per page. no omitted heading levels. |
| Heading links | Every previous heading anchor remains present. |
| Descriptive links | Link text names its destination. Relative file targets exist. |
| Keyboard access | Tab reached the guide link in `AGENTS.md` and the first guide link. Focus was visible. Links use native anchors. |
| Text alternatives | No image or diagram changed. No custom control was added. |
| Color | No meaning depends on color. Commands remain copyable text. |

The browser observations cover repository-only prose. This PR changes no public
page, site navigation, redirect, or publication workflow.

## Required corpus promotion

The 33 new tests change the Python test tree. The existing parity workflow
therefore collected fresh public inputs in CI, as required by
`docs/DEVELOPMENT_WORKFLOW.md`. The new capture retains all 19,706 previous test
identities and adds the 33 documentation tests. It contains 18,134 distinct
public inputs. The product, contracts, examples, collector and environment
source identities are unchanged.

CI run `42183463854`, job `127783090198`, produced artifact `13488580027`
from merge revision `2efca1db4e77e24c1344ded77a0ca9d584ac18df`. Its decoded
input credential scan passed before upload. The artifact contains 45,304 files.
Its ZIP SHA-256 is
`f316e41b742436c3cd83deca4df4ea78dc8fb82a89c9eabab31828f1212b45a0`.

The fresh capture replaces 6,886 input descriptors. Representative differences
include generated UUIDs, an ephemeral loopback registry port and SQLite backup
bytes. The complete generated artifact supplies the replacement corpus. No
expected result or source identity is edited by hand. Hosted checks verify
reproduction and the Go runners against the promoted cases.

The independent review approved this promotion. It confirmed complete coverage,
unchanged non-regression inventory and identical replacement groups by surface,
command, arguments, origin tests and filenames. Fourteen focused storage and
comparison tests passed. The promoted files match every ZIP entry byte for byte.

## Sonar maintainability repair

The first complete hosted analysis found two complexity findings in the prose
stage. Private helpers in the same existing module now own path selection and
protected-catalog loading. The stage coordinates those helpers and Vale.
The 33 existing behavior cases passed after extraction. No test source,
selection rule, protected identity or command behavior changed.

# Golden parity corpus

Issue #1778 records the machine-readable behavior of the Python implementation as a golden corpus.
The Go port checks each Go component against it.
After the cutover, the corpus stays as a regression suite.

## Problem

The Go port must keep the SDL and the published contracts the same for consumers.
Only machine-readable behavior is parity data.
Help text and free-text messages may change.
The check must compare each Go component with recorded Python results, not with hand-written expectations.

## Architecture

`tools/parity_corpus.py` records the corpus from the Python implementation.
The corpus is in `implementations/go/internal/parity/testdata`, inside the Go module.
Mutation testing copies only the module, so the Go tests read no file outside it.

| Part | Content |
| --- | --- |
| `manifest.json` | The corpus schema `raes-parity-corpus/v1`, content digests of reference source, recorder and environment locks, and the Python version |
| `inputs/<sha256>` | Each input file once, under the SHA-256 digest of its content |
| `cases/<surface>/<command>/<sha256 of the name>.json` | One recorded invocation: name, surface, command, arguments, input digests, and result |

The `cli` surface runs `raes semantic` commands on the SDL examples and the contract fixtures.
Its result is the exit code and the JSON standard output, without the free-text `message` of each diagnostic.
The `schema` surface validates each contract fixture against its published schema, and its result is the verdict.
The case file names use digests, because repository path policy reserves some fixture path names.

The Go package `internal/parity` loads the corpus and verifies each input against its digest.
Each Go port adds a runner for the commands that it implements.
`TestCorpus` compares numbers exactly, including large integers and decimal
exponents, and fails a runner that has no case. Its independent implemented-command
inventory requires `canonical encode`; deleting that runner fails the check.
`RAES_PARITY_COMPLETE=1` fails any recorded command without a runner and is required
at cutover. During incremental porting, only genuinely unported commands may skip.
The manifest binds source identity by the sorted Python package paths and bytes,
not by an unstable branch-tip commit. The recorder and Python lock/configuration
have separate digests, and the interpreter version is recorded explicitly.

The CI job `parity-corpus` records the corpus again from the Python implementation.
It fails when one corpus file differs, and it uploads the fresh corpus for review.
Recordings run in CI only.

## Security and data flows

The protected assets are the integrity of the corpus and the integrity of the parity verdict.
The recorder runs the Python implementation of the repository on repository inputs.
A corpus edit by hand is untrusted, because it could make a wrong Go result pass.

```mermaid
flowchart LR
    subgraph Repository
        Py[Python implementation]
        In[SDL examples and contract fixtures]
        Corpus[(Committed corpus)]
        Go[Go components and runners]
    end
    In --> Rec[parity_corpus.py in the parity-corpus job]
    Py --> Rec
    Rec -->|fresh corpus| Cmp{Byte comparison}
    Corpus --> Cmp
    Cmp -->|difference: fail and upload| Gate[CI gate]
    Corpus -->|cases and inputs checked by digest| Test[TestCorpus]
    Go --> Test
    Test -->|result mismatch fails| Gate
```

| Threat | Control | Verification |
| --- | --- | --- |
| A hand edit of the corpus makes a wrong Go result pass | The `parity-corpus` job records the corpus again and compares each file byte for byte | `test_parity_corpus_check_runs_in_the_gate_and_uploads_a_fresh_corpus` and the job |
| An input file changes under a case | The loader verifies each input against its SHA-256 digest | `TestLoadRejectsAnInvalidCorpus` |
| An ambiguous corpus file | The loader rejects unknown fields, data after the value, and an unknown schema | `TestLoadRejectsAnInvalidCorpus` |
| Free text becomes parity data | The recorder drops each diagnostic `message` | The `tests/test_issue_1778_parity_corpus.py` tests |
| A Go runner with no case passes | `TestCorpus` fails each runner without a case | `TestCorpus` |
| A recorded input holds a credential | Gitleaks scans the corpus in the hygiene lane | The hygiene lane |

## Supporting artifacts

- `tools/parity_corpus.py` and `implementations/python/tests/test_issue_1778_parity_corpus.py`
- `implementations/go/internal/parity/`
- The `parity-corpus` job in `.github/workflows/canonical-verification.yml`

## References and document review

- Issue #1778

## Incremental delivery inventory

The corpus is incomplete against #1778. That issue owns all pending surfaces;
no incremental slice completes the parent acceptance criteria.

| Surface / input inventory | Recorded today | Required before completing #1778 |
| --- | --- | --- |
| Semantic CLI and SDL fixtures | Parse, validate, normalize, resolve, compile, inspect, conformance and transforms | Bind the complete CLI command/option inventory and defect inputs to recordings |
| Published schemas | Valid/invalid JSON fixtures in matching published-contract directories | Supply cases for published identities without fixtures and enforce full identity coverage |
| Canonical forms | Contract JSON fixtures and numeric/Unicode/surrogate edge texts | Keep coverage aligned with each added compatibility defect |
| Other CLI services | None | Processor, runtime, conformance and remaining CLI command recordings |
| MCP tools | None | Tool inventory, success, refusals, diagnostics and deterministic recordings |
| HTTP API | None | Route/method inventory, bodies, status codes, errors and recovery recordings |
| Prior Python defect cases and limits | Only cases reached by the fixtures above | Map the regression-test inventory, input limits, security/error/recovery cases to explicit corpus cases |

The Go cutover must additionally bind this inventory to CI completeness checks;
the no-skip mode alone proves only coverage of cases that were recorded, not that
every exposed surface or defect was recorded. #1778 remains open until both hold.

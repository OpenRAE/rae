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
| `manifest.json` | The corpus schema, Python source commit and tree, recorder digest, and locked environment digests |
| `inputs/<sha256>` | Each input file once, under the SHA-256 digest of its content |
| `cases/<surface>/<command>/<sha256 of the name>.json` | One recorded invocation: name, surface, command, arguments, input digests, and result |

The `cli` surface runs `raes semantic` commands on the SDL examples and the contract fixtures.
Its result is the exit code and the JSON standard output, without the free-text `message` of each diagnostic.
The `schema` surface validates each contract fixture against its published schema, and its result is the verdict.
The case file names use digests, because repository path policy reserves some fixture path names.

The Go package `internal/parity` loads the corpus and verifies each input against its digest.
Each Go port adds a runner for the commands that it implements.
`TestCorpus` runs each case that has a runner, and it fails a runner that has no case.

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

## Review remediation design

The parity package owns exact JSON comparison. JSON numbers compare by decimal
value, including equivalent fractional and exponent spellings, without conversion
to floating point. Normalization keeps a decimal coefficient and an arbitrary-size
exponent rather than expanding attacker-controlled exponents into huge integers.
Malformed or concatenated JSON results fail before comparison.

`coverage.json`, outside the generated corpus, records implemented runner keys.
Removing a registered runner for an implemented key fails, as does a runner without
cases. `RAES_PARITY_REQUIRE_COMPLETE=1` rejects all uncovered keys at cutover and
requires the inventory to declare full corpus coverage. `corpus_complete` stays
false until issue #1778 is fully delivered, including surfaces with no cases yet.
The inventory starts empty because this PR implements no product surface.
Port issues must add both their runner and its required key in the same change.

The manifest records the last commit changing the Python packages, their Git tree
identity, the recorder SHA-256, Python version, and the SHA-256 of the Python
lockfile. Reproduction checks preserve the recorded source commit when its tree
still matches; unrelated commits must not invalidate unchanged behavior. Source,
recorder or lock changes require a new CI recording. CI fetches history so the
recorded commit can be verified. Provenance is checked before runners execute.
The loader rejects missing provenance, unsafe input names, missing results,
empty or duplicate cases, and malformed input digests.

Coverage inventory must distinguish observed cases from complete surface coverage.
The parent issue remains incomplete until every exposed surface, published contract,
fixture, example and exposed Python regression input has recorded behavior.

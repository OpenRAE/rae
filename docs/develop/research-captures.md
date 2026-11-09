# Research captures on concurrent branches

Feature branches record research evidence under unique, content-addressed paths.
They do not allocate a global release number or edit a central list of revisions.
The formal and specification loaders discover `captures/*/manifest.json` next to
the existing `bundles` directory. Each capture binds its snapshot, analysis, protocol, corpus, and artifact pins.
Paths remain relative to the repository.
The bounded document and replay checks still apply.

The existing numbered manifests remain unchanged. `published-history.json`
freezes their admitted inventory and digests, so discovery cannot silently drop
history. Each new capture also has an independent `capture-records` manifest pin, so
removing a capture directory is detected. Adding a capture never edits the
published-history inventory. It also never edits either
family's narrative `index.md`; describe the new work in its issue or PR instead.

Use the [frozen contributor setup](../../CONTRIBUTING.md#set-up-the-repository) before these commands.
Run them from the repository root.

## Recording a branch capture

First execute the relevant evidence collection and analysis against the branch's
source. Prepare a complete snapshot and its matching analysis with honest scope,
provenance, digest pins and baseline joins. An old observation cannot become
current by changing its source digest. Production and participant observations
retain their recorded limits; CI performs the full independent replay.

Use an admitted manifest as the protocol, corpus and artifact template. Supply
both freshly prepared documents together:

```sh
uv run --project implementations/python --frozen python -m tools.research_capture record formal-semantic-validation \
  --template docs/research/formal-semantic-validation/bundles/retest-v76.json \
  --snapshot docs/research/prepared-formal-snapshot.json \
  --analysis docs/research/prepared-formal-analysis.json

uv run --project implementations/python --frozen python -m tools.research_capture record specification-coverage \
  --template docs/research/specification-coverage/bundles/raes-standardized-specification-coverage-issue-1366-sync-v75.json \
  --snapshot docs/research/prepared-specification-snapshot.json \
  --analysis docs/research/prepared-specification-analysis.json
```

The command prints a new manifest path.
It copies the snapshot without changing observation labels.
It derives the directory from the document pins. If the analysis references the prepared
snapshot path, the recorder replaces that reference with `@snapshot`.
During formal validation, this token resolves to the manifest-pinned snapshot.
Thus the directory name has no self-reference. Other evidence
references remain unchanged and their referenced files must be committed.
Keep the resulting capture directory and its `capture-records` receipt; prepared input copies need not be committed.
For an unchanged historical capture, omit `--snapshot` and `--analysis` to wrap
its existing exact bytes. Repeating the same capture is idempotent. A different capture creates another directory.
Thus parallel branches do not overwrite each other's evidence files.

## Routine verification

A new source edit does not require a new research capture.
Routine CI replays the latest recorded formal and specification cases against current code.
Changed outcomes, invalid artifacts, and broken joins still fail.
The recorded package digests describe the source used for the saved observation.
They are not a prerequisite for replay and do not establish current coverage.
Capture dates select the recorded cases; future and ambiguous dates are rejected.

The finite model job runs the current graphs and fixed negative controls.
It requires the expected positive baseline decision.
It does not republish or independently reproduce a historical capture.
The explicit publication and reproduction commands remain available for a deliberate research claim.
Historical inventories, document pins, and capture retention records remain intact.

Record fresh research when a specific claim needs a new observation.
Do not update an old observation's source digest to describe new code.
Source-bound publication still requires the selected capture to match the live implementation.

## Numbered publication during integration

After integration and validation, use a clean checkout of `dev`:

```sh
uv run --project implementations/python --frozen python -m tools.research_capture publish formal-semantic-validation
```

The command selects the current content-addressed capture and writes a small
`publications/vN.json` receipt. `N` follows the existing numbered history and
previous publication receipts. The receipt pins the capture manifest's path and
SHA-256; the capture identity, observation bytes and baseline links stay unchanged.
Commit that receipt through the integration workflow before publishing the other
family. Repeating publication of a committed receipt returns the existing path.
The command refuses feature branches, detached checkouts, `main`, and dirty
integration checkouts. It does not merge a PR or change any branch itself.

Existing open PRs still using global version filenames must adopt captures when
they next synchronize. This change prevents new capture-allocation collisions;
it does not resolve unrelated feature-code conflicts or historical collisions
already present on other branches.

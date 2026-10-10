# Captured boundary shapes

These are the responses the #1344 audit observed from real producers. Every
observation was made on 2026-10-09 (UTC) except NS-5, which was read on
2026-10-10. Each entry names the producer and how the response was obtained,
with the producer version where the audit recorded one. Unless an entry says
otherwise, probes ran on macOS 27.0.1 arm64. Long values are trimmed where
marked, and signed URL query strings are removed. Divergence IDs refer to the
register in [`index.md`](index.md).

The entries for the store and Ground Control client (ST-1 to ST-4), time and
MCP (TM-1 to TM-3) and runtime snapshots (RS-1 to RS-3) are summaries, not raw
responses. Their probes drove this repository's code at `35122105` in its
project environment (CPython 3.14.4), and each entry summarizes what its probe
observed. The probe scripts are not part of this record.

## GitHub

GH-1. REST `GET repos/OpenRAE/rae/pulls/25`, read with `gh api` on 2026-10-09,
trimmed to three fields:

```json
{"base": {"ref": "dev"}, "body": null, "number": 25}
```

GH-2. Default branch and a merged PR into `dev`, read with `gh api` and
`gh pr view 1413 --json baseRefName,closingIssuesReferences,body` on 2026-10-09,
trimmed to the fields shown. Issue #1361 was closed by `github-actions[bot]`,
not by the merge. `closes_lines` is not a `gh` field: it lists the
`Closes #N` text in `body`, as the jq expression
`[.body | scan("Closes #[0-9]+")]` extracts it:

```json
{"default_branch": "main"}
{"baseRefName": "dev", "closes_lines": ["Closes #1361"], "closingIssuesReferences": []}
```

GH-3. Release run 36967479436, job `publish-github`, log lines 361-363 (tag `v6.0.1`):

```text
failed to run git: fatal: not a git repository (or any of the parent directories): .git
##[error]Process completed with exit code 1.
```

GH-4. `gh attestation verify` 2.101.0 output for the v6.0.1 wheel, trimmed to the
identity the verifier reads. The list held one entry. The same command on a
bundle that held this attestation twice exited 0 and printed two entries with
this identity:

```json
[{"verificationResult": {"signature": {"certificate": {
  "issuer": "https://token.actions.githubusercontent.com",
  "sourceRepositoryURI": "https://github.com/OpenRAE/rae",
  "buildSignerURI": "https://github.com/OpenRAE/rae/.github/workflows/release-please.yml@refs/heads/main",
  "runInvocationURI": "https://github.com/OpenRAE/rae/actions/runs/36967479436/attempts/1"}}}}]
```

GH-5. A partially re-run workflow run, `GET actions/runs/36342459179` and its
attempt-2 job list, read on 2026-10-09. Jobs carried over from attempt 1 keep
their attempt-1 start time:

```json
{"run_attempt": 2, "created_at": "2026-09-27T18:55:46Z", "run_started_at": "2026-09-27T19:05:09Z"}
[{"name": "canonical / generic-tool-local-inputs", "started_at": "2026-09-27T19:05:14Z"},
 {"name": "canonical / test-shard (0)", "started_at": "2026-09-27T18:55:49Z"},
 {"name": "fast-feedback", "started_at": "2026-09-27T18:55:54Z"}]
```

NS-3. The v6.0.1 release evidence produced by run 36967479436, from its
`release-evidence-3d59d0eb64d3736e337a387f55bc6f1880ccfcfd` artifact (ID
11210897140), downloaded with `gh run download`. The workflow keeps that
artifact for 7 days. It expired at 05:29Z on 2026-10-09, after the download, so
this capture cannot be fetched again. `release-evidence-index.json`, trimmed:

```json
{"release": {"run_attempt": "1", "run_id": "36967479436", "tag": "v6.0.1",
             "source_sha": "3d59d0eb64d3736e337a387f55bc6f1880ccfcfd",
             "workflow_sha": "3d59d0eb64d3736e337a387f55bc6f1880ccfcfd"},
 "subjects": [{"role": "wheel", "sha256": "3e97f42d42564acc1740757157ffd35a8c6373487845e987a314da54388a06c0"},
              {"role": "sdist", "sha256": "8ab156fb1b9c1f0b467c08d98c0695403224ad3c6f2b7835e30b570f8741e67f"}],
 "test_subjects": [{"role": "derived-test-wheel", "derived_from": "raes-6.0.1.tar.gz",
                    "sha256": "3e97f42d42564acc1740757157ffd35a8c6373487845e987a314da54388a06c0"}]}
```

The artifact's `build-inventory.json` lists all three subjects (`wheel`, `sdist`,
`derived-test-wheel`), and the derived test wheel has the wheel's digest. The
index's `release` block is also the observation behind the inventory's
`GITHUB_SHA` and `GITHUB_WORKFLOW_SHA` row.

## libvirt

LV-1 and LV-4. libvirt 12.7.0 `test:///default` through libvirt-python 12.8.0,
captured on 2026-10-09:

```text
defineXML, same name, new UUID: libvirtError code=9 "operation failed: domain 'raes-audit-web' already exists with uuid 19837e5e-7699-51af-8bd1-435e6ce85a5f"
defineXML, same UUID, new name: libvirtError code=9 "operation failed: domain 'raes-audit-web' is already defined with uuid 19837e5e-7699-51af-8bd1-435e6ce85a5f"
destroy() on an inactive domain: libvirtError code=55 "Requested operation is not valid: domain is not running"
```

LV-2 and LV-3. The same libvirt and binding, captured at 09:48Z. The domain and
network XML was rendered at `35122105` by `native_matrix`, `network_xml` and
`domain_xml` in `raes_backend_libvirt.techvault_matrix`. Each object was
defined and started, then read back with `XMLDesc(0)`. The domain's changed
elements, trimmed:

```text
defined:   <memory unit="MiB">128</memory>  <vcpu>2</vcpu>
read back: <memory unit='KiB'>131072</memory>
           <currentMemory unit='KiB'>131072</currentMemory>
           <vcpu placement='static'>2</vcpu>
```

Each network read back with an added `<bridge stp='on' delay='0'/>`. Lookups of
names that were never defined, with the name elided:

```text
lookupByName:        libvirtError code=42 "Domain not found"
networkLookupByName: libvirtError code=43 "Network not found: no network with matching name '<name>'"
```

`test:///default` starts no hypervisor, so a `qemu:///system` readback adds
elements this capture does not show, such as device addresses and aliases.
#1453 proposes the full capture, with the rendered XML, as test data for the
TechVault fakes.

## Guest appliance

GU-1. Serial fact channel of the production-built guest appliance, booted with
128 MiB under `qemu-system-x86_64` (Ubuntu noble `busybox-static` 1.36.1, kernel
`linux-image-6.8.0-1067-aws`). The bytes end in CRLF (`^M`):

```text
RAES-GUEST-FACTS v1^M
challenge 3904beced86cd1db84d3f7137b7a432c^M
architecture x86_64^M
vcpus 1^M
memory_mib 81^M
iface 52:54:00:c4:7e:78 192.0.2.10 1^M
content /etc/raes/marker aabb38db6cd478c6dcbf41b2973d99a8e72cafe9a026df5808d5015452b38a55 644^M
service beacon tcp 9000 1 1^M
init complete^M
```

The kernel log of the same boot:

```text
Memory: 74496K/130552K available (22528K kernel code, 4446K rwdata, 14088K rodata, 5048K init, 4656K bss, 55796K reserved, 0K cma-reserved)
```

GU-2. Account lines from a 128 MiB boot that requested `loner`, `ops` and `dflt`
enabled and `analyst` disabled:

```text
account loner 1000 /home/loner /bin/sh 1 ^M
account analyst 1001 /home/analyst /bin/sh 1 raes^M
account ops 1002 /home/ops /bin/sh 1 raes,wheel^M
account dflt 1003 /home/dflt /bin/sh 1 ^M
```

## Network services

NS-1. macOS `/usr/bin/curl` 8.7.1 with the production argv shape
(`--fail --location --proto =https --max-filesize`) on the locked ATLAS asset
(625790 bytes) with a limit one byte short, captured on 2026-10-09:

```text
--http2   exit=56  curl: (56) Maximum file size exceeded
--http1.1 exit=63  curl: (63) Maximum file size exceeded
exact limit (625790) exit=0, 625790 bytes
```

Ubuntu 24.04 curl 8.5.0 returned 63 for the same transfer on both protocols.

NS-2. Anonymous tag listing on public registries, captured on 2026-10-09:

```text
GET https://ghcr.io/v2/oras-project/oras/tags/list
HTTP/2 401
www-authenticate: Bearer realm="https://ghcr.io/token",service="ghcr.io",scope="repository:oras-project/oras:pull"

GET https://registry-1.docker.io/v2/library/alpine/tags/list
HTTP/2 401
www-authenticate: Bearer realm="https://auth.docker.io/token",service="registry.docker.io",scope="repository:library/alpine:pull"
```

With a token, a ghcr.io blob request returns `HTTP/2 307` with
`location: https://pkg-containers.githubusercontent.com/ghcr1/blobs/sha256:...?<signed query removed>`.

NS-4. Two downloads of the locked NIST CSF export URL returned 107517 and 107518
bytes with different SHA-256 digests. The workbook's `docProps/core.xml`
creation time and one sheet cell differ between them, and neither digest matches
the lock.

NS-5. The Docker Official Image `tomcat:latest` (Tomcat 11.0.26), read
anonymously on 2026-10-10 from `public.ecr.aws/docker/library/tomcat`. `HEAD`
requests to `registry-1.docker.io` returned the same index digest
(`sha256:bb7c0c78078841047e2d475acce833ef337cb0007ca7c7e4c9ff9058d9019801`) and
the same linux/amd64 manifest digest
(`sha256:594377d00cebafa7a413a171ad35bd1756c9be9b26855c8c3ba23313db4e18b9`).
That manifest lists ten layers, and three of them are one 32-byte layer:

```text
layers[4] sha256:4f4fb700ef54461cfa02571ae0db9a0dc1e0cdb5577484a6d75e68dc38e8acc1 size=32
layers[7] sha256:4f4fb700ef54461cfa02571ae0db9a0dc1e0cdb5577484a6d75e68dc38e8acc1 size=32
layers[9] sha256:4f4fb700ef54461cfa02571ae0db9a0dc1e0cdb5577484a6d75e68dc38e8acc1 size=32
```

## Command-line tools

CL-1. The pinned conftest 0.68.0 (OPA 1.15.1), `conftest test input.json --policy <dir> --output json`,
captured on 2026-10-09:

```text
policy that passes:   exit=0, stdout [{"filename": "input.json", "namespace": "main", "successes": 1}]
no rules in main:     exit=0, stdout [{"filename": "input.json", "namespace": "main", "successes": 0}]
rule conflict:        exit=1, stdout empty, stderr
  Error: running test: query rule: check: query rule: evaluating policy: policy-conflict/conflict.rego:6: eval_conflict_error: complete rules must not produce multiple outputs
parse error:          exit=1, stdout empty, stderr
  Error: running test: load: loading policies: load: 1 error occurred during loading: policy-parse-error/broken.rego:9: rego_parse_error: unexpected eof token
conftest verify:      exit=1 on the parse error, exit=0 on the rule conflict
```

CL-2. git 2.54.0 (Apple Git-157), `git diff --name-only --diff-filter=d --cached`
in a scratch repository, next to the `-z` form:

```text
"contracts/schemas/na\303\257ve.json"
contracts/schemas/plain.json
docs/renamed.md
"docs/tab\tname.md"
docs/with space.md

git ls-files -z: contracts/schemas/naïve.json | contracts/schemas/plain.json | docs/renamed.md | docs/tab<TAB>name.md | docs/with space.md
```

## SQLite store and Ground Control client

ST-1. `flock`, observed through a forked child and a separate probe process. The
first two lines come from an OS-level `flock` probe. The last two run the
production `RuntimeOwnerLease.close()` and a variant that always unlocks:

```text
after forked child closed a dup:                  BlockingIOError(errno=35 EAGAIN)
after forked child called LOCK_UN on inherited fd: acquired (parent lock was silently released)
production close() in a forked child, third process: blocked (parent still exclusive)
close() that always unlocks, third process:          ACQUIRED the lock (two owners possible)
```

ST-2. SQLite 3.50.4 under CPython 3.14.4, a commit-time failure in the
production `transaction()`:

```text
deferred foreign key: transaction() raised from commit(): sqlite3.IntegrityError(FOREIGN KEY constraint failed)
  in_transaction after failed commit: True; row persisted after close(): 0
WAL write failure at COMMIT (RLIMIT_FSIZE): sqlite3.OperationalError(disk I/O error) SQLITE_IOERR_WRITE
  in_transaction after failure: False; PRAGMA quick_check: ok
disk full inside the body: sqlite3.OperationalError(database or disk is full) SQLITE_FULL, isinstance(OSError) False
```

ST-3. A production store file under SQLite 3.50.4, corrupted in place, then
admitted:

```text
index root page overwritten: quick_check row "Tree 10 page 10: btreeInitPage() returns error code 11"
  admit_runtime raises ValueError(local control-plane database failed its integrity check)
state table root page overwritten: quick_check raises sqlite3.DatabaseError(database disk image is malformed)
  admit_runtime raises sqlite3.DatabaseError(database disk image is malformed)
file truncated from 40960 to 20480 bytes: same as above
```

ST-4. The production Ground Control client against local test servers:

```text
connection refused:             GroundControlUnavailable (handled)
server closes without response: http.client.RemoteDisconnected (not a GroundControlError)
truncated body:                 http.client.IncompleteRead (not a GroundControlError)
200 with an HTML page:          json.decoder.JSONDecodeError (not a GroundControlError)
200 with non-UTF-8 JSON:        UnicodeDecodeError (not a GroundControlError)
401 JSON:                       GroundControlAuthRequired (handled)
```

## MCP, time and runtime payloads

TM-1. Workflow steps completed 1 ms apart, timestamps formatted the way the RAES
runtime (`datetime.now(UTC).isoformat()`) and the LilRAE workflow engine format
them:

```text
A = 2026-10-08T12:00:01Z   B = 2026-10-08T12:00:01.001000Z
compensation order recorded: ['a', 'b']   (reverse completion order is ['b', 'a'])
control with both fractions present: ['b', 'a']
```

TM-2. `RuntimeFactBindingAdmission` and `bind_action_inputs`:

```text
'2026-07-20T03:02:00Z': admitted; bind accepted, disposition BOUND
'2026-07-20T03:02:00':  admitted; bind raised TypeError: can't compare offset-naive and offset-aware datetimes
'2026-07-20':           admitted; bind raised TypeError: can't compare offset-naive and offset-aware datetimes
```

TM-3. The `raes_mcp` server over stdio, `sdl_validate` called with an object
where the schema expects a string:

```text
isError: True
Error executing tool sdl_validate: 1 validation error for sdl_validateArguments
sdl_content
  Input should be a valid string [type=string_type, input_value={'secret': 'do-not-disclose-42'}, input_type=dict]
```

RS-1, RS-2 and RS-3. One live control plane (stub target), compared across its
producers:

```text
carriers in the /snapshot API but absent from the conformance hermetic payload: realization_envelope, realization_provenance
store serializer closure records: present; /snapshot route closure records: {}
mixed_composition_states and mixed_composition_history: present in the store, {} in the public API
real snapshot with participant behavior history, semantic conformance:
  participant behavior history requires a participant.behavior snapshot entry with action_contract_addresses and observation_boundary_addresses
  participant behavior event references unknown action_contract_address 'participant.action-contract.scan'
```

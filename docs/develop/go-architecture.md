# Current Go architecture

This is the current system view for the Go port.
[The model](../../implementations/architecture.json) owns package placement, dependencies, build contexts and intended interfaces.
[ADR-122](../decisions/adrs/adr-122-go-architecture-model.md) owns the checking rules.
The generated view lists the code that exists now.
An empty layer is planned, not implemented.
Python remains the behavioral reference for components not yet ported.

## Components and consumer boundary

Environment packs, LilRAE and Coldlight use the Go module.
[Issue #1825](https://github.com/OpenRAE/rae/issues/1825) owns their public package design and compatibility policy.
No product package is downstream-importable today.
The `public` flag is for layers.
It does not bypass Go's `internal` rule.
The tooling module is a development dependency, not the consumer product API.

```mermaid
flowchart TB
    Consumers[Environment packs / LilRAE / Coldlight]
    subgraph Host[Embedding host boundary - planned]
        Providers[Store / lease / clock providers]
        API[Consumer API - issue 1825 - planned]
    end
    subgraph RAES[RAES Go module]
        Transport[CLI / MCP / HTTP adapters - planned]
        App[Shared application services - planned]
        SDL[SDL admission - planned]
        Contracts[Published contract admission - implemented]
        Processor[Compilation / planning / trial compilation - planned]
        Runtime[Shared runtime control plane - planned]
        Backend[Backend interfaces - planned]
        Base[Shared base primitives - implemented]
    end
    Consumers --> API
    API --> App
    Transport --> App
    App --> SDL
    App --> Processor
    App --> Runtime
    SDL --> Contracts
    Processor --> SDL
    Runtime --> Backend
    Runtime --> Providers
    Contracts --> Base
    Providers --> Temporal[Temporal execution composition - planned ADR-113]
```

Published contract admission is implemented.
It compiles the packaged schemas offline and checks family rules against explicit owner records.
Caller payloads cannot create trusted context, and validation performs no network retrieval.
The [contract design](../decisions/issue-1780-contract-validation-design.md) records its interfaces and failure controls.

Consumers need bounded SDL reads.
They also need checks, edits, errors, locks and digests.
They also include normalized contract round trips, artifact admission, compilation, planning and runtime result admission.
Diagnostics preserve code, pointer, source range, stage and severity.
Typed handles and caller validators cannot be replaced with JSON-only shims.
RAES owns semantic admission, defaults, schemas, vocabulary and address grammar.
Consumer adapters must not call Python.
They must not copy core checks.

Coldlight embeds the shared runtime selected by ADR-104 and ADR-113.
Its planned API includes actor-bound submissions, idempotent receipts, snapshots, participant transitions and audit.
It also includes store, lease and clock interfaces and Temporal execution adapters.
ADR-104's P0/P1/P2 profiles describe reference capabilities, not proof of Go delivery.
P3 coordinated multi-process, multi-tenant service remains a nonclaim.

## Data flows and protection boundaries

```mermaid
flowchart LR
    Documents[Untrusted documents and imports]
    Requests[Untrusted requests and identities]
    subgraph Host[Host authority boundary - planned]
        Auth[Authentication and route authority]
        Secrets[Native credentials and resources]
    end
    subgraph Core[RAES admission and policy boundary]
        Ingress[Bounded ingress - implemented primitive]
        Admission[Contract admission implemented / SDL admission planned]
        Policy[Actor / scope / target policy - planned]
        Plan[Compilation and planning - planned]
        Runtime[Shared operation runtime - planned]
    end
    Documents -->|bounded supplied bytes| Ingress
    Ingress -->|parsed values| Admission
    Requests -->|credentials and operation request| Auth
    Auth -->|authenticated principal| Policy
    Admission -->|validated scenario values| Plan
    Plan -->|admitted execution plan| Runtime
    Policy -->|actor-bound operation| Runtime
    Runtime -->|atomic state and receipts| Store[(Authoritative provider store - planned)]
    Runtime -->|admitted effects| Backend[Injected backend - planned]
    Secrets -->|host-owned handles| Backend
    Backend -->|observed result| Runtime
    Runtime -->|admitted results and audit| Evidence[(Evidence and audit - planned)]
    Runtime -->|value-free events| Logs[(Operational logs - planned)]
```

| Asset / threat | Boundary and control | Evidence / verification |
| --- | --- | --- |
| Source containment and parser exhaustion | Bounded supplied sources; strict ingress before semantic admission | Base ingress tests; published contracts; #1782/#1785 remain planned |
| Cross-actor operations | Transport authenticates; core binds actor, scope, target and idempotency | ADR-104; future runtime conformance tests |
| Confused transport authority | One route authority; invalid bearer credentials cannot fall back to proxy headers | ADR-104; reference security configuration and route tests |
| Uncertain effects and corrupt state | Backend admission, atomic terminal commits, CAS and leases | ADR-104 and ADR-113; Go runtime remains planned |
| Secret disclosure | Logical secret references; native credentials stay in the host | ADR-115 and ADR-116; future adapter redaction tests |
| Audit confusion | Operational logs carry no values and cannot replace evidence or audit | ADR-066 and ADR-116 |
| Architectural drift | Exact typed API, package graph, design commitments and source-bound view checks | ADR-122; arch and archcheck negative tests |

Snapshots prove structural consistency. They do not prove semantic equivalence or service readiness.
Review checks these trust explanations whenever bound evidence changes.

## Ownership and reuse

| Concern | Canonical owner / reuse decision |
| --- | --- |
| Strict bounded JSON | `base/ingress.Parse`; standard encoding/json alone does not enforce the published ingress policy |
| Canonical bytes | `base/canonjson`; JCS and sorted Python JSON are distinct compatibility profiles |
| Digests | `base/digest`; reuse crypto/sha256, not local digest wrappers in each slice |
| Random streams | `base/randstream`; admitted BLAKE3 adapter preserves profiles and seek behavior |
| Addresses and pointers | `base/address` and `base/jsonpointer`; published grammars remain authoritative |
| URI safety | `base/urisafety`; standard URL parsing plus documented Unicode and error-precedence compatibility |
| Clock and timestamp policies | `base/clock` and `base/timestamp`; inject wall-clock reads and reuse the four named grammars |
| Errors and logging | `base/fault` and `base/logrecord`; value-free codes and bounded log records through standard error wrapping and log/slog |
| Graphs | `base/graph`; shared iterative cycle, ordering and component operations |
| Versions and scalar domains | `base/softwareversion` and `base/domain`; closed typed descriptors and bounded comparisons |
| Snapshot values | `base/value`; bounded closed JSON values without foreign callbacks |
| Secret reference identities | `base/secretref`; bounded inert identities, with no secret resolution |
| Contract admission and defaults | `contract/admission` and `contract/validation`; published schemas, full family rules and explicit trusted context |
| Operation and persistence semantics | Planned runtime layer; transports and embedders share the same core |
| Architecture checks | Tooling `arch`; standard Go types and existing model/findings, no product-internal imports |

Compatibility reasons and parity evidence:
[canonical JSON](../decisions/issue-1779-canonical-json-design.md),
[ingress and URI](../decisions/issue-1779-ingress-design.md),
[random streams](../decisions/issue-1779-random-streams-design.md), and
[parity harness](../decisions/issue-1778-parity-corpus-design.md).
The architecture check does not alter those semantics.
The [shared-primitives completion design](../decisions/issue-1779-shared-primitives-completion.md) owns the newly merged base helpers and their compatibility reasons.

## Maintenance

Each port slice changes the model before code.
Do not copy shared helpers.
Use the owner listed above.
Keep source limits in place.
Keep secrets out of logs.
It records typed APIs and updates the owning design's API commitment.
It reviews this overview when source commitments change.
`archcheck -view` prints the generated section for review; it does not overwrite the overview.
`archcheck -api` prints actual interfaces for comparison; it does not approve them.
The existing go-architecture CI job checks documentation and code changes.

<!-- go-view -->

| Layer | Status | Allowed dependencies |
| --- | --- | --- |
| `base` | implemented packages |  |
| `contract` | implemented packages | base |
| `sdl` | planned | contract, base |
| `processor` | planned | sdl, contract, base |
| `backend` | planned | contract, base |
| `runtime` | planned | backend, processor, sdl, contract, base |
| `conformance` | planned | runtime, backend, processor, sdl, contract, base |
| `app` | planned | conformance, runtime, backend, processor, sdl, contract, base |
| `adapter` | planned | app, runtime, contract, base |
| `command` | planned | adapter, base |
| `parity` | implemented packages | base, contract |
| `tooling` | implemented packages |  |

```mermaid
flowchart BT
    L0["base"]
    L1["contract"]
    L1 --> L0
    L2["sdl"]
    L2 --> L1
    L2 --> L0
    L3["processor"]
    L3 --> L2
    L3 --> L1
    L3 --> L0
    L4["backend"]
    L4 --> L1
    L4 --> L0
    L5["runtime"]
    L5 --> L4
    L5 --> L3
    L5 --> L2
    L5 --> L1
    L5 --> L0
    L6["conformance"]
    L6 --> L5
    L6 --> L4
    L6 --> L3
    L6 --> L2
    L6 --> L1
    L6 --> L0
    L7["app"]
    L7 --> L6
    L7 --> L5
    L7 --> L4
    L7 --> L3
    L7 --> L2
    L7 --> L1
    L7 --> L0
    L8["adapter"]
    L8 --> L7
    L8 --> L5
    L8 --> L1
    L8 --> L0
    L9["command"]
    L9 --> L8
    L9 --> L0
    L10["parity"]
    L10 --> L0
    L10 --> L1
    L11["tooling"]
```

| Package owner | Layer | Cross-layer visibility | Consumer importable | Actual dependencies |
| --- | --- | --- | --- | --- |
| `implementations/go/internal/base/address` | base | true | false | implementations/go/internal/base/fault |
| `implementations/go/internal/base/canonjson` | base | true | false | implementations/go/internal/base/fault |
| `implementations/go/internal/base/digest` | base | true | false |  |
| `implementations/go/internal/base/ingress` | base | true | false | implementations/go/internal/base/fault |
| `implementations/go/internal/base/jsonpointer` | base | true | false |  |
| `implementations/go/internal/base/randstream` | base | true | false | implementations/go/internal/base/fault |
| `implementations/go/internal/base/urisafety` | base | true | false | implementations/go/internal/base/fault |
| `implementations/go/internal/parity` | parity | false | false | implementations/go/internal/base/address, implementations/go/internal/base/canonjson, implementations/go/internal/base/digest, implementations/go/internal/base/ingress, implementations/go/internal/base/jsonpointer, implementations/go/internal/base/randstream, implementations/go/internal/base/urisafety, implementations/go/internal/base/clock, implementations/go/internal/base/domain, implementations/go/internal/base/fault, implementations/go/internal/base/graph, implementations/go/internal/base/logrecord, implementations/go/internal/base/secretref, implementations/go/internal/base/softwareversion, implementations/go/internal/base/timestamp, implementations/go/internal/base/value, implementations/go/internal/contract/validation, implementations/go/internal/contract/admission |
| `implementations/tooling/go/arch` | tooling | false | true |  |
| `implementations/tooling/go/cmd/archcheck` | tooling | false | false | implementations/tooling/go/arch |
| `implementations/tooling/go/cmd/raesvet` | tooling | false | false | implementations/tooling/go/lint/getprefix, implementations/tooling/go/lint/gotwant, implementations/tooling/go/lint/wrapverb |
| `implementations/tooling/go/cmd/regressiontest` | tooling | false | false |  |
| `implementations/tooling/go/lint/getprefix` | tooling | false | true |  |
| `implementations/tooling/go/lint/gotwant` | tooling | false | true |  |
| `implementations/tooling/go/lint/wrapverb` | tooling | false | true |  |
| `implementations/go/internal/base/clock` | base | true | false |  |
| `implementations/go/internal/base/fault` | base | true | false |  |
| `implementations/go/internal/base/timestamp` | base | true | false | implementations/go/internal/base/fault |
| `implementations/go/internal/base/softwareversion` | base | true | false | implementations/go/internal/base/canonjson, implementations/go/internal/base/digest, implementations/go/internal/base/fault |
| `implementations/go/internal/base/domain` | base | true | false | implementations/go/internal/base/softwareversion, implementations/go/internal/base/fault |
| `implementations/go/internal/base/value` | base | true | false | implementations/go/internal/base/fault, implementations/go/internal/base/canonjson |
| `implementations/go/internal/base/logrecord` | base | true | false | implementations/go/internal/base/fault |
| `implementations/go/internal/base/graph` | base | true | false | implementations/go/internal/base/fault |
| `implementations/go/internal/base/secretref` | base | true | false | implementations/go/internal/base/fault |
| `implementations/go/internal/contract/corpus` | contract | true | false |  |
| `implementations/go/internal/contract/binding` | contract | true | false |  |
| `implementations/go/internal/contract/validation` | contract | true | false | implementations/go/internal/contract/corpus, implementations/go/internal/contract/binding, implementations/go/internal/base/ingress, implementations/go/internal/base/fault, implementations/go/internal/base/canonjson, implementations/go/internal/base/jsonpointer |
| `implementations/tooling/go/contractgen` | tooling | false | true |  |
| `implementations/tooling/go/cmd/contractgen` | tooling | false | false | implementations/tooling/go/contractgen |
| `implementations/go/internal/contract/admission` | contract | true | false | implementations/go/internal/contract/validation, implementations/go/internal/contract/corpus, implementations/go/internal/base/canonjson, implementations/go/internal/base/digest, implementations/go/internal/base/timestamp, implementations/go/internal/base/graph, implementations/go/internal/base/urisafety, implementations/go/internal/base/address, implementations/go/internal/base/jsonpointer, implementations/go/internal/base/value, implementations/go/internal/base/domain, implementations/go/internal/base/randstream, implementations/go/internal/base/fault, implementations/go/internal/base/ingress |

| Trust-view evidence | SHA-256 |
| --- | --- |
| `contracts/schemas/experiment-core/materialization-archive-record-v1.json` | `fb61b1d9bb70ffedf7fec94325c3751a29ef7db7f6e8bea8fc96c064d101ba90` |
| `docs/decisions/adrs/adr-066-observability-evidence-plane-separation.md` | `938ce2443ce7bd9e5cfa151d9740610ac23fa4338efa48c3cb022c7543bab24a` |
| `docs/decisions/adrs/adr-104-runtime-control-plane-architecture.md` | `b8a790286f92fa21777e4220ec25a321273fe2c6741345732d9aa14bc448e2cf` |
| `docs/decisions/adrs/adr-113-reusable-execution-machinery.md` | `6d904befc0d37d44b07ed083d297c7a0e3ba0d520d79f9ddce1999477c78e91d` |
| `docs/decisions/adrs/adr-115-concrete-backends-owned-outside-raes.md` | `d01cea802cfd206bcdc42ad7f92403fd3f070cfc41ecb5b7b7fdf1e5c5798558` |
| `docs/decisions/adrs/adr-116-shared-exceptions-and-operational-logging.md` | `a4e20904762d23ff25162b910ab91032fdaac84b38ef727401c7fe501dde6ffa` |
| `docs/decisions/adrs/adr-122-go-architecture-model.md` | `e4cf1ddd7deed20c8b1890842b72a3f7b0f0ac14fa6659121f02e92ab9658954` |
| `docs/decisions/issue-1775-go-architecture-model-design.md` | `d12f71c98e4bcad11f42db41338d2d93e9d9ed21731e5e4a1b9ed6fbbba1d2c8` |
| `docs/decisions/issue-1778-parity-corpus-design.md` | `c3197d51b64c8b2684096ad8d4ed4df223457b2e811a16e68bf31e9babc15830` |
| `docs/decisions/issue-1779-canonical-json-design.md` | `c68392c70e55eabd39a1d1b287c082fc98b40aea2a50a90a43384f34aea752a3` |
| `docs/decisions/issue-1779-ingress-design.md` | `21fe1ede3a371941bd13605037cf6e378a6f442d9622dbc9fa716e952cbad281` |
| `docs/decisions/issue-1779-random-streams-design.md` | `dae79083acb2909a63a43849e9aeb0ddf4594d3e7d54d118b2a1dd54f68cdb8b` |
| `docs/decisions/issue-1779-shared-primitives-completion.md` | `6db76f93cc860d13e966bd591fc4d4c4fc3d2c27789aafe1c1bd30dcc57d657e` |
| `docs/decisions/issue-1780-contract-validation-design.md` | `1536d572e8ce033672e5388bffb7fc4769ee6365c46024bd2fc6f7b181a72b9f` |
| `docs/decisions/issue-1859-go-architecture-contract-design.md` | `ed0f2251cdbfb59c3a7806b71f58df17278b4873d73afad42c41cfe003d18fcb` |
<!-- go-component base 63cb070395441a6c5ab12ddeed860f76bfd01b7a2b2fb3033da7bf94f9351b5c -->
<!-- go-component contract e497c6eb9972d5dc649183b892c7448a0d143323c4db77a96600b24de260a536 -->
<!-- go-component sdl f2ef48d420a282d49876ba16ac0ca8485a5a42888a57d893f67220779f97f636 -->
<!-- go-component processor c956df1e8eaba7191f304226c67cde64b748f4aade9d4463f742f0b93465106c -->
<!-- go-component backend 23e74144190b5a5ff1c3dbcbc3e763da4d180dbde83a16d9c5665a6fedb70bb2 -->
<!-- go-component runtime 7dcc7a3112b858559b3a785cc568c86c0bcc5abb7f8ab9d57070f89878b76ccf -->
<!-- go-component conformance f9a3aa506277b1262080ff48e8c185236a70be59d3ec15e5134b3b6815a300d9 -->
<!-- go-component app 134d035b61898721768d58785b7f7d32b9cbf60d67d3e2a26709980774fba2f4 -->
<!-- go-component adapter df9a0feabe8cb178a947daa565bd6d4e3d5c0c3ad61391d10f4a5aa681c3b207 -->
<!-- go-component command 63da404ddc4609c5d45dfc520a1db6a8ac072236100c0c60636e8b657a5d2f38 -->
<!-- go-component parity 31885fcdddf5de5886fa3b80a3c27f5a5248a2cf1582f287dee0a50f7db31cf7 -->
<!-- go-component tooling ad5d823364f919bb722e00bd992740e972322ab4fc5a0f2d282d5018ff5c9b36 -->

<!-- /go-view -->

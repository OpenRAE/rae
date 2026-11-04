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
| `docs/decisions/issue-1780-contract-validation-design.md` | `4416f80437e2b60e95aa2008c111e43bd141461001d9d73b4f286fa908a0edf4` |
| `docs/decisions/issue-1859-go-architecture-contract-design.md` | `ed0f2251cdbfb59c3a7806b71f58df17278b4873d73afad42c41cfe003d18fcb` |
<!-- go-component base c948030cc17959714a44e9009a563549362ca24e52aef05223b4ac747186a5ff -->
<!-- go-component contract 35807dce0f949f7aeef1aabee23a11554748af4cf2a3894b6de956d505b93172 -->
<!-- go-component sdl 4a32b6fb2513b32c456aa410ea035aac02ae0c0410e057b2a898d5973dc571d1 -->
<!-- go-component processor 3171a23330e20bf17c11f71ff86f6822e24d5eaef2e44369603100977519f4f1 -->
<!-- go-component backend 8c201362640554fe6ef3412a983d9311020686804d7b6963426df080706e3872 -->
<!-- go-component runtime b3a4b53368cb1e1122eedec1d7338201c01bcbc6fc8fc1ef4a3f2f226a59b138 -->
<!-- go-component conformance b8803fc5c5d52641f4d492003f04a626d591715331634cae691cc1edffff9202 -->
<!-- go-component app 7329418a7e5f5bc3a6d9169536bfc2751e2c272bd9bd4a3fdd625133dc63dec2 -->
<!-- go-component adapter 5bdfdca31c96a6270162f85322a728bdd04e44912a2e0423e9e0d532535a3ccc -->
<!-- go-component command 8124eaeb6e71a39f28df7d173b258cb38c1ad68b454a154b97e67895817501ec -->
<!-- go-component parity fe6bc1cb2e85e04c6417de6efb0ee2fd63fb9219e7a3a630dc90edcbb9d2d2a6 -->
<!-- go-component tooling 3d3ed5d2a20ce1eb63442650a115e34531ed3d6d396e0949f07303aedad938ee -->

<!-- /go-view -->

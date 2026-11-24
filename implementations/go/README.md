# Go implementation

The Go port develops on `go-cutover`.
Python remains the released implementation until the hard cutover.
The published contracts remain the authority.

## Public packages

Consumers import `base/fault`, `base/ingress`, `base/canonjson`, `base/digest`, `base/address`, `base/clock`, `contract/binding`, `contract/validation` and `contract/admission`.
All other packages are below `internal`.
The [consumer API reference](../../docs/decisions/issue-1825-public-go-api.md) names the planned packages and their owners.
The [external consumer fixture](testdata/consumer) imports these packages at a pinned module version.
It uses `GOWORK=off` and read-only module resolution.
Module files do not contain `replace` directives.

## Contract boundary

`internal/contract/corpus.Open` returns the read-only corpus built into the binary.
It needs no source checkout or network access.
It includes the third-party notice and all corpus families.

`contract/validation.New` compiles the published schemas offline.
Keep the returned validator for reuse.
It is safe to share if its registered rules are safe to share.
Its methods return value-free errors through the existing fault classes.

Use `CheckSchema` for a schema verdict.
Use `DecodeSchema` to obtain a checked transport value.
This method also checks the JSON round trip.
Neither method claims semantic validity.
The caller supplies its byte and depth limits through `ingress.Limits`.

Use `contract/admission.New` and its `Validate` method for complete semantic admission.
This owner binds all published invariant rules and checks supplemental model rules.
Its `CheckPortable` method preserves the portable entry point's local validation claim.
It does not establish full contextual conformance.
Trusted context uses explicit family interfaces.
The [admission guide](contract/admission/README.md) describes those interfaces and their ownership.
The constructor requires all 180 published invariant IDs and validates its consumed catalogs.

The lower-level `validation.Validate` interface also supports explicit owner-supplied rules.
Supply those rules to `validation.New` or `WithRules`.
Each rule has a `Key` with the published contract and invariant IDs.
The validator rejects unknown keys, duplicate registrations and missing callbacks.
It invokes rules only where their schema branches apply.
A missing applicable rule prevents admission.
A rule that needs context must declare `RequiresContext`.
The trusted caller supplies that context directly.
The validator never resolves authority from payload claims.

`validation.Defaulted` returns a fresh schema-checked view with published defaults.
Digest owners use it and apply their documented serializer omissions.
It does not change schema acceptance or grant admission.
`DefaultedObjectFragment` applies the same default rules to a reachable object definition.
Fragment and instance checks do not grant contextual admission.
`CheckReferenceBinding` checks catalog schema pointers, instance paths and key fields against the compiled bundle.

An admitted `Value` keeps its bytes private.
`JSON` returns a copy.
`Transport` returns a fresh generated value.
Changing either copy does not change the admitted value.
The zero value is not admitted.

The generated types in `contract/binding` are transport data.
`Field[T]` distinguishes absent members, explicit null and supplied values.
Numbers retain their exact JSON form.
Union fields retain raw JSON until the schema checks their branches.
Open objects retain their extra members.
The types do not replace schema or semantic checks.

## Generation and checks

Build `implementations/tooling/go/cmd/contractgen` from the tooling module.
Run the built command from the repository root.
The command reads the publication inventory, rule specification and corpus.
It writes the generated bindings and embedded archive pieces.
The `-check` flag compares the complete output, including extra or missing files.

Do not edit generated files.
Do not edit a published schema to make generation pass.
The [design](../../docs/decisions/issue-1780-contract-validation-design.md)
records the boundary and its controls.
The [rule specification](../../specs/conformance/contract-invariant-rules.md)
states the invariant inventory.
The admission owner supplies the domain rules.

CI checks generation, built packaging, schema parity, portable admission parity and the existing Go quality gates.
The portable admission inventory covers 363 recorded decisions.
The complete CLI command remains a separate port.
Local tests select the affected packages and cases.
Full test, mutation and fuzz suites run only in CI.

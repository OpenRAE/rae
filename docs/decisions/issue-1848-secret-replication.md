# Secret replication policy

Issue #1848 extends the secret model in `raes.runtime_secret_service`.
The public field is `RuntimeServiceSecret.replication`.
Its type is `RuntimeSecretReplication`.
Package and execution boundaries stay the same.

## Contract and design

The policy identity is `provider: gcp-secret-manager` plus an exact `mode`.
The modes are `automatic` and `user-managed`.
Other provider names and mode spellings are invalid.
This keeps GCP meaning without equating it to another provider's policy.

An absent or null policy makes no replication claim.
It never means automatic.
Automatic mode has no replica list.
User-managed mode needs a nonempty list with distinct locations.
An automatic policy can name a native KMS key.
Each managed replica can name its own key.
An automatic key must use `global`.
A replica key must use that replica's location.
Names carry no key material.

The old `location`, `replica_locations`, and `encryption_key_ref` fields must
be empty when a typed policy is present.
This leaves one source of meaning.
A supplied resource scope must use provider `gcp`.

Mode, location and key names can use whole-field variables.
Checks run again after binding.
Closed fields, provider identity and list bounds are checked on input.
The schema records a callable rule for checks that compare field values.
These include location uniqueness and key/location agreement.

The model registry and existing pipeline retain the nested value.
This covers imports, compilation, plans and stored snapshots.
Native names are inert; imports do not rewrite them as SDL references.
The exact runtime-platform application concern still owns backend admission.
It refuses unsupported intent before effects.
Result checks detect a missing or changed policy.
No backend gains cloud support through this change.

## Data flow and security

```mermaid
flowchart LR
    A[Authored SDL and local imports] --> V[Parse and validate]
    V --> S[Bind variables and revalidate]
    S --> C[Compile and transport plan]
    C --> G[Backend support checks]
    G --> B[External backend]
    B --> R[Result checks]
    R --> D[Snapshots and materialized SDL]
```

The parser and runtime checks remain trust boundaries.
Closed models reject unknown policies and conflicting fields.
Exact result checks prevent lost replicas or keys.
Native key names are inert strings.
RAES does not discover credentials, fetch keys, call a cloud API or use an SDK.
The backend owns live provider checks and immutable-policy handling.
A valid policy gives no right to replace an existing secret.

## Verification

The two issue test modules cover policy checks, variable binding, imports,
plan transport, disk snapshots, materialized SDL, backend refusal and results.
Five source mutations each disable one guard.
The focused tests catch all five: automatic replicas, managed replicas and keys,
key location, legacy conflicts and scope provider.
Schema parity and publication checks cover the five affected schemas.
The runtime field ledger includes both new model types and all seven new fields.

## Reference

[GCP Secret Manager REST v1](https://docs.cloud.google.com/secret-manager/docs/reference/rest/v1/projects.secrets#Replication),
read 2026-11-02, defines the modes, replica list, key locations and immutable policy.
Offline tests check the declared contract.
They do not prove live provider support.

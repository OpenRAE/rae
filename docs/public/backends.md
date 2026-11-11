# Check a backend boundary

Check the packaged fixtures before you integrate a live target.
RAES owns portable SDL, processing, runtime admission, contracts, and conformance.
The backend owner manages native resources, credentials, allocation, and teardown.

## Before you start

Use Python 3.14 and an installed RAES 11.0.2 package.
Run `python -m pip install raes==11.0.2` inside your virtual environment if needed.
Installation contacts your configured package source and writes that environment.
The fixture check below needs no backend identity or native resource permissions.
It reads the packaged corpus and does not deploy infrastructure.

## Run the portable fixture check

Run the provisioning-only profile:

```console
raes conformance backend --profile provisioning-only --format text
```

The report starts with these results:

```text
backend conformance: passed
requested: provisioning-only; achieved: provisioning-only
native conformance: false
checks: {'passed': 38, 'failed': 0, 'unsupported': 0}
```

Exit `0` means that the selected finite fixture cases passed.
Keep the full report, profile digest, case identities, producer version, and limitations.
It checks published contract examples, including expected refusals.
It does not check your own manifest.
It does not certify native execution.
The Python equivalent is `run_fixture_suite(profile=...)` from `raes_conformance.conformance`.

If the report fails, inspect its diagnostics before integration.
A missing corpus produces `conformance.fixture-missing` and exit `1`.
Restore the packaged fixtures or reinstall the matching release.
Do not remove failing cases or turn fixture success into a native claim.
No native cleanup is needed for this check.

## Admit your own target

1. Obtain the backend's exact release, manifest, installed components, and native setup instructions.
2. Validate the scenario through the [SDL procedure](sdl/validate-compile-plan.md).
3. Plan with the exact manifest through [backend-specific planning](sdl/validate-compile-plan.md#task-cards).
4. Read every unsupported, degraded, or refused result before authorizing execution.

A valid SDL document can exceed the selected backend's capabilities.
A manifest claim does not prove that the declared code is installed.
Start with the [backend-manifest schemas](https://github.com/OpenRAE/rae/tree/v11.0.2/contracts/schemas/backend-manifest)
and [conformance API reference](api/contracts.rst).
The [runtime contract reference](https://github.com/OpenRAE/rae/blob/v11.0.2/specs/formal/runtime-contracts/README.md)
gives exact portable result and capability rules for that release.
Read its implementation evidence before treating a schema as proof of native support.

`run_target_conformance(target)` exercises the surface of an explicitly supplied runtime target.
It can invoke target effects. Obtain resource permissions and a verified cleanup procedure before calling it.
Use the backend owner's approved disposable environment.
Retain original readback, evidence, failures, and cleanup results in that owner's release gate.
A documentation fixture check supplies none of those facts.

## Select an external owner

[LilRAE](https://github.com/OpenRAE/lilrae) owns its backend distribution and native lifecycle.
Choose a LilRAE release with an explicitly supported RAES pairing.
RAES 7.0.0 was the last release with bundled reference and libvirt backends.
The [concrete-backend migration](https://github.com/OpenRAE/rae/blob/main/docs/migration/concrete-backends.md)
records removed imports and commands. RAES supplies no replacement libvirt deployment command.

OpenRAE/env-packs owns pack authoring and distribution.
Shifter and other adapters retain their own repositories, setup, and evidence boundaries.
No external backend is qualified by the fixture report above.
Native integration remains unverified here.
It needs the exact release pairing and installation.
It also needs authorized commands, native readback, and cleanup evidence.

## Read runtime artifacts after integration

Use these exact references when your backend implements the corresponding contract:

- [SDL run records](https://github.com/OpenRAE/rae/blob/main/docs/explain/reference/materialization-attestations.md): backend-reported realization, retained with the run.
- [Runtime descendant inventory](https://github.com/OpenRAE/rae/blob/main/docs/explain/reference/runtime-descendant-inventory.md): unplanned children and later inventory changes.
- [Operation supervision](https://github.com/OpenRAE/rae/blob/main/docs/explain/reference/backend-operation-supervision.md): progress, cancellation, and uncertain effects.
- [Trial unit](https://github.com/OpenRAE/rae/blob/main/docs/explain/reference/backend-trial-unit.md): one admitted entry's execution and separate cleanup observations.
- [Mixed-backend adoption](https://github.com/OpenRAE/rae/blob/main/docs/migration/mixed-backend-execution.md): installed bridges, time coordination, and independent stage readers.

Reporting does not establish independent observation, successful interruption, or resource reuse.
For mixed use, check the [current support table](https://github.com/OpenRAE/rae/blob/main/docs/explain/reference/revised-control-semantics.md)
before composing services. Controlled test examples do not certify a native backend.

## Finish

You have a fixture report and a bounded route to your target's own qualification.
Use the target's owner for native teardown after effect reconciliation.
Read [portability concepts](concepts.md) for the distinction between authored meaning and realized behavior.

# Cloud resource descriptions

Use [cloud-secret-cross-project.sdl.yaml](cloud-secret-cross-project.sdl.yaml) to inspect cross-project identity and secret access declarations.
A workload in project A uses an identity to read a secret in project B.
The example separates metadata access from version state and includes a denied value read.

## Required support

The RAES file parser and published JSON Schema can check this synthetic input.
Host sizes are omitted, so the parser reports capacity advisories.
The example deploys no cloud service and establishes no access result.
Native execution needs a separate backend that supports the declared resources and access checks.

See the [cloud-resource reference](../../../specs/sdl/cloud-resource-access.md) for field meaning.
See the [example catalogue](../../README.md) for other authoring examples and validation commands.

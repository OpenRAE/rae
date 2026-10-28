# Cloud resource descriptions

[The example](cloud-secret-cross-project.sdl.yaml) has a workload in project A
use an identity to read a secret in project B.
It keeps metadata access and version state separate.
It includes a denied value read.

This file describes part of a system.
It leaves host sizes open, so the parser reports capacity advisories.
Tests parse the file and check it against the published JSON Schema.
It does not deploy a cloud service or prove an access result.

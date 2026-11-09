# Implementations

This reference identifies the implementation and artifact owners in this checkout.
The implementations consume `specs/` and `contracts/`.
They do not define normative meaning.

| Tree | Responsibility | Reader route |
| --- | --- | --- |
| `python/` | Python packages, CLI, processor, runtime, and tests | [Contributor setup](../CONTRIBUTING.md#set-up-the-repository) |
| `tooling/` | Reviewed development inputs and frozen tooling environment | [Tooling reference](tooling/README.md) |
| `formal/participant_crossing/` | Model-check adapter and negative corpus | [Counterexample guide](formal/participant_crossing/README.md) |

OpenRAE/rae owns these portable contracts and runtime admission checks.
Each concrete backend distribution owns its native execution, credentials, rollback, and teardown.
A reference stub is not a production backend.

This checkout has no Go module.
Issue #1803 owns the Go build and instruction migration.
Issue #1804 owns publication at cutover.
Use the current Python setup until that boundary changes.

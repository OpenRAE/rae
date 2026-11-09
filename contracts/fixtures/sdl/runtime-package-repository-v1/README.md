# Runtime package repository profile fixtures

This reference describes the portable APT repository cases from issue #847.
The valid case pins the public signing-key bytes with an exact digest.
The invalid case gives an HTTPS key locator without its mandatory SHA-256 digest.
A locator alone is not an exact trust binding.

The [software reference](../../../../specs/sdl/software-requirements.md)
gives the acquisition and repository rules.
`test_issue_847_runtime_package_repositories.py` checks parsing, compilation, schema shape, and refusals.
These local cases do not fetch a key, install a package, or qualify a package repository.

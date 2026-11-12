# Project governance

This page explains who decides project scope and accepts changes.
Use [CONTRIBUTING.md](CONTRIBUTING.md) for setup and pull request steps.

RAES is a maintainer-led open source project. The maintainer sets project
scope, accepts changes, manages releases, and protects the repository's
normative specifications and contracts.

## Propose a change

Open an issue before changing RAES SDL meaning, published contracts, processor
behavior, backend conformance, or project governance. Describe the user need,
current boundary, examples, compatibility effect, and evidence that can test
the change.

Small docs, test, and defect fixes can start as pull requests against `dev`.
The maintainer may ask for an issue when review reveals a wider design choice.

## Make a decision

The maintainer decides whether a change fits the project and has enough
evidence. Durable architecture choices are recorded as architecture decision
records. Normative meaning remains in the approved specification and contract
surfaces.

The project welcomes review but does not require a second maintainer or
independent approval for every change. This keeps the current single-maintainer
model honest and usable.

## Release a change

Pull requests target `dev`. The maintainer approves promotion to `main`.
Release Please prepares release changes on `main` from Conventional Commit titles. It owns package versions, release notes, and
`CHANGELOG.md`.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the working steps and
[MAINTAINERS.md](MAINTAINERS.md) for current ownership.

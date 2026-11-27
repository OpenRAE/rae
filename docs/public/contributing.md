# Improve RAES

Prepare a checkout, run a targeted check, and submit a pull request through
[the contribution guide](https://github.com/OpenRAE/rae/blob/main/CONTRIBUTING.md).
It links to setup and checks before project governance.

Choose the route that matches your change:

- Report a reproducible defect with the
  [bug template](https://github.com/OpenRAE/rae/issues/new?template=bug_report.md).
- Propose a focused improvement with the
  [feature template](https://github.com/OpenRAE/rae/issues/new?template=feature_request.md).
- Follow [CONTRIBUTING.md](https://github.com/OpenRAE/rae/blob/main/CONTRIBUTING.md)
  for setup, tests, commits, and pull requests.
- Read the repository
  [documentation style guide](https://github.com/OpenRAE/rae/blob/main/docs/explain/reference/documentation-style-guide.md)
  before changing public prose.

Discuss SDL, contract, or authority changes before implementation. A small
field change can affect schemas, examples, processors, backends, and
conformance fixtures.

Pull requests target `dev`. The maintainer approves promotion to `main`.
Do not run full test suites locally or edit generated release entries.
Read the [release history](https://github.com/OpenRAE/rae/blob/main/CHANGELOG.md),
[repository license](https://github.com/OpenRAE/rae/blob/main/LICENSE), and
[component notices](https://github.com/OpenRAE/rae/blob/main/THIRD_PARTY_NOTICES.md)
when you need those records.

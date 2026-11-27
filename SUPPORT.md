# Get support

Use this guide to report a reproducible problem or propose a focused change.
RAES SDL has community support on a best-effort basis.

## Choose a route

- Report bugs and documentation problems through [GitHub issues](https://github.com/OpenRAE/rae/issues/new/choose).
- Propose language or contract changes through the feature request template.
- Follow [CONTRIBUTING.md](CONTRIBUTING.md) to submit a change.
- Report suspected vulnerabilities privately through [SECURITY.md](SECURITY.md).
- Report conduct concerns through [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md#report-a-concern).

## Include a small example

For a bug report, include:

- repository commit or package version
- operating system and Python version
- command or API call
- smallest SDL input that shows the problem
- expected result
- actual result and relevant error output

Remove credentials, personal data, and private scenario content before posting.
Do not attach environment dumps or unredacted logs.

For a language or contract proposal, include:

- the scenario authoring problem
- the current workaround, if any
- affected SDL sections, schemas, contracts, or backend expectations
- examples of inputs that should become valid or invalid

## Know what to expect

The project has [one maintainer](MAINTAINERS.md).
Issues and pull requests are handled as time permits.
Runnable examples help the maintainer assess a report.
There is no commercial support channel for this repository.

OpenRAE/rae owns portable contracts and runtime admission.
A concrete backend distribution owns its credentials, native effects, rollback, and teardown.
Name that distribution and its version when reporting backend behavior.
Do not post its credentials here.

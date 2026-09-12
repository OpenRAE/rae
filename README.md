# Reproducible Agentic Environments System

[![CI](https://github.com/OpenRAE/rae/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/OpenRAE/rae/actions/workflows/ci.yml)
[![Docs](https://github.com/OpenRAE/rae/actions/workflows/docs.yml/badge.svg?branch=main)](https://openrae.github.io/rae/)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/OpenRAE/rae/badge)](https://securityscorecards.dev/viewer/?uri=github.com/OpenRAE/rae)
[![PyPI](https://img.shields.io/pypi/v/raes.svg)](https://pypi.org/project/raes/)
[![Python](https://img.shields.io/pypi/pyversions/raes.svg)](https://pypi.org/project/raes/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/OpenRAE/rae/blob/main/LICENSE)

RAES, the Reproducible Agentic Environments System, helps you describe and
check an agentic environment. RAES SDL is its YAML language for authored
scenarios.

You can use RAES to record nodes, links, participants, objectives, workflows,
variation, and evidence needs without tying the scenario to one deployment
backend.

## Validate your first scenario

You need standard CPython 3.11 through 3.14. Python 3.15 is not admitted until
its post-final dependency and compatibility qualification is complete. OCI
module extraction on Python 3.11 additionally requires Python 3.11.4 or newer.
Earlier patch releases lack the mandatory safe tar extraction filter and fail
closed instead of extracting without it.

```console
python -m venv .venv
source .venv/bin/activate
python -m pip install raes
```

Save this file as `first-scenario.sdl.yaml`:

<!-- quickstart-sdl:start -->
```yaml
name: first-scenario
description: A small network with one Linux host.

nodes:
  lab-network:
    type: Switch
  web:
    type: compute
    os: linux
    resources:
      ram: 2 GiB
      cpu: 1

infrastructure:
  lab-network:
    count: 1
    properties:
      cidr: 10.0.0.0/24
      gateway: 10.0.0.1
  web:
    count: 1
    links:
      - lab-network
```
<!-- quickstart-sdl:end -->

Validate it:

```console
python - <<'PY'
from pathlib import Path
from raes import parse_sdl_file

scenario = parse_sdl_file(Path("first-scenario.sdl.yaml"))
print(f"Validated {scenario.name} with {len(scenario.nodes)} nodes.")
PY
```

The command prints:

```text
Validated first-scenario with 2 nodes.
```

RAES has checked the file shape and current semantic rules. It has not created
infrastructure. Continue with the
[quickstart](https://openrae.github.io/rae/quickstart.html) to learn what
each part means.

## Choose your route

- **Scenario authors:** Start with the
  [SDL guide](https://openrae.github.io/rae/sdl/) and
  [worked examples](https://github.com/OpenRAE/rae/tree/main/examples/scenarios).
- **Python users:** Use the
  [Python guide](https://openrae.github.io/rae/guides/python.html) and
  [API reference](https://openrae.github.io/rae/api/).
- **CLI users:** See the
  [command-line guide](https://openrae.github.io/rae/guides/cli.html).
- **Backend implementers:** Read the
  [backend and conformance guide](https://openrae.github.io/rae/backends.html).
- **Researchers:** Review the
  [research context](https://openrae.github.io/rae/research.html),
  [current limits](https://openrae.github.io/rae/limitations.html), and
  [citation guide](https://openrae.github.io/rae/citation.html).
- **Contributors:** Follow
  [CONTRIBUTING.md](https://github.com/OpenRAE/rae/blob/main/CONTRIBUTING.md)
  and the
  [developer documentation index](https://github.com/OpenRAE/rae/blob/main/docs/README.md).

## Understand what RAES promises

An authored scenario records intent. A processor and backend may turn supported
parts of that intent into runtime resources. Reports and evidence show what was
accepted, changed, observed, or left unsupported.

RAES can support a bounded reproduction attempt. It does not promise
deterministic runtime behavior, equal outcomes, exact replay, scientific
validity, or reproducibility.

The repository does not include a production deployment backend or a managed
environment service. It includes contracts, stubs, examples, conformance
checks, and reference code. Read the
[current limits](https://openrae.github.io/rae/limitations.html) before
choosing it for a study or integration.

## See where RAES fits

Cyber, AI security, AI safety, testing, research, and evaluation are
non-exhaustive application areas. Additional domains can add their own
profiles, assets, examples, vocabularies, backends, and evidence rules.

RAES separates these concerns:

- **Authored scenario:** The meaning written in RAES SDL.
- **Processor:** The code that validates, expands, and compiles that meaning.
- **Backend:** The implementation that accepts a supported runtime request.
- **Runtime:** The resources and participant activity that occur during a run.
- **Evidence:** The records used to state and inspect a bounded result.

The strongest current examples come from cyber ranges and agent evaluation.
The core model is not limited to those areas.

## Work from a repository checkout

Install the locked development environment:

```console
git clone https://github.com/OpenRAE/rae.git
cd rae
uv sync --project implementations/python --all-extras --frozen
uv run --project implementations/python raes --help
```

Run the canonical verification graph:

```console
uv tool run --from 'nox[uv]==2026.4.10' nox -f noxfile.py -s verify
```

Useful repository roots are:

- `docs/public/` for hosted reader documentation;
- `docs/README.md` for developer and working records;
- `specs/` for normative specifications;
- `contracts/` for published schemas and fixtures;
- `examples/` for authored scenarios and reusable patterns;
- `implementations/python/` for the reference implementation.

## Project status

RAES is an academic and engineering project with one maintainer. Contributions
are welcome. The project does not require a second maintainer or independent
reviewer for every change.

Release Please owns package versions, GitHub releases, and `CHANGELOG.md`.
Published schemas carry separate stability labels. See
[GOVERNANCE.md](https://github.com/OpenRAE/rae/blob/main/GOVERNANCE.md) and
[MAINTAINERS.md](https://github.com/OpenRAE/rae/blob/main/MAINTAINERS.md) for
the current decision and maintenance model.

## Cite RAES

```bibtex
@software{raes,
  author  = {Edwards, Brad},
  title   = {RAES: Reproducible Agentic Environments System},
  year    = {2026},
  license = {MIT},
  url     = {https://github.com/OpenRAE/rae}
}
```

RAES is released under the
[MIT License](https://github.com/OpenRAE/rae/blob/main/LICENSE). Third-party
notices are in
[THIRD_PARTY_NOTICES.md](https://github.com/OpenRAE/rae/blob/main/THIRD_PARTY_NOTICES.md).

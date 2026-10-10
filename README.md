# Reproducible Agentic Environments System

[![CI](https://github.com/OpenRAE/rae/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/OpenRAE/rae/actions/workflows/ci.yml)
[![Docs](https://github.com/OpenRAE/rae/actions/workflows/docs.yml/badge.svg?branch=main)](https://openrae.github.io/rae/)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/OpenRAE/rae/badge)](https://securityscorecards.dev/viewer/?uri=github.com/OpenRAE/rae)
[![PyPI](https://img.shields.io/pypi/v/raes.svg)](https://pypi.org/project/raes/)
[![Python](https://img.shields.io/pypi/pyversions/raes.svg)](https://pypi.org/project/raes/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/OpenRAE/rae/blob/main/LICENSE)

RAES, the Reproducible Agentic Environments System, helps you describe an
agentic environment, check it before anything runs, and keep evidence about
what a run realized. RAES SDL is its YAML language for authored scenarios.

A RAES scenario records the nodes, links, participants, objectives, workflows,
variation, and evidence needs of an environment. RAES checks the scenario
against published rules. A backend that supports the features it needs can
then run it. The backend's reports show what was realized and observed.

![RAES validates an authored scenario and compiles a plan. An external backend, such as Shifter, LilRAE, or your own backend, realizes and runs it. Simulator and gym adapters are unreleased. Reports and evidence describe the result.](https://openrae.github.io/rae/_static/raes-ecosystem.svg)

How a scenario reaches a run:

1. Author a scenario in RAES SDL. RAES validates it and compiles a plan.
2. Choose an external backend that supports what the scenario needs. Shifter
   and LilRAE (formerly APTL) are examples. You can also write your own
   backend. Simulator and gym adapters are unreleased.
3. The backend builds the environment, and participants act in it.
4. Reports and evidence describe what was realized and observed.

## What RAES provides

RAES owns the meaning of an authored scenario and the formats around it:

- the RAES SDL language, its specifications, and published schemas;
- published contracts for the data that tools and backends exchange;
- validation and processing that check a scenario and compile plans;
- conformance tests that check whether a backend honors a stated boundary;
- reference tools: the Python package, the `raes` command, examples, and a
  reference emulation backend; and
- evidence structures that record what was requested, realized, and observed.

These parts make scenario intent portable, checkable, and shareable. They also
tie that intent to evidence about what a backend realized.

Cyber, AI security, AI safety, testing, research, and evaluation are
non-exhaustive application areas. Additional domains can add their own
profiles, assets, examples, vocabularies, backends, and evidence rules.

## Validate your first scenario

You need standard CPython 3.11 through 3.14. Install the published package in
a virtual environment:

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

## Run a scenario on a backend

This repository includes contracts, stubs, a reference emulation backend, and
conformance tests. It does not include a production deployment backend or a
managed environment service. External backends realize scenarios outside this
repository:

- [Shifter](https://github.com/Brad-Edwards/shifter) is a multi-user cyber
  range platform.
- [LilRAE](https://github.com/OpenRAE/lilrae), formerly APTL, is a
  single-user backend for local labs, cyber ranges, and other environments.
- Your own backend can declare what it supports in a backend manifest and
  test that claim with the RAES conformance tests. Start with the
  [backend and conformance guide](https://openrae.github.io/rae/backends.html).
- [OpenRAE/adapters](https://github.com/OpenRAE/adapters) holds adapter
  projects for simulators and cyber gyms. None is released. Each adapter's own
  conformance reports and evidence records state what it can run.

Shifter, LilRAE, and the adapters are separate projects with their own
documentation. This repository does not ship or certify them. A backend's own
reports and conformance evidence state what it supports.

## Package and share scenarios

[OpenRAE/env-packs](https://github.com/OpenRAE/env-packs) owns environment
pack structure, schemas, templates, and the tools to author, validate, and
release packs. A pack carries RAES SDL scenarios and other reusable assets.
RAES remains authoritative for the SDL, concept, and reusable-asset
trust-policy meanings a pack relies on. Catalogs make packs easier to find.
They do not add SDL semantics.

To build a pack, follow the env-packs
[quickstart](https://github.com/OpenRAE/env-packs/blob/main/docs/public/quickstart.md).
It scaffolds a first pack and validates it.

## Choose your route

- **New to RAES:** Learn the
  [core concepts](https://openrae.github.io/rae/concepts.html), then complete
  the
  [first-scenario tutorial](https://openrae.github.io/rae/tutorials/first-scenario.html).
- **Scenario authors:** Start with the
  [SDL guide](https://openrae.github.io/rae/sdl/), then
  [validate, compile, and inspect a scenario plan](https://openrae.github.io/rae/sdl/validate-compile-plan.html).
  Browse the
  [worked examples](https://github.com/OpenRAE/rae/tree/main/examples/scenarios).
- **Pack authors:** Follow the env-packs
  [quickstart](https://github.com/OpenRAE/env-packs/blob/main/docs/public/quickstart.md).
- **Python and CLI users:** Use the
  [Python guide](https://openrae.github.io/rae/guides/python.html), the
  [command-line guide](https://openrae.github.io/rae/guides/cli.html), and the
  [API reference](https://openrae.github.io/rae/api/). To serve the runtime
  over HTTP, read
  [serve the runtime control plane](https://openrae.github.io/rae/guides/control-plane.html).
- **Participant control:** Use the
  [participant-control guide](https://openrae.github.io/rae/participant-control.html)
  to govern participant input and output.
- **Backend and adapter implementers:** Read the
  [backend and conformance guide](https://openrae.github.io/rae/backends.html)
  and see [OpenRAE/adapters](https://github.com/OpenRAE/adapters).
- **Shifter and LilRAE users:** Install and run each backend from its own
  documentation: [Shifter](https://github.com/Brad-Edwards/shifter) and
  [LilRAE](https://openrae.github.io/lilrae/).
- **Researchers:** Review the
  [research context](https://openrae.github.io/rae/research.html),
  [current limits](https://openrae.github.io/rae/limitations.html), and
  [citation guide](https://openrae.github.io/rae/citation.html).
- **Contributors:** Follow
  [CONTRIBUTING.md](https://github.com/OpenRAE/rae/blob/main/CONTRIBUTING.md),
  the [governance model](https://github.com/OpenRAE/rae/blob/main/GOVERNANCE.md),
  and the
  [developer documentation index](https://github.com/OpenRAE/rae/blob/main/docs/README.md).
- **Help:** See [get help](https://openrae.github.io/rae/support.html) for
  issues and private security reports.

## Know the limits

An authored scenario records intent. A backend may realize only the parts it
supports. Reports and evidence show what was accepted, changed, observed, or
left unsupported.

RAES can support a bounded reproduction attempt. It does not promise
deterministic runtime behavior, equal outcomes, exact replay, scientific
validity, or reproducibility. Read the
[current limits](https://openrae.github.io/rae/limitations.html) before
choosing RAES for a study or integration.

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

Also record the release or commit, scenario, backend, and run evidence that
you used. The [citation guide](https://openrae.github.io/rae/citation.html)
lists what to include.

RAES is released under the
[MIT License](https://github.com/OpenRAE/rae/blob/main/LICENSE). Third-party
notices are in
[THIRD_PARTY_NOTICES.md](https://github.com/OpenRAE/rae/blob/main/THIRD_PARTY_NOTICES.md).

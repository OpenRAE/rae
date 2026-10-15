# Landing Page Precedent Review

Date: 2026-10-09

Issue: #938. Requirement: none.

Purpose: base the structure of `README.md` and `docs/public/index.md` on how
established open-source, developer-tool, and research-software landing pages
present a problem, their concepts, a first success, integrations, navigation,
and citation. Each page below was read directly on 2026-10-09. The notes record
what each page showed on that date, quoted where the wording matters. On
2026-10-10 each page was read again in full for two additions: the "Concepts"
observation in each finding, and what Stripe's development-environment page and
uv offer after their commands.

## Sources Reviewed

| Page | Kind | Sections read on 2026-10-09 |
| --- | --- | --- |
| [Stripe Documentation](https://docs.stripe.com/) | Developer documentation; the editorial exemplar named in `docs/explain/reference/documentation-style-guide.md` | Opening, task links, product groups |
| [Stripe: set up your development environment (Python)](https://docs.stripe.com/get-started/development-environment?lang=python) | Task page | Headings, first commands and their shown responses, cautions |
| [uv](https://docs.astral.sh/uv/) | Developer tool | Opening, install, first project, speed claim |
| [Pydantic Validation](https://pydantic.dev/docs/validation/latest/get-started/) | Library | Opening, examples, adoption claims |
| [FastAPI](https://fastapi.tiangolo.com/) | Framework | Opening, sections before the first example, productivity claims |
| [Gymnasium](https://gymnasium.farama.org/) | Research software for agent environments | Opening, example, external environments, paper link |
| [Inspect](https://inspect.aisi.org.uk/) | AI evaluation framework | Opening, first run, providers and sandboxes, citation |
| [Snakemake](https://snakemake.readthedocs.io/en/stable/) | Research workflow software | Opening, support channels, citation |
| [CybORG](https://github.com/cage-challenge/CybORG) | Cyber operations research environment | Opening, install, examples, citation |

## Findings

### Stripe

The home page opens with "Explore our guides and examples to integrate
Stripe." It is a router: task links such as "Accept payments online" and "Set
up your development environment" come before products grouped by area
(Payments, Revenue, Risk, Data, and others).

The development-environment page states what the reader will learn, then pairs
each command with the response it prints: "If everything worked, the
command-line displays the following response." The API-key caution sits inside
"Run your first SDK request", next to the code it constrains. The page ends with
"See also" right after that step: "This wraps up the quickstart. See the links
below for a few different ways to process a payment for the product you just
created."

Concepts: on the home page each product has a short purpose line (Billing,
"Subscriptions and recurring payments"), and the request sample links "Learn
more about Payment Intents". The development-environment page defines each tool
in the sentence that introduces it: the Stripe CLI is "a tool that gets you
command line access to your Stripe integration".

Useful: route choice before detail on the home page, next steps after the first
result on the development-environment page, a visible result after every
command, and cautions placed beside the step they limit. Friction: the home
page now opens with agent tooling ("Start here: Integrate with Stripe using
skills and plugins") before the payment tasks.

### uv

The opening line is "An extremely fast Python package and project manager,
written in Rust." The first project runs `uv init example`, `uv add ruff`, and
`uv run ruff check`, with shown output. Integrations are not on the landing
page; they are listed under Guides. The page has no citation guidance. It ends
with "Learn more" after its command sections: "See the first steps or jump
straight to the guides to start using uv."

Concepts: each capability (projects, scripts, tools, Python versions, and the
pip interface) gets one sentence before its commands, often by comparison with
a familiar tool: "uv executes and installs command-line tools provided by
Python packages, similar to pipx."

Useful: one short command sequence per capability, each followed by its
output. Friction: "10-100x faster" links to `BENCHMARKS.md`, but "extremely
fast" has no measurement on the page.

### Pydantic

The page opens with "Pydantic is the most widely used data validation library
for Python." After `pip install pydantic`, it shows a "Validation Successful"
example and a "Validation Error" example, both with their output.

Concepts: "Why use Pydantic?" gives each idea one line and a "Learn more…"
link, such as type hints, JSON Schema, and strict and lax modes. The first
example introduces `BaseModel` by subclassing it.

Useful: a failure shown next to the success explains what validation means.
Rejected: adoption figures without a source on the page ("around 8,000
packages on PyPI use Pydantic", "downloaded over 550M times/month"), a logo
wall used as evidence, and a superlative opening.

### FastAPI

The tagline is "FastAPI framework, high performance, easy to learn, fast to
code, ready for production". Six second-level sections (Sponsors, Opinions, a
documentary, a related tool, Requirements, and Installation) come before the
first runnable example.

Concepts: the opening's "key features" list comes before the example. A "Recap"
after the example states the idea the framework rests on: "you declare once the
types of parameters, body, etc. as function parameters."

Rejected: "Increase the speed to develop features by about 200% to 300%",
which rests on an "estimation based on tests conducted by an internal
development team", and sponsor material before the first example.

### Gymnasium

The heading is "An API standard for reinforcement learning with a diverse
collection of reference environments", followed by "Gymnasium is a maintained
fork of OpenAI's Gym library." The only code is a `LunarLander-v3` loop with
`render_mode="human"`. The page shows no install step and no output; the Box2D
environment page separately asks for `pip install gymnasium[box2d]`.
Third-party environments have their own "External Environments" entry, apart
from the reference environments the project maintains. A "Paper" link points
to arXiv 2407.17032; the page has no BibTeX.

Concepts: the page explains reset, step, observation, reward, and episode
termination only in the example's comments ("step (transition) through the
environment with the action").

Useful: a clear line between maintained reference environments and external
ones. Friction: the example needs an extra and a display that the page does
not mention.

### Inspect

The page opens with "Inspect is a framework for frontier AI evaluations
developed by the UK AI Security Institute and Meridian Labs." The first run is
`pip install inspect-ai`, an exported provider API key, and `inspect eval`.
The result appears only as a log-viewer screenshot. The page names "built-in
support for over 20 model providers" and sandboxes for Docker, Kubernetes,
Modal, Proxmox, and Vagrant "via an extension API". It ends with a "Citation"
section: "For attribution, please cite this work as:" and a BibTeX
`@software` entry.

Concepts: before its examples, "Hello, Inspect" defines the core terms in one
sentence each: "An Inspect evaluation is a Task that brings together three
things": a dataset, a solver, and a scorer.

Useful: execution environments are presented as extensions, separate from the
framework that owns evaluation meaning, and the citation is a copyable block.
Friction: the first success needs a model provider API key and shows no text
output.

### Snakemake

The opening is "The Snakemake workflow management system is a tool to create
reproducible and scalable data analyses." The landing page has no install
command or example; both are links. Support is routed by purpose: questions to
Stack Overflow, discussion to Discord ("Please do not post questions there."),
and bugs and feature requests to the issue tracker. The citation section reads
"When using Snakemake, please cite our "rolling" paper" and gives a DOI, with
no BibTeX.

Concepts: the opening paragraph names them. Workflows are "described via a
human readable, Python based language" and scale to servers, clusters, grids,
and clouds "without the need to modify the workflow definition". A workflow can
describe the software it needs, and a run can become a shareable report.

Useful: support routing by purpose and a durable citation identifier.
Friction: no first success on the landing page, and prose-only citation.

### CybORG

The README opens with "A cyber security research environment for training and
development of security human and autonomous agents." Installation is
`pip install -e .` from a checkout. It describes "a common interface for both
emulated, using cloud based virtual machines, and simulated network
environments", but every example uses the simulated mode, and no example shows
printed output. "Citing this project" gives a BibTeX `@misc` entry.

Concepts: scenarios and agents are not defined. They appear in code
(`DroneSwarmScenarioGenerator`, `DroneRedAgent`) and in one sentence about the
red agent parameter. Each wrapper gets a one-line description.

Useful: a BibTeX entry in the README. Rejected: a checkout-based first install,
naming an execution mode that the examples do not show, and examples without
visible results.

## Patterns RAES Adopts

1. Open with what the reader can do and why it helps, in plain words (Stripe,
   Inspect).
2. Give one short first success on the published package, followed by its exact
   output and the boundary of that result (Stripe, uv, Pydantic).
3. Draw a clear line between what this repository owns and what external
   projects provide (Gymnasium's external environments, Inspect's sandbox
   extensions).
4. Offer reader routes after the first success (uv's closing "Learn more", the
   closing "See also" on Stripe's development-environment page, and the style
   guide's progressive-disclosure row and entry-page step 7). Stripe's home
   page and the style guide's "Early route choice" row put routes first. RAES
   departs from that because its front page now carries the first success
   itself, as the README already did.
5. Route support by purpose (Snakemake sends questions, discussion, and bugs to
   separate channels). The private route for vulnerabilities comes from RAES's
   own `SECURITY.md` and `docs/public/support.md`.
6. End with a copyable BibTeX entry and a link to fuller citation guidance
   (Inspect, CybORG).

## Patterns RAES Rejects

1. Superlatives, unsourced adoption figures, logo walls, and testimonials
   (Pydantic, FastAPI, uv).
2. Sponsor or promotional material before the first example (FastAPI).
3. A first success that needs a checkout, credentials, a display, or an
   undeclared extra (CybORG, Inspect, Gymnasium).
4. A result shown only as a screenshot, or not shown (Inspect, Gymnasium,
   CybORG).
5. Naming an execution mode or backend that the page does not support with
   evidence (CybORG).

## Resulting Structure

`README.md` and `docs/public/index.md` share one order:

1. What RAES is and why a checkable scenario helps, then a repository-native
   diagram of RAES, an external backend, the run, and its evidence, repeated as
   numbered text.
2. What RAES provides: the surfaces this repository owns.
3. Validate your first scenario: the published package, the exact output, and
   what that output does and does not mean.
4. Run a scenario on a backend: Shifter, LilRAE (formerly APTL), your own
   backend, and the unreleased simulator and gym adapters, with the statement
   that none of them ships in this repository.
5. Package and share scenarios: env-packs owns pack structure; RAES owns SDL
   meaning.
6. Choose your route.
7. Know the limits.
8. Cite RAES.

Checkout setup, test commands, repository layout, release mechanics, and
maintainer policy stay in `CONTRIBUTING.md`, `docs/README.md`, `GOVERNANCE.md`,
and the hosted limits page.

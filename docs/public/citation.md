# Cite RAES

Identify the software and artifacts that contributed to your result.
Use this software citation for RAES:

```bibtex
@software{raes,
  author  = {Edwards, Brad},
  title   = {RAES: Reproducible Agentic Environments System},
  year    = {2026},
  license = {MIT},
  url     = {https://github.com/OpenRAE/rae}
}
```

## Identify the exact software

1. Record the installed distribution version from its package metadata.
2. Record the full source commit when you use a checkout or modified build.
3. Link the corresponding release tag or immutable commit.
4. Describe local changes and retain their patch with your study materials.

The BibTeX entry identifies the project. Add your exact version or commit to
your citation record; do not cite a moving branch as the software you used.
Use the [release history](https://github.com/OpenRAE/rae/releases) to locate
your release. A documentation build's version does not identify your installation.

Smith, Katz, Niemeyer, and the FORCE11 Software Citation Working Group's
[Software Citation Principles](https://force11.org/info/software-citation-principles-published-2016/)
(2016, DOI `10.7717/peerj-cs.86`) require specificity about the software version used.
They also distinguish credit, identification, and access.
The project citation alone cannot identify a particular experiment.

## Identify the scenario and execution

Record these details beside the result that depends on them:

| Artifact | Details to retain |
| --- | --- |
| Authored scenario | File or artifact identity, source revision, content digest, parameters, and resolved module dependencies. |
| Instantiated scenario | The concrete input after parameter substitution, its identity, and its relation to the authored scenario. |
| Processor | Distribution, version or commit, configuration, and compilation or planning profiles. |
| Backend and runtime | Owning project, distribution, version or commit, selected configuration, and installed support. State when none was used. |
| Contracts and profiles | Exact identifiers and revisions, schema publication status, and digests where the contract defines them. |
| Run and apparatus | Run identity, execution setup, realized choices, observation rules, and relevant timing assumptions. |
| Evidence and analysis | Capture specification, evidence identities, checksums, losses, redaction, analysis version, and the exact claim supported. |

Use the [experiment contract definitions][experiment] for artifact relationships.
A digest identifies content by a computed value. You still need access to the
content. The digest cannot prove that its claims are true.
Cite an external backend separately when it contributes to the result.
RAES supplies interfaces; it does not certify the cited backend.

For example, a parse-only study can identify the source commit, scenario digest,
parser version, and validation result. It should state that no backend ran.
A deployment study also needs the backend, configuration, observed realization,
and evidence for its reported outcome.

## State access and claim limits

Link evidence only when you have permission to disclose it.
For restricted evidence, give a safe identifier and access conditions.
Explain what the reader cannot check. Keep secrets and private locations out of citations.
Do not describe unavailable fixture content as a collected experiment artifact.

Distinguish a demonstrated result, a hypothesis, an open question, and a
historical finding. State the tested bounds and untested conditions.
One successful tool check does not establish scientific validity or independent reproduction.
The [research routes](research.md) show how to connect claims to bounded evidence.

[experiment]: https://github.com/OpenRAE/rae/blob/e71ddbc29e9e06658ddbe2b2c12edf8ed424f044/specs/formal/experiment-core/README.md

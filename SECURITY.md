# Security policy

## Report a vulnerability

Do not put vulnerability details in public issues, pull requests, or
discussions.

Report a suspected vulnerability through GitHub private vulnerability
reporting: [open a private report](https://github.com/OpenRAE/rae/security/advisories/new).
If you cannot use GitHub, email **security@autarchy.ai**. Put
`RAES SDL security report` in the subject or first line.

Include enough detail to reproduce and assess the issue:

- affected package, command, schema, or document
- affected version, commit, or branch
- reproduction steps
- expected and actual behavior
- impact
- proof of concept or logs, if available

## Check the scope

Security reports are most useful for issues in:

- parser and validator behavior
- SDL module resolution and publication
- contract generation and conformance tooling
- CLI behavior
- MCP server behavior
- runtime control-plane code
- repository automation that handles untrusted input

The repository also holds research and third-party reference material. A fix
for archived third-party material often belongs in the upstream project.

## Know what to expect

RAES has one maintainer and no security response SLA. Reports are reviewed as
time allows. A small example helps the maintainer assess current code,
published contracts, and documented workflows.

Avoid publishing exploit details until the maintainer has had reasonable time
to assess the report and prepare a fix or mitigation.

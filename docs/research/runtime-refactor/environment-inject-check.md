**Environment and inject compilation check**

Source revision: `ae2f3311`. Executed: 2026-09-21.
Interpretation: [working diagnosis](diagnosis.md).

This check parses, instantiates, and compiles three small scenarios and one existing TechVault example. It invokes no backend, reads no credentials, and makes no claim about live MCP behavior or inject realization.

Run from the repository root:

```sh
uv run --project implementations/python --frozen --no-default-groups python - <<'PY'
import json
from pathlib import Path
from raes import parse_sdl, parse_sdl_file
from raes_processor.compiler import compile_scenario_runtime_model

base = '''name: environment-entry-points
nodes:
  service:
    type: compute
    os: linux
    services:
      - {name: mcp-entry, port: 8000, protocol: tcp}
'''
inject = '''injects:
  proceed:
    source: researcher-proceed
events:
  proceed-event:
    injects: [proceed]
'''
timeline = '''scripts:
  timeline:
    start_time: 0
    end_time: 60
    speed: 1
    events: {proceed-event: 10}
stories:
  story:
    scripts: [timeline]
'''
cases = [
    ('entry-points-only', parse_sdl(base)),
    ('entry-points-and-inject', parse_sdl(base + inject)),
    ('entry-points-and-scheduled-inject', parse_sdl(base + inject + timeline)),
    ('techvault-defensive-min', parse_sdl_file(
        Path('examples/scenarios/techvault-defensive-min.sdl.yaml'))),
]
for name, scenario in cases:
    model = compile_scenario_runtime_model(scenario)
    print(json.dumps({
        'case': name,
        'declared_agents': len(scenario.agents),
        'compiled_participants': len(model.participant_behaviors),
        'nodes': len(model.node_deployments),
        'injects': len(model.injects),
        'events': len(model.events),
        'scripts': len(model.scripts),
        'stories': len(model.stories),
        'diagnostics': [d.code for d in model.diagnostics],
    }))
PY
```

Recorded results:

```json
[
  {"case":"entry-points-only","declared_agents":0,"compiled_participants":0,"nodes":1,"injects":0,"events":0,"scripts":0,"stories":0,"diagnostics":[]},
  {"case":"entry-points-and-inject","declared_agents":0,"compiled_participants":0,"nodes":1,"injects":1,"events":1,"scripts":0,"stories":0,"diagnostics":[]},
  {"case":"entry-points-and-scheduled-inject","declared_agents":0,"compiled_participants":0,"nodes":1,"injects":1,"events":1,"scripts":1,"stories":1,"diagnostics":[]},
  {"case":"techvault-defensive-min","declared_agents":0,"compiled_participants":0,"nodes":6,"injects":0,"events":0,"scripts":0,"stories":0,"diagnostics":[]}
]
```

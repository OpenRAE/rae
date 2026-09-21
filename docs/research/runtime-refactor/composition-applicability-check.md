**F17: apparatus selection and crossing applicability**

Source revision: `21c77af8`. Executed: 2026-09-21.
Interpretation: [completed diagnosis](diagnosis.md).

This read-only check constructs an apparatus selection with two bindings whose sink applicability is disjoint. It checks request validation and selection digests. It invokes no provider or backend.

Run from the repository root:

```sh
uv run --project implementations/python --frozen --no-default-groups python - <<'PY'
import copy
import json
from pathlib import Path
from pydantic import ValidationError
from raes_contracts.contracts.participant_control_selection import ParticipantControlSelectionModel
from raes_contracts.contracts.participant_control_composition import (
    ParticipantControlRequestModel, control_digest,
)

path = Path('contracts/fixtures/participant-runtime/participant-control-evaluation-v1/valid/teaching-inject.json')
base = json.loads(path.read_text())['request']
request = copy.deepcopy(base)
second = copy.deepcopy(request['selection']['bindings'][0])
second['instance_id'] = 'other-sink-provider'
for scope in second['applicability']:
    scope['sink_ref'] = 'another-sink'
request['selection']['bindings'].append(second)
request['context']['provider_states'].append({
    'instance_id': second['instance_id'],
    'state': request['context']['provider_states'][0]['state'],
})
selection = ParticipantControlSelectionModel.model_validate(request['selection'])
print('two-sink apparatus selection: accepted')
try:
    ParticipantControlRequestModel.model_validate(request)
    print('whole selection at original sink: accepted')
except ValidationError as exc:
    print('whole selection at original sink:', exc.errors()[0]['msg'])
filtered = ParticipantControlRequestModel.model_validate(base)
print('applicable subset at original sink: accepted')
print('subset preserves required runtime selection digest:',
      control_digest(filtered.selection) == control_digest(selection))
PY
```

Recorded output:

```text
two-sink apparatus selection: accepted
whole selection at original sink: Value error, participant control applicability is unresolved
applicable subset at original sink: accepted
subset preserves required runtime selection digest: False
```

`ParticipantControlRequestModel._admitted_scope` requires each selected binding to match the crossing. `participant_control_orchestration._request_refusal` requires `control_digest(request.selection) == control_digest(binding.selection)`, where `ParticipantControlRuntimeBinding` supplies the fixed admitted selection. Therefore the accepted subset cannot pass that runtime gate when the complete two-sink selection is bound. This is a source-derived conclusion using the executed validation/digest check; it is not a backend execution result.

The reproduction isolates applicability. It does not claim that the added provider's profile obligations are complete or that its absence of slots is desirable; the latter is separately diagnosed under F07. Assigning it slots cannot make its disjoint applicability match the original sink.

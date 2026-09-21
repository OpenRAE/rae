"""Small source-audit counterexamples; no repository tests or external effects."""
import copy
import json
import sys
from types import SimpleNamespace
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit('usage: python reproduce-2026-09-21.py /path/to/rae-at-audited-revision')
ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'implementations/python/packages'))
from raes_contracts.contracts.participant_control_composition import (
    ParticipantControlEvaluationModel, ParticipantControlRequestModel,
    control_digest, derive_control_composition,
)
from raes_contracts.contracts.participant_control_results import (
    ControlMechanismResultModel, ControlEffectiveSupportModel,
)

fixture = json.loads((ROOT / 'contracts/fixtures/participant-runtime/participant-control-evaluation-v1/valid/teaching-inject.json').read_text())

def derive(data):
    request = ParticipantControlRequestModel.model_validate(data['request'])
    bindings = {b.instance_id: b for b in request.selection.bindings}
    context_digest = control_digest(request.context)
    for result in data['results']:
        result['binding_digest'] = control_digest(bindings[result['instance_id']])
        result['context_digest'] = context_digest
    for support in data['support']:
        support['context_digest'] = context_digest
    results = tuple(ControlMechanismResultModel.model_validate(r) for r in data['results'])
    support = tuple(ControlEffectiveSupportModel.model_validate(s) for s in data['support'])
    composition = derive_control_composition(request, results, support,
        incumbent_gate_disposition='permit',
        incumbent_gate_evidence=ParticipantControlEvaluationModel.model_validate(fixture).composition.incumbent_gate_evidence)
    data['composition'] = composition.model_dump(mode='json')
    # Confirm the entire published evaluation contract, not just reducer output.
    ParticipantControlEvaluationModel.model_validate(data)
    return {'disposition': composition.disposition, 'blockers': composition.blockers}

results = {}
for kind in ('deny', 'withhold'):
    data = copy.deepcopy(fixture)
    data['results'][1]['payload']['target'] = {
        'kind': kind,
        'crossing_decision': data['request']['context']['crossing'],
        'subject': data['request']['context']['subject'],
    }
    results['subsequent_' + kind + '_effect_on_parent'] = derive(data)

data = copy.deepcopy(fixture)
for slot in data['request']['selection']['slots']:
    slot['role'] = 'advisory'
for result in data['results']:
    result['status'] = 'failed'
    result['payload'] = None
for support in data['support']:
    support['status'] = 'unsupported'
    support['effective_level'] = 'unsupported'
    support['installation'] = None
results['only_advisory_slots_unsupported_provider'] = derive(data)

data = copy.deepcopy(fixture)
data['request']['selection']['slots'] = []
data['results'] = []
results['required_profile_no_slots'] = derive(data)

data = copy.deepcopy(fixture)
data['support'][0]['effective_level'] = 'bounded'
data['support'][0]['constraints'] = [{
    'kind': 'constraint', 'ref': 'finite-bound', 'revision': 'rev1',
    'digest': 'sha256:' + 'a' * 64,
}]
data['support'][0]['downgrade_authority'] = data['request']['context']['authority']
results['explicitly_authorized_bounded_support'] = derive(data)

# Runtime request omission does not consult the admitted required-profile set.
from raes_contracts.runtime_state import RuntimeSnapshot
from raes_runtime.participant_control_binding import ParticipantControlRuntimeBinding
from raes_runtime.participant_control_orchestration import resolve_participant_control_outcome, _mechanism_results

class AbsentResolver:
    def resolve(self, **coordinates):
        return None
    def validation_context(self, record):
        return None
    def effect_operation(self, request, context):
        return None

class EmptyProvider:
    def resolve(self, request):
        return ()

base = ParticipantControlEvaluationModel.model_validate(fixture)
binding = ParticipantControlRuntimeBinding(selection=base.request.selection,
    providers={'influence': EmptyProvider()}, resolver=AbsentResolver())
cp = SimpleNamespace(_participant_control=binding, _snapshot=RuntimeSnapshot())
crossing = SimpleNamespace(decision=object(), intent=SimpleNamespace(participant_address='participants.student'))
results['required_profile_resolver_none'] = {
    'required_profiles': binding.selection.required_profiles,
    'runtime_outcome': resolve_participant_control_outcome(cp, crossing, sink_kind='teaching-observation'),
}

# Split the dependent rule and fact into separate installed providers.
data = copy.deepcopy(fixture)
fact_binding = data['request']['selection']['bindings'][0]
rule_binding = copy.deepcopy(fact_binding)
rule_binding['instance_id'] = 'rule-provider'
data['request']['selection']['bindings'] = [rule_binding, fact_binding]
data['request']['selection']['slots'][1]['instance_id'] = 'rule-provider'
data['request']['context']['provider_states'].append({
    'instance_id': 'rule-provider',
    'state': data['request']['context']['provider_states'][0]['state'],
})
request = ParticipantControlRequestModel.model_validate(data['request'])
calls = []
class RecordedProvider:
    def __init__(self, identity): self.identity = identity
    def resolve(self, request):
        calls.append(self.identity)
        return ()
binding = ParticipantControlRuntimeBinding(selection=request.selection,
    providers={identity: RecordedProvider(identity) for identity in ('influence', 'rule-provider')},
    resolver=AbsentResolver())
_mechanism_results(SimpleNamespace(), binding, request)
results['cross_provider_dependency_invocation'] = {
    'declared_dependency': 'rule-provider.rule depends on influence.fact',
    'actual_invocation_order': calls,
}

print(json.dumps(results, indent=2))

"""Observation points for the upstream-only mixed-control demonstration.

These test providers implement the published protocols. RAE owns all admission,
execution, settlement and verdicts. Nothing in this module discovers a backend.
"""

from copy import deepcopy

from mixed_conformance_harness import Dispatcher, PortableHarness
from participant_crossing_fixtures import PARTICIPANT
from raes_runtime.control_plane_store import LocalControlPlaneStore


class DemonstrationHarness(PortableHarness):
    def __init__(self, root, environment_digest):
        super().__init__(root, affine_destination=4, dispatcher=Dispatcher())
        self.environment_digest = environment_digest
        self.observed_compositions = []
        self.observed_controls = []

    def composition(self, request):
        configuration = super().composition(request)
        if configuration is not None:
            self.observed_compositions.append((request, configuration, self.composed[-1]))
        return configuration

    def control(self, request):
        configuration = super().control(request)
        if configuration is not None:
            self.observed_controls.append((request, configuration))
        return configuration

    def observations(self):
        compositions = []
        for request, configuration, apparatus in self.observed_compositions:
            snapshot, operations = self._read_composition(request, configuration, apparatus)
            compositions.append(
                {
                    "case": request.case_id,
                    "collection_id": request.collection_id,
                    "participant": configuration.participant_address,
                    "episode": configuration.episode_id,
                    "run_id": apparatus.run_id,
                    "binding": apparatus.declaration.model_dump(mode="json"),
                    "time_models": {
                        ref: model.model_dump(mode="json")
                        for ref, model in configuration.binding.context.time_models.items()
                    },
                    "operations": operations,
                    "composition_state": deepcopy(snapshot.mixed_composition_states.get(apparatus.run_id)),
                    "composition_history": deepcopy(list(snapshot.mixed_composition_history.get(apparatus.run_id, []))),
                    "time_readback": snapshot.time_model_state.model_dump(mode="json"),
                    "provider_readback": {
                        "translated_actions": list(apparatus.roles["bridge"].native_targets),
                        "component_actions": {
                            name: runtime.admission_count for name, runtime in apparatus.runtimes.items()
                        },
                        "starts": apparatus.roles["bridge"].starts,
                        "role_calls": list(apparatus.calls),
                    },
                }
            )
        controls = []
        for request, configuration in self.observed_controls:
            snapshot = configuration.store.load_snapshot_state().snapshot
            controls.append(
                {
                    "case": request.case_id,
                    "collection_id": request.collection_id,
                    "participant": configuration.participant_address,
                    "episode": configuration.episode_id,
                    "operations": operation_observations(configuration.store),
                    "history": deepcopy(list(snapshot.participant_control_history.get(PARTICIPANT, []))),
                }
            )
        return {"compositions": compositions, "controls": controls}

    def _read_composition(self, request, configuration, apparatus):
        if request.case_id != "edge-restart-no-reissue":
            return configuration.store.load_snapshot_state().snapshot, operation_observations(configuration.store)
        # The runner closed its lease. Read through a fresh, scope-checked
        # admission instead of bypassing the local store's ownership boundary.
        store = LocalControlPlaneStore(self.root / (request.restart_of or request.collection_id))
        lease = store.admit_runtime(
            target_scope="target:" + configuration.target.name, run_scope=f"run:{apparatus.run_id}"
        )
        try:
            return store.load_snapshot_state().snapshot, operation_observations(store)
        finally:
            lease.close()
            store.close()


def operation_observations(store):
    """Keep synthetic portable facts, never arbitrary result payloads or exceptions."""

    observations = []
    for record in store.load_records().values():
        invocation = record.invocation
        observations.append(
            {
                "operation_id": record.receipt.operation_id,
                "kind": record.status.context.operation_kind.value,
                "state": record.status.state.value,
                "invocation_id": invocation.request.binding.invocation_id if invocation else None,
                "consumed": invocation.consumed if invocation else None,
                "stages": [item.model_dump(mode="json") for item in invocation.mixed_reports] if invocation else [],
            }
        )
    return observations

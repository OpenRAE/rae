package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/graph"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// CheckPortableNodeInventory compares portable nodes with independently derived
// native facts. It reuses the existing identity, reference, capacity, concern,
// and offer owners. It grants no collection, artifact acquisition, attestation,
// execution, or delivery authority; the caller admits those independent joins.
func CheckPortableNodeInventory(v *Validator, inventory binding.RuntimeSnapshotV1, manifest binding.BackendManifestV2, envelope binding.RealizationEnvelopeV1, originalAddresses []string, compilation MaterializationCompilation) (bool, error) {
	if v == nil || len(originalAddresses) > 16384 {
		return false, invalid()
	}
	snapshot, err := portableInventoryTransport(v, termRuntimeSnapshotV1, inventory)
	if err != nil {
		return false, err
	}
	target, err := portableInventoryTransport(v, termBackendManifestV2, manifest)
	if err != nil {
		return false, err
	}
	offer, err := portableInventoryTransport(v, termRealizationEnvelopeV1, envelope)
	if err != nil {
		return false, err
	}
	if !materializationEnvelopeMatches(at(target, "realization_envelope"), offer) {
		return false, invalid()
	}
	original := map[string]bool{}
	for _, address := range originalAddresses {
		if len(address) > 4096 || original[address] {
			return false, invalid()
		}
		original[address] = true
	}
	compiled, err := portableInventoryCompilation(v, compilation)
	if err != nil {
		return false, err
	}
	return portableInventoryAdmits(v, snapshot, target, offer, original, compiled), nil
}

func portableInventoryAdmits(v *Validator, snapshot, target, offer any, original map[string]bool, compiled *materializationCompiled) bool {
	live := materializationScope(object(at(snapshot, "entries")), termProvisioning)
	available, edges, total, err := materializationCapabilityInventory(live)
	if err != nil || graph.HasCycle(edges) {
		return false
	}
	provisioner := at(target, "capabilities", "provisioner")
	if maximum := at(provisioner, "max_total_nodes"); maximum != nil {
		ceiling, ok := number(maximum)
		if !ok || total.Cmp(ceiling) > 0 {
			return false
		}
	}
	state := materializationInventory{execution: materializationExecution{owner: v, manifest: target, current: compiled}, envelope: offer, entries: live}
	for address, entry := range live {
		if !state.portableInventoryEntry(address, entry, provisioner, available, live, original) {
			return false
		}
	}
	return true
}

func (r *materializationInventory) portableInventoryEntry(address string, entry, provisioner any, available, live map[string]any, original map[string]bool) bool {
	kind := stringAt(entry, "resource_type")
	if kind != termNode && kind != termNetwork {
		return true
	}
	if materializationNodeCapabilities(entry, provisioner) != nil {
		return false
	}
	return original[address] || r.portablePreparedNode(entry, available, live) == nil
}
func portableInventoryTransport(v *Validator, contract string, input any) (map[string]any, error) {
	limits := ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}
	if err := CheckTransport(input, limits); err != nil {
		return nil, err
	}
	raw, err := json.Marshal(input)
	if err != nil || v.CheckPortable(contract, raw, limits) != nil {
		return nil, invalid()
	}
	return v.low.DefaultedObjectFragment(contract, "#", raw, limits)
}
func portableInventoryCompilation(v *Validator, input MaterializationCompilation) (*materializationCompiled, error) {
	limits := ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}
	full, err := ingress.Parse(input.FullDocument, limits, ingress.Object)
	if err != nil || value.Validate(full, value.Runtime()) != nil {
		return nil, invalid()
	}
	document, err := ingress.Parse(input.Document, limits, ingress.Object)
	if err != nil || value.Validate(document, value.Runtime()) != nil {
		return nil, invalid()
	}
	compiled := &materializationCompiled{document: document, full: full}
	if err := v.materializationPhaseMetadata(compiled, input); err != nil {
		return nil, err
	}
	return compiled, nil
}
func (r *materializationInventory) portablePreparedNode(entry any, available, live map[string]any) error {
	if !subset(stringsOf(at(entry, termOrderingDependencies)), keySet(live)) || !subset(stringsOf(at(entry, termRefreshDependencies)), keySet(live)) {
		return invalid()
	}
	payload := at(entry, "payload")
	name := stringAt(payload, termName)
	candidate := at(payload, "spec", termNode)
	supplied := at(r.execution.current.document, termNodes, name)
	normalized := at(r.execution.current.full, termNodes, name)
	if supplied == nil || normalized == nil || !equal(supplied, candidate) {
		return invalid()
	}
	native, err := json.Marshal(normalized)
	if err != nil {
		return invalid()
	}
	if err := r.execution.owner.CheckSDLConstruction(termInstantiatedScenarioV1, "#/$defs/Node", native, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}); err != nil {
		return err
	}
	if err := materializationNodeIdentity(entry, normalized); err != nil {
		return err
	}
	if err := materializationNodeReferences(entry, normalized, available); err != nil {
		return err
	}
	return r.portablePreparedNodeSupport(entry, candidate, name)
}

func (r *materializationInventory) portablePreparedNodeSupport(entry, candidate any, name string) error {
	for _, raw := range r.execution.current.prepared[stringAt(entry, fieldAddress)] {
		requirement, err := materializationJSON(raw)
		if err != nil {
			return err
		}
		if stringAt(requirement, fieldAddress) != stringAt(entry, fieldAddress) {
			return invalid()
		}
		// Explicit verified availability remains with the realization owner, which
		// runs ArtifactSupport against the caller's independently frozen facts.
		if at(requirement, "artifact_requirement") != nil {
			continue
		}
		if err := r.preparedSupport(requirement); err != nil {
			return err
		}
	}
	return materializationOfferIn(candidate, "nodes."+name, r.execution.current.presence[name], at(r.envelope, "expression"))
}

func materializationEnvelopeMatches(pin, envelope any) bool {
	return matchingFields(pin, envelope, termContractID, termSchemaVersion, termDigest) && equal(at(pin, "envelope_id"), at(envelope, "id")) && equal(at(pin, "configuration_digest"), at(envelope, termConfiguration, "configuration_digest"))
}

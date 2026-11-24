package planning

import (
	"encoding/json"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func (selection *preparedSelection) portableNodeViolation() (string, error) {
	inventory, entries, err := selection.selectedInventory()
	if err != nil {
		return "", err
	}
	if !preparedOperatingSystemsSupported(entries, selection.original.manifest) {
		return termBackendPreparationSelectedAnInadmissiblePortableNodeCompletion, nil
	}
	facts, requirements, context, err := selection.portableNodeFacts(entries)
	if err != nil {
		return preparedNodeRefusal(err)
	}
	owner, err := planOwner()
	if err != nil {
		return "", err
	}
	contextFragment, err := admission.AdmitFragment(owner, admission.RealizationValue, context, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	if err != nil {
		return "", err
	}
	findings, err := sdl.ValidateNodeRealizationContext(contextFragment)
	if err != nil {
		return preparedNodeRefusal(err)
	}
	if len(findings) > 0 {
		return termBackendPreparationSelectedAnInadmissiblePortableNodeCompletion, nil
	}
	granted, err := preparedArtifactDeliveriesAdmit(contextFragment, entries)
	if err != nil {
		return preparedNodeRefusal(err)
	}
	if !granted {
		return termBackendPreparationSelectedAnInadmissiblePortableNodeCompletion, nil
	}
	artifactFindings, err := realization.ArtifactSupport(requirements, selection.original.manifest, selection.original.context.ArtifactAvailability)
	if err != nil {
		return "", err
	}
	if len(artifactFindings) > 0 {
		return termBackendPreparationSelectedAnInadmissiblePortableNodeCompletion, nil
	}
	original := []string{}
	for _, operation := range selection.original.operations[termProvisioning] {
		original = append(original, operation.Address)
	}
	envelope := selection.original.context.RealizationEnvelope
	if envelope == nil {
		return termBackendPreparationSelectedAnInadmissiblePortableNodeCompletion, nil
	}
	admitted, err := admission.CheckPortableNodeInventory(owner, inventory, selection.original.manifest, *envelope, original, facts)
	if err != nil {
		return preparedNodeRefusal(err)
	}
	if !admitted {
		return termBackendPreparationSelectedAnInadmissiblePortableNodeCompletion, nil
	}
	return selection.retainPreparedPresence(facts)
}

func preparedArtifactDeliveriesAdmit(context admission.Fragment, entries map[string]snapshotEntry) (bool, error) {
	consumers, err := processor.GeneratedArtifactConsumers(context)
	if err != nil {
		return false, err
	}
	for _, entry := range entries {
		if entry.Domain != termProvisioning || entry.Kind != termGeneratedArtifact {
			continue
		}
		payload, err := preparedPayload(entry.Payload)
		if err != nil {
			return false, err
		}
		name, _ := payload["name"].(string)
		required := preparedEnvironmentDeliveries(consumers[name])
		grant, _ := preparedPointer(payload, []string{"spec", "environment_consumers"})
		if grant == nil {
			grant = []any{}
		}
		if !preparedUnorderedRowsEqual(required, grant) {
			return false, nil
		}
	}
	return true, nil
}

func preparedEnvironmentDeliveries(consumers []processor.ArtifactConsumer) []any {
	rows := []any{}
	for _, consumer := range consumers {
		if consumer.DeliveryMode != "environment" && consumer.DeliveryMode != "env_file" {
			continue
		}
		row := map[string]any{termNode: consumer.Node, "target_address": consumer.TargetAddress, "delivery_mode": consumer.DeliveryMode, "output": consumer.Output}
		if consumer.DeliveryMode == "environment" {
			row["environment_variable"] = consumer.EnvironmentVariable
		} else {
			row["environment_file"] = consumer.EnvironmentFile
		}
		rows = append(rows, row)
	}
	return rows
}

func preparedUnorderedRowsEqual(required []any, grant any) bool {
	provided, ok := grant.([]any)
	if !ok || len(required) != len(provided) {
		return false
	}
	keys := make([][]string, 2)
	for index, rows := range [][]any{required, provided} {
		for _, row := range rows {
			canonical, err := canonjson.JCS(rawProjection(row))
			if err != nil {
				return false
			}
			keys[index] = append(keys[index], string(canonical))
		}
		slices.Sort(keys[index])
	}
	return slices.Equal(keys[0], keys[1])
}

func (selection *preparedSelection) retainPreparedPresence(facts admission.MaterializationCompilation) (string, error) {
	for _, operation := range selection.operations {
		payload, decodeErr := preparedPayload(operation.Payload)
		if decodeErr != nil {
			return "", decodeErr
		}
		name, _ := payload["name"].(string)
		selection.nodePresence[operation.Address] = facts.NodePresence[name]
	}
	return "", nil
}

func preparedNodeRefusal(err error) (string, error) {
	category, classified := fault.CategoryOf(err)
	if classified && category == fault.InvalidInput {
		return termBackendPreparationSelectedAnInadmissiblePortableNodeCompletion, nil
	}
	return "", err
}

func preparedOperatingSystemsSupported(entries map[string]snapshotEntry, manifest binding.BackendManifestV2) bool {
	for _, entry := range entries {
		if entry.Domain != termProvisioning || entry.Kind != termNode {
			continue
		}
		payload, err := preparedPayload(entry.Payload)
		if err != nil || !preparedOperatingSystemSupported(payload, manifest) {
			return false
		}
	}
	return true
}

func preparedOperatingSystemSupported(payload map[string]any, manifest binding.BackendManifestV2) bool {
	choice := make([]string, 3)
	domains := make([][]string, 3)
	for i, key := range []string{"os_family", "os_distribution", "os_version"} {
		value, present := payload[key]
		if !present {
			continue
		}
		text, ok := value.(string)
		if !ok || text == "unknown" || text == "other" {
			return false
		}
		choice[i] = text
		if text != "" {
			domains[i] = []string{text}
		}
	}
	if choice[0] == "" && choice[1] == "" && choice[2] == "" {
		return true
	}
	p := fieldValue(fieldValue(manifest.Capabilities).Provisioner)
	if choice[0] != "" && !slices.Contains(fieldValue(p.SupportedOsFamilies), choice[0]) {
		return false
	}
	if choice[1] == "" && choice[2] == "" {
		return choice[0] != ""
	}
	return jointOperatingSystemOffered(manifest, domains[0], domains[1], domains[2])
}
func (selection *preparedSelection) selectedInventory() (binding.RuntimeSnapshotV1, map[string]snapshotEntry, error) {
	entries := map[string]snapshotEntry{}
	for address, raw := range fieldValue(selection.original.context.Snapshot.Entries) {
		var entry snapshotEntry
		if json.Unmarshal(raw, &entry) != nil {
			return binding.RuntimeSnapshotV1{}, nil, invalidPlan()
		}
		entries[address] = entry
	}
	for _, operation := range selection.operations {
		if operation.Action == termDelete {
			delete(entries, operation.Address)
			continue
		}
		entries[operation.Address] = snapshotEntry{Address: operation.Address, Domain: termProvisioning, Kind: operation.Kind, Payload: operation.Payload, Ordering: operation.Ordering, Refresh: operation.Refresh, Profiles: nonNilPreparedProfiles(operation.Profiles), Status: "planned-state-projection"}
	}
	for address, entry := range entries {
		entry.Ordering = nonNilStrings(entry.Ordering)
		entry.Refresh = nonNilStrings(entry.Refresh)
		entry.Profiles = nonNilPreparedProfiles(entry.Profiles)
		if entry.Status == "" {
			entry.Status = "ready"
		}
		entries[address] = entry
	}
	wire := map[string]any{"schema_version": "runtime-snapshot/v1", "entries": entries}
	if err := value.ValidateProjected(wire, value.Runtime(), planProjectionValue); err != nil {
		return binding.RuntimeSnapshotV1{}, nil, err
	}
	var inventory binding.RuntimeSnapshotV1
	if json.Unmarshal(rawProjection(wire), &inventory) != nil {
		return binding.RuntimeSnapshotV1{}, nil, invalidPlan()
	}
	return inventory, entries, nil
}

type portableFactBuilder struct {
	facts        admission.MaterializationCompilation
	requirements []realization.Requirement
	original     map[string]bool
	resources    map[string]any
	raw, full    portableContext
}

func (selection *preparedSelection) portableNodeFacts(entries map[string]snapshotEntry) (admission.MaterializationCompilation, []realization.Requirement, map[string]any, error) {
	builder := portableFactBuilder{facts: admission.MaterializationCompilation{PreparedNodeRequirements: map[string][][]byte{}, NodePresence: map[string]map[string][]string{}}, original: map[string]bool{}, resources: map[string]any{}, raw: newPortableContext(), full: newPortableContext()}
	for _, operation := range selection.original.operations[termProvisioning] {
		builder.original[operation.Address] = true
	}
	for _, address := range slices.Sorted(maps.Keys(entries)) {
		if err := builder.entry(address, entries[address]); err != nil {
			return builder.facts, nil, nil, err
		}
	}
	context, err := builder.liveResourceContext()
	if err != nil {
		return builder.facts, nil, nil, err
	}
	rawContext := maps.Clone(context)
	rawContext["nodes"] = builder.raw.nodes
	rawContext["infrastructure"] = builder.raw.infrastructure
	builder.facts.Document = rawProjection(rawContext)
	builder.facts.FullDocument = rawProjection(context)
	return builder.facts, builder.requirements, context, nil
}

func (b *portableFactBuilder) liveResourceContext() (map[string]any, error) {
	owner, err := planOwner()
	if err != nil {
		return nil, err
	}
	input := map[string]any{"nodes": b.full.nodes, "infrastructure": b.full.infrastructure, "resources": b.resources}
	fragment, err := admission.AdmitFragment(owner, admission.RealizationValue, input, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	if err != nil {
		return nil, err
	}
	context, err := processor.PreparedResourceContext(fragment)
	if err != nil {
		return nil, err
	}
	native, ok := context.Document().(map[string]any)
	if !ok {
		return nil, invalidPlan()
	}
	return native, nil
}

func (b *portableFactBuilder) entry(address string, entry snapshotEntry) error {
	if entry.Domain != termProvisioning {
		return nil
	}
	payload, err := preparedPayload(entry.Payload)
	if err != nil {
		return err
	}
	if entry.Kind != termNode && entry.Kind != termNetwork {
		b.resources[address] = map[string]any{termResourceType: entry.Kind, termPayload: payload}
		return nil
	}
	name, valid := payload["name"].(string)
	if !valid {
		return invalidPlan()
	}
	spec, valid := payload["spec"].(map[string]any)
	if !valid {
		return invalidPlan()
	}
	node, derived, presence, err := compilePortableNode(spec[termNode], name, address)
	if err != nil {
		return err
	}
	b.raw.nodes[name], b.full.nodes[name] = spec[termNode], node.Document()
	b.raw.infrastructure[name], b.full.infrastructure[name] = spec["infrastructure"], spec["infrastructure"]
	b.facts.NodePresence[name] = presence
	if b.original[address] {
		return nil
	}
	return b.addRequirements(address, derived)
}

func (b *portableFactBuilder) addRequirements(address string, derived []realization.Requirement) error {
	b.requirements = append(b.requirements, derived...)
	for _, requirement := range derived {
		fragment, err := realization.AdmitRequirement(requirement)
		if err != nil {
			return err
		}
		b.facts.PreparedNodeRequirements[address] = append(b.facts.PreparedNodeRequirements[address], rawProjection(fragment.Document()))
	}
	return nil
}

//nolint:ireturn // The native concern owner issues the normalized value handle.
func compilePortableNode(input any, name, address string) (admission.Fragment, []realization.Requirement, map[string][]string, error) {
	owner, err := planOwner()
	if err != nil {
		return nil, nil, nil, err
	}
	fragment, err := admission.AdmitFragment(owner, admission.RealizationValue, input, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	if err != nil {
		return nil, nil, nil, err
	}
	return realization.CompilePreparedNode(fragment, name, address)
}

type portableContext struct {
	nodes, infrastructure map[string]any
}

func newPortableContext() portableContext {
	return portableContext{nodes: map[string]any{}, infrastructure: map[string]any{}}
}

func nonNilPreparedProfiles(input []binding.DomainProfileBindingV1) []binding.DomainProfileBindingV1 {
	if input == nil {
		return []binding.DomainProfileBindingV1{}
	}
	return input
}

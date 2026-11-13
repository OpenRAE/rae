package realization

import (
	"bytes"
	"encoding/json"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/address"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func payloadConcern(payload map[string]any, path []string) (any, bool) {
	var current any = payload
	for _, key := range path {
		record, ok := current.(map[string]any)
		if !ok {
			return nil, false
		}
		var present bool
		current, present = record[key]
		if !present {
			return nil, false
		}
	}
	return current, true
}
func setPayloadConcern(payload map[string]any, path []string, value any) error {
	if len(path) == 0 {
		return invalidRealization()
	}
	current := payload
	for _, key := range path[:len(path)-1] {
		child, ok := current[key].(map[string]any)
		if !ok {
			return invalidRealization()
		}
		current = child
	}
	current[path[len(path)-1]] = value
	return nil
}
func projectedConcern(kind string) bool {
	definition, present := concernDefinitionFor(kind)
	return present && len(definition.authored) > 0 && definition.authored[0] == termRuntime
}
func sanitizeConcern(kind string, value any, observed, recursive bool) (any, error) {
	if kind == termRuntimeMounts {
		if observed {
			if err := validateMountObservation(value); err != nil {
				return nil, err
			}
		}
		return projectMounts(value, true, false)
	}
	if kind == termRuntimeSoftwareComponents {
		return projectTypedRuntimeOptions(kind, value, observed, true, false)
	}
	switch kind {
	case termLinuxCapabilities, termProcessResourceLimits, termPublishedPorts, termForwardingAgents, termServiceListeners:
		recursive = false
	}
	owner, err := realizationOwner()
	if err != nil {
		return nil, err
	}
	fragment, err := admission.AdmitFragment(owner, admission.RealizationValue, value, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	if err != nil {
		return nil, err
	}
	result, err := ProjectConcern(kind, fragment, observed, recursive)
	if err != nil {
		return nil, err
	}
	return result.Document(), nil
}
func validateSoftwareReferences(payload map[string]any) error {
	value, present := payloadConcern(payload, []string{termSpec, termNode, termRuntime})
	if !present {
		return nil
	}
	runtime, ok := value.(map[string]any)
	if !ok {
		return nil
	}
	components, ok := runtime[termSoftwareComponents].([]any)
	if !ok || len(components) == 0 {
		return nil
	}
	subset := map[string]any{}
	for _, key := range []string{termSoftwareComponents, termPackages, termRepositoryState} {
		if item, present := runtime[key]; present {
			subset[key] = item
		}
	}
	raw, err := json.Marshal(subset)
	if err != nil {
		return invalidRealization()
	}
	owner, err := realizationOwner()
	if err != nil {
		return err
	}
	return owner.CheckSDLConstruction("sdl-authoring-input-v1", "#/$defs/RuntimeConfiguration", raw, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
}

func projectPayload(requirements []Requirement, address string, payload map[string]any, observed bool) error {
	if len(requirements) > sdl.DefaultLimits().MaxComposedNodes {
		return invalidRealization()
	}
	if observed {
		if err := validateSoftwareReferences(payload); err != nil {
			return err
		}
	}
	handled := map[string]bool{}
	for _, requirement := range requirements {
		if requirement.Address != address || !projectedConcern(requirement.Kind) {
			continue
		}
		descriptor, _ := nativeConcernDescriptor(requirement.Kind)
		key := strings.Join(descriptor.PayloadPath, "\x00")
		if handled[key] {
			continue
		}
		current, present := payloadConcern(payload, descriptor.PayloadPath)
		if !present {
			continue
		}
		if err := projectPayloadConcern(payload, descriptor, requirement, current, observed); err != nil {
			return err
		}

		handled[key] = true
	}
	return nil
}

func projectPayloadConcern(payload map[string]any, descriptor Descriptor, requirement Requirement, current any, observed bool) error {
	safe, err := sanitizeConcern(requirement.Kind, current, observed, requirement.Constraint != nil)
	if err != nil {
		return err
	}
	if err := setPayloadConcern(payload, descriptor.PayloadPath, safe); err != nil {
		return err
	}
	return nil
}

// Equivalent treats malformed legacy concern values as a recoverable mismatch.
// The native value handles remain mandatory even when their payloads differ.
func Equivalent(requirements []Requirement, address string, before, after admission.Fragment) (bool, error) {
	if admission.CheckFragment(before, admission.RealizationValue) != nil || admission.CheckFragment(after, admission.RealizationValue) != nil {
		return false, invalidRealization()
	}
	left, leftOK := before.Document().(map[string]any)
	right, rightOK := after.Document().(map[string]any)
	if !leftOK || !rightOK {
		return false, nil
	}
	for _, input := range []struct {
		value    map[string]any
		observed bool
	}{{left, false}, {right, true}} {
		if err := projectPayload(requirements, address, input.value, input.observed); err != nil {
			if category, known := fault.CategoryOf(err); known && category == fault.InvalidInput {
				return false, nil
			}
			return false, err
		}
	}
	return payloadEqual(left, right), nil
}

// SanitizeSnapshot projects only the concern paths selected by the compiled
// requirements. The returned snapshot owns its containers and payload bytes.
func SanitizeSnapshot(requirements []Requirement, snapshot binding.RuntimeSnapshotV1) (binding.RuntimeSnapshotV1, error) {
	result, err := snapshotSanitizationCopy(snapshot)
	if err != nil {
		return binding.RuntimeSnapshotV1{}, err
	}
	entries, _ := result.Entries.Value()
	if len(requirements) > sdl.DefaultLimits().MaxComposedNodes {
		return binding.RuntimeSnapshotV1{}, invalidRealization()
	}
	state := snapshotSanitizer{entries: entries, handled: map[string]bool{}, sanitized: map[string]map[string]any{}}
	for _, requirement := range requirements {
		if err := state.concern(requirement); err != nil {
			return binding.RuntimeSnapshotV1{}, err
		}
	}
	if err := state.finish(); err != nil {
		return binding.RuntimeSnapshotV1{}, err
	}
	return result, nil
}

// SanitizePreparedNodeSnapshot uses the existing recursive observation owner for
// every registered runtime concern on independently selected portable addresses.
func SanitizePreparedNodeSnapshot(addresses []string, snapshot binding.RuntimeSnapshotV1) (binding.RuntimeSnapshotV1, error) {
	if err := preparedSanitizationAddresses(addresses); err != nil {
		return binding.RuntimeSnapshotV1{}, err
	}
	if err := admission.CheckPreparedSnapshot(snapshot); err != nil {
		return binding.RuntimeSnapshotV1{}, err
	}
	result, err := snapshotSanitizationCopy(snapshot)
	if err != nil {
		return binding.RuntimeSnapshotV1{}, err
	}
	entries, _ := result.Entries.Value()
	state := snapshotSanitizer{entries: entries, handled: map[string]bool{}, sanitized: map[string]map[string]any{}}
	for _, compiledAddress := range addresses {
		if err := state.preparedNode(compiledAddress); err != nil {
			return binding.RuntimeSnapshotV1{}, err
		}
	}
	if err := state.finish(); err != nil {
		return binding.RuntimeSnapshotV1{}, err
	}
	return result, nil
}

func preparedSanitizationAddresses(addresses []string) error {
	if len(addresses) > 16384 {
		return invalidRealization()
	}
	projected := make([]any, len(addresses))
	seen := map[string]bool{}
	for index, compiledAddress := range addresses {
		if len(compiledAddress) > 4096 || !address.Valid(compiledAddress) || seen[compiledAddress] || !strings.HasPrefix(compiledAddress, "provision.node.") && !strings.HasPrefix(compiledAddress, "provision.network.") {
			return invalidRealization()
		}
		seen[compiledAddress] = true
		projected[index] = compiledAddress
	}
	return value.Validate(projected, value.Runtime())
}

func (s *snapshotSanitizer) preparedNode(compiledAddress string) error {
	for _, definition := range concernDefinitions {
		if !projectedConcern(definition.kind) {
			continue
		}
		if err := s.concernAt(compiledAddress, definition.kind, true); err != nil {
			return err
		}
	}
	return nil
}

func snapshotSanitizationCopy(snapshot binding.RuntimeSnapshotV1) (binding.RuntimeSnapshotV1, error) {
	limits := ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}
	if err := admission.CheckTransport(snapshot, limits); err != nil {
		return binding.RuntimeSnapshotV1{}, err
	}
	raw, err := json.Marshal(snapshot)
	if err != nil {
		return binding.RuntimeSnapshotV1{}, invalidRealization()
	}
	owner, err := realizationOwner()
	if err != nil {
		return binding.RuntimeSnapshotV1{}, err
	}
	if err := owner.CheckPortable("runtime-snapshot-v1", raw, limits); err != nil {
		return binding.RuntimeSnapshotV1{}, err
	}
	var result binding.RuntimeSnapshotV1
	if err := json.Unmarshal(raw, &result); err != nil {
		return binding.RuntimeSnapshotV1{}, invalidRealization()
	}
	return result, nil
}

type snapshotSanitizer struct {
	entries   map[string]json.RawMessage
	handled   map[string]bool
	sanitized map[string]map[string]any
}

func (s *snapshotSanitizer) concern(requirement Requirement) error {
	if !projectedConcern(requirement.Kind) {
		return nil
	}
	return s.concernAt(requirement.Address, requirement.Kind, requirement.Constraint != nil)
}

func (s *snapshotSanitizer) concernAt(compiledAddress, kind string, recursive bool) error {
	descriptor, present := nativeConcernDescriptor(kind)
	if !present {
		return invalidRealization()
	}
	key := compiledAddress + "\x00" + strings.Join(descriptor.PayloadPath, "\x00")
	if s.handled[key] {
		return nil
	}
	entry, present := s.entries[compiledAddress]
	if !present {
		return nil
	}
	document, present := s.sanitized[compiledAddress]
	if !present {
		decoder := json.NewDecoder(bytes.NewReader(entry))
		decoder.UseNumber()
		if decoder.Decode(&document) != nil {
			return invalidRealization()
		}
	}
	payload, ok := document["payload"].(map[string]any)
	if !ok {
		return nil
	}
	current, present := payloadConcern(payload, descriptor.PayloadPath)
	if !present {
		return nil
	}
	safe, err := sanitizeConcern(kind, current, true, recursive)
	if err != nil {
		return err
	}
	if err := setPayloadConcern(payload, descriptor.PayloadPath, safe); err != nil {
		return err
	}
	s.sanitized[compiledAddress] = document
	s.handled[key] = true
	return nil
}
func (s *snapshotSanitizer) finish() error {
	for address, entry := range s.sanitized {
		if err := validateSoftwareReferences(ownedProjection[map[string]any](entry["payload"])); err != nil {
			return err
		}
		encoded, err := json.Marshal(entry)
		if err != nil {
			return invalidRealization()
		}
		s.entries[address] = encoded
	}
	return nil
}

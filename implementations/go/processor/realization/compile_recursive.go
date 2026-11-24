package realization

import (
	"maps"
	"slices"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/internal/base/domain"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/sdlrules"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type concernMetadata struct {
	concern                  *compiledConcern
	metadata                 admission.RealizationNormalizationMetadata
	domain                   admission.Fragment
	apparatus                string
	nodes                    int
	pending, invalid, opened bool
	err                      error
	optional                 map[string]bool
	packages                 map[packageCoordinate][]map[string]any
}

func (c *compiledConcern) lower(requirement *Requirement, apparatus string) (bool, error) {
	requirement.Constraint, requirement.Structure = nil, nil
	requirement.ConstraintBinding = ""
	requirement.RecursivePending = false
	requirement.StructureError = false
	if record, present := c.input.explicitness[c.fieldPath]; present && record.Classification == termConstrained && requirement.ValueDomain == nil && (c.definition.kind == termOsFamily || c.definition.kind == termOsDistribution || c.definition.kind == termOsVersion) {
		return false, nil
	}
	projection, err := ProjectConcern(c.definition.kind, c.value, false, true)
	if err != nil {
		if category, ok := fault.CategoryOf(err); ok && category == fault.InvalidInput {
			requirement.StructureError = true
			return false, nil
		}
		return false, err
	}
	rootDomain := requirement.ValueDomain
	if rootDomain == nil && c.definition.kind == "node-architecture" {
		rootDomain, err = c.input.architectureDomain(c.pointer)
		if err != nil {
			return false, err
		}
	}
	context := concernMetadata{concern: c, domain: rootDomain, apparatus: apparatus, optional: map[string]bool{}, metadata: admission.RealizationNormalizationMetadata{Scopes: []admission.RealizationScope{}, CollectionProfiles: []admission.RealizationCollectionProfile{}, Origins: map[string]string{}, LeafConstraints: map[string]admission.Fragment{}, OptionalFields: []string{}, MemberPresence: map[string]string{}}}
	source, projected := c.value.Document(), projection.Document()
	context.collect(projected, source, "", c.fieldPath, "", 0)
	return context.lowerConstraint(requirement, projection, projected)
}
func (m *concernMetadata) lowerConstraint(requirement *Requirement, projection admission.Fragment, projected any) (bool, error) {
	if m.err != nil {
		return false, m.err
	}
	if m.pending {
		requirement.RecursivePending = true
		return false, nil
	}
	if m.invalid {
		requirement.StructureError = true
		return false, nil
	}
	m.metadata.OptionalFields = slices.Sorted(maps.Keys(m.optional))
	closure := admission.RealizationClosure{}
	switch projected.(type) {
	case map[string]any, []any:
		closure = m.closure("")
	}
	if m.err != nil {
		return false, m.err
	}
	if m.pending {
		requirement.RecursivePending = true
		return false, nil
	}
	result, err := admission.NormalizeRealizationLiteral(projection, "raes/"+m.concern.definition.kind+"/v1", closure, m.metadata, admission.DefaultConstraintLimits())
	if err != nil {
		return false, err
	}
	if result.Status != termConformant {
		requirement.StructureError = true
		return false, nil
	}
	document, err := bindScalarChoices(result.Document)
	if err != nil {
		requirement.StructureError = true
		return false, nil //nolint:nilerr // This relation reports candidate refusal in its result without failing the enclosing operation.
	}
	binding, err := admission.RealizationConstraintBinding(document, projection)
	if err != nil {
		return false, err
	}
	requirement.Constraint = document
	requirement.ConstraintBinding = binding
	return m.opened, nil
}

func (m *concernMetadata) closure(pointer string) admission.RealizationClosure {
	posture := termClosed
	resolved, err := sdl.ResolveRealizationDesignation(m.concern.input.scenario, m.concern.pointer+pointer)
	if err != nil {
		m.err = err
		return admission.RealizationClosure{}
	}
	document := ownedProjection[map[string]any](resolved.Document())
	if document["delegated"] == true {
		switch m.apparatus {
		case "":
			m.pending = true
		case termOpenWorld:
			posture = termOpen
		}
	} else if document["closure"] == termOpenWorld {
		posture = termOpen
	}
	if posture == termOpen {
		m.opened = true
	}
	return admission.RealizationClosure{Posture: posture, Universe: m.concern.definition.kind, Profile: "raes/" + m.concern.definition.kind + "/v1"}
}

func metadataPointer(pointer, key string) string {
	return pointer + jsonpointer.FromTokens([]string{key})
}

func (m *concernMetadata) collect(projected, source any, pointer, path, sourcePointer string, depth int) {
	m.nodes++
	limits := admission.DefaultConstraintLimits()
	if m.invalid || m.pending || m.err != nil {
		return
	}
	if depth > limits.MaxDepth || m.nodes > limits.MaxNodes {
		m.invalid = true
		return
	}
	record, authored := m.concern.input.explicitness[path]
	m.metadata.Origins[pointer] = metadataOrigin(record, authored)
	if !authored && pointer != "" {
		m.optional[pointer] = true
	}
	switch value := projected.(type) {
	case map[string]any:
		m.collectRecord(value, source, pointer, path, sourcePointer, depth)
	case []any:
		m.collectSequence(value, source, pointer, path, sourcePointer, depth)
	default:
		m.leaf(projected, source, pointer, sourcePointer, record, authored)
	}
}
func metadataOrigin(record explicitnessRecord, authored bool) string {
	if !authored {
		return "default"
	}
	if record.Provenance == termProcessorDerived {
		return termProcessor
	}
	return termAuthor
}
func (m *concernMetadata) collectRecord(value map[string]any, source any, pointer, path, sourcePointer string, depth int) {
	m.metadata.Scopes = append(m.metadata.Scopes, admission.RealizationScope{FieldPointer: pointer, Closure: m.closure(sourcePointer)})
	original, isRecord := source.(map[string]any)
	_, isSequence := source.([]any)
	_, hasValue := value[termValue]
	scalarAlias := len(value) == 2 && value[termIdentityMarker] != nil && hasValue && !isRecord && !isSequence
	if presence, ok := original[termPresence].(string); ok && softwarePresence(m.concern.definition.kind, sourcePointer) {
		m.metadata.MemberPresence[pointer] = presence
	}
	for _, key := range m.fieldOrder(value, sourcePointer) {
		if scalarAlias {
			m.collect(value[key], source, metadataPointer(pointer, key), path, sourcePointer, depth+1)
			continue
		}
		sourceKey := strings.TrimSuffix(strings.TrimSuffix(key, "_present"), "_commitment")
		m.collect(value[key], original[sourceKey], metadataPointer(pointer, key), path+"."+sourceKey, metadataPointer(sourcePointer, sourceKey), depth+1)
	}
	if m.concern.definition.kind == termRuntimeSoftwareComponents {
		m.softwareConstraints(original, pointer, path)
	}
}
func (m *concernMetadata) collectSequence(value []any, source any, pointer, path, sourcePointer string, depth int) {
	closure := m.closure(sourcePointer)
	m.metadata.Scopes = append(m.metadata.Scopes, admission.RealizationScope{FieldPointer: pointer, Closure: closure})
	identity := m.collectionIdentity(pointer)
	if pointer == "" && m.concern.definition.kind == "runtime-packages" {
		identity = packageIdentity(value)
	}
	if len(identity) > 0 {
		m.metadata.CollectionProfiles = append(m.metadata.CollectionProfiles, admission.RealizationCollectionProfile{FieldPointer: pointer, CollectionKind: m.concern.definition.kind, IdentityFields: identity, Closure: closure})
	}
	original, ok := source.([]any)
	if !ok {
		m.invalid = true
		return
	}
	indices := m.sequenceSourceIndices(original, sourcePointer)
	if len(indices) != len(value) {
		m.invalid = true
		return
	}
	for index, child := range value {
		sourceIndex := indices[index]
		position := strconv.Itoa(sourceIndex)
		m.collect(child, original[sourceIndex], metadataPointer(pointer, strconv.Itoa(index)), path+"["+position+"]", metadataPointer(sourcePointer, position), depth+1)
	}
}
func (m *concernMetadata) sequenceSourceIndices(original []any, pointer string) []int {
	indices := make([]int, 0, len(original))
	for index, item := range original {
		if m.concern.definition.kind == termRuntimeMounts && pointer == "" {
			record, _ := item.(map[string]any)
			if record["source_kind"] != termBind && record["source_kind"] != termTmpfs {
				continue
			}
		}
		indices = append(indices, index)
	}
	return indices
}

func (m *concernMetadata) leaf(projected, source any, pointer, sourcePointer string, record explicitnessRecord, authored bool) {
	var rule any
	switch {
	case authored && record.Classification == termOpen:
		if source != termUnknown && source != "other" {
			m.invalid = true
			return
		}
		rule = map[string]any{termKind: "knowledge", "state": termUnknown}
	case authored && record.Classification == termConstrained:
		rule = m.constrainedLeafRule(projected, source, pointer, sourcePointer)

	case !authored && m.closure(sourcePointer).Posture == termOpen:
		rule = map[string]any{termKind: "delegated"}
	}
	if rule != nil {
		fragment, err := m.concern.input.valueFragment(rule)
		if err != nil {
			m.err = err
			return
		}
		m.metadata.LeafConstraints[pointer] = fragment
	}
}

func (m *concernMetadata) constrainedLeafRule(projected, source any, pointer, sourcePointer string) any {
	if !runtimeMarker(pointer) && domain.Equal(source, projected) {
		if rule, found := m.parameterImageRule(projected, pointer, sourcePointer); found {
			return rule
		}
	}
	var selectedDomain any
	if pointer == "" && m.domain != nil {
		selectedDomain = m.domain.Document()
	}
	if selectedDomain == nil && !runtimeMarker(pointer) {
		selectedDomain = m.authoredLeafDomain(sourcePointer)
	}
	if m.err != nil {
		return nil
	}
	if selectedDomain == nil {
		m.invalid = true
		return nil
	}
	return map[string]any{termKind: termDomain, termDomain: selectedDomain}
}
func (m *concernMetadata) parameterImageRule(projected any, pointer, sourcePointer string) (any, bool) {
	image, found, err := sdl.ParameterDerivationImage(m.concern.input.scenario, m.concern.pointer+sourcePointer)
	if err != nil {
		if category, ok := fault.CategoryOf(err); ok && category == fault.InvalidInput {
			m.invalid = true
		} else {
			m.err = err
		}
		return nil, true
	}
	if !found {
		return nil, false
	}
	m.metadata.Origins[pointer] = termProcessor
	if image == nil {
		return map[string]any{termKind: termLiteral, termValue: projected}, true
	}
	return map[string]any{termKind: termDomain, termDomain: map[string]any{termKind: termEnum, termValues: image.Document()}}, true
}
func (m *concernMetadata) authoredLeafDomain(sourcePointer string) any {
	constraint, exists := m.concern.input.constraints[m.concern.pointer+sourcePointer]
	if !exists {
		return nil
	}
	values := make([]any, len(constraint.Values))
	for index, raw := range constraint.Values {
		value, err := nativeValue(raw)
		if err != nil {
			m.err = err
			return nil
		}
		values[index] = value
	}
	return map[string]any{termKind: termEnum, termValues: values}
}

func (m *concernMetadata) collectionIdentity(pointer string) []string {
	if pointer == "" {
		return m.concern.definition.identity
	}
	kind := m.concern.definition.kind
	if kind == "runtime-datastore-services" || kind == "runtime-orchestration-authorities" || kind == "runtime-app-authorizations" {
		if identity := sdlrules.RuntimeCollectionIdentity(strings.TrimPrefix(kind, "runtime-"), pointer); identity != "" {
			return []string{identity}
		}
	}
	tokens := jsonpointer.Tokens(pointer)
	field := tokens[len(tokens)-1]
	identity := ""
	switch {
	case kind == termRuntimeSoftwareComponents && field == "repository_refs":
		identity = termIdentityMarker
	case kind == termRuntimeRepositoryState:
		identity = map[string]string{"repositories": termRepositoryID, "trust_bindings": termTrustID}[field]
	case kind == termLinuxCapabilities && slices.Contains([]string{termRequired, termEffective, termAdd, termDrop, "process_overrides"}, field):
		identity = termIdentityMarker
	case kind == termRuntimeMounts && field == termOptions:
		identity = termIdentityMarker
	case kind == termForwardingAgents:
		identity = map[string]string{termSources: "source_id", termTransforms: "transform_id", termShipTargets: "target_id", termReloadChannels: "reload_channel_id", "settings": termSettingID}[field]
	}
	if identity != "" {
		return []string{identity}
	}
	return nil
}

func packageIdentity(rows []any) []string {
	seen := map[string]bool{}
	for _, item := range rows {
		row, _ := item.(map[string]any)
		identity, err := projectionDigest([]any{row[termManager], row[termName]})
		if err != nil || seen[identity] {
			return []string{termManager, termName, termArchitecture}
		}
		seen[identity] = true
	}
	return []string{termManager, termName}
}

func softwarePresence(kind, pointer string) bool {
	tokens := jsonpointer.Tokens(pointer)
	return kind == termRuntimeSoftwareComponents && len(tokens) == 1 || kind == termRuntimeRepositoryState && len(tokens) == 2 && (tokens[0] == "repositories" || tokens[0] == "trust_bindings")
}

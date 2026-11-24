package admission

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"slices"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

// Fixture kinds that must be internally consistent. An invalid fixture stays
// as written, so it can test an absent derived field.
const (
	fixtureKindValid          = "valid"
	fixtureKindContextInvalid = "context-invalid"
)

var errSealInapplicable = errors.New("derived field cannot be computed")

// SealFixture returns a valid or context-invalid fixture of contractID with
// each absent derived field filled: self-digests and derived identifiers.
// Nested owners are sealed first, and a present value stays as written. The
// existing members keep their order and each filled member follows them.
// Other kinds, other contracts and owners that do not validate stay as
// written. Sealing grants no admission.
func SealFixture(v *Validator, contractID, kind string, data []byte, limits ingress.Limits) ([]byte, error) {
	if v == nil {
		return nil, invalid()
	}
	if (kind != fixtureKindValid && kind != fixtureKindContextInvalid) || !slices.Contains(sealedContracts(), contractID) {
		return data, nil
	}
	fills := map[string][]sealedMember{}
	_, err := v.low.VisitDefinitions(contractID, data, limits, func(visit validation.DefinitionVisit) error {
		v.sealOwner(contractID, visit, fills)
		return nil
	})
	if err != nil {
		return nil, err
	}
	if len(fills) == 0 {
		return data, nil
	}
	return insertMembers(data, fills)
}

// sealedContracts names the contracts whose documents contain derived fields.
func sealedContracts() []string {
	return []string{
		trialPlanContract, "assigned-trial-v1", "authoring-adapter-vector-v1", "domain-profile-definition-v1",
		"experiment-authoring-input-v1", "experiment-run-v1", "experiment-study-v1", "materialization-archive-record-v1",
		termMixedParticipantCompositionProfileV1, "participant-configuration-result-v1",
		"participant-opacity-analysis-evidence-v1", "participant-opacity-model-check-evidence-v1",
		"plan-realization-profiles-v1", termRealizationEnvelopeV1, termRealizedTimeModelV1,
		"sdl-candidate-synthesis-input-v1", "sdl-candidate-synthesis-record-v1", "semantic-comparison-request-v1",
		"semantic-comparison-result-v1", "semantic-projection-report-v1",
	}
}

type sealedMember struct {
	key   string
	value any
}

// sealField is one derived field of an owner model: its path in the owner
// and how its value is computed from the owner.
type sealField struct {
	path        []string
	compute     func(*sealContext) (any, error)
	placeholder any
}

type sealContext struct {
	e                      *Validator
	contractID, definition string
	root                   bool
	node                   map[string]any
}

func digestPlaceholder() string { return "sha256:" + strings.Repeat("0", 64) }

// view returns the owner with its published defaults. The root model uses
// the contract defaults; a nested model uses its $defs member.
func (s *sealContext) view() (map[string]any, error) {
	if s.root {
		value, err := s.e.defaulted(s.contractID, s.node)
		if err != nil {
			return nil, err
		}
		if view := object(value); view != nil {
			return view, nil
		}
		return nil, invalid()
	}
	raw, err := json.Marshal(s.node)
	if err != nil {
		return nil, invalid()
	}
	return s.e.low.DefaultedObjectFragment(s.contractID, schemaDefinitionsPrefix+s.definition, raw, ingress.Limits{MaxBytes: max(32<<20, 2*len(raw)), MaxDepth: 64})
}

// sealOwner follows the reference engine: fill placeholders, then compute
// one field at a time, because a later value can cover an earlier one. An
// owner that does not validate keeps all of its derived fields absent.
func (e *Validator) sealOwner(contractID string, visit validation.DefinitionVisit, fills map[string][]sealedMember) {
	fields := sealFields()[visit.Definition]
	if len(fields) == 0 {
		return
	}
	type pending struct {
		parent  map[string]any
		pointer string
		field   sealField
	}
	var work []pending
	for _, field := range fields {
		parent, pointer := visit.Value, visit.Path
		for _, key := range field.path[:len(field.path)-1] {
			parent = object(parent[key])
			pointer += "/" + jsonpointer.EscapeToken(key)
		}
		key := field.path[len(field.path)-1]
		if _, present := parent[key]; parent == nil || present {
			continue
		}
		parent[key] = field.placeholder
		work = append(work, pending{parent, pointer, field})
	}
	context := &sealContext{e: e, contractID: contractID, root: visit.Path == "", definition: visit.Definition, node: visit.Value}
	values := make([]any, 0, len(work))
	for _, item := range work {
		value, err := item.field.compute(context)
		if err != nil {
			for _, other := range work {
				delete(other.parent, other.field.path[len(other.field.path)-1])
			}
			return
		}
		item.parent[item.field.path[len(item.field.path)-1]] = value
		values = append(values, value)
	}
	for index, item := range work {
		fills[item.pointer] = append(fills[item.pointer], sealedMember{item.field.path[len(item.field.path)-1], values[index]})
	}
}

// validated computes a value only from an owner that validates with its
// placeholders, as the reference engine requires.
func validated(compute func(*sealContext, map[string]any) (any, error)) func(*sealContext) (any, error) {
	return func(s *sealContext) (any, error) {
		view, err := s.view()
		if err != nil {
			return nil, err
		}
		return compute(s, view)
	}
}

func viewSelfDigest(field string) func(*sealContext) (any, error) {
	return validated(func(_ *sealContext, view map[string]any) (any, error) { return selfDigest(view, field) })
}

func viewDigest(path ...string) func(*sealContext) (any, error) {
	return validated(func(_ *sealContext, view map[string]any) (any, error) { return jsonDigest(at(view, path...)) })
}

func trialSealField(field string) sealField {
	return sealField{path: []string{field}, placeholder: digestPlaceholder(), compute: func(s *sealContext) (any, error) {
		_, expected, err := s.e.expectedTrialDigest(s.contractID, s.node, field)
		return expected, err
	}}
}

// sealFields maps each owner model to its derived fields in reference order.
func sealFields() map[string][]sealField {
	placeholder := digestPlaceholder()
	return map[string][]sealField{
		modelAdmittedTrialEntry:  {trialSealField("entry_digest")},
		"AdmittedTrialPlanModel": {trialSealField("plan_digest")},
		"AuthoringAdapterVectorModel": {
			{path: []string{"input_digest"}, placeholder: placeholder, compute: validated(func(s *sealContext, _ map[string]any) (any, error) {
				return digest.SHA256([]byte(stringAt(s.node, "input_source"))), nil
			})},
			{path: []string{"operation_digest"}, placeholder: placeholder, compute: validated(func(s *sealContext, _ map[string]any) (any, error) {
				return authoringOperationDigest(s.node)
			})},
		},
		"DomainProfileSchemaModel": {{path: []string{"schema_digest"}, placeholder: placeholder, compute: validated(func(s *sealContext, _ map[string]any) (any, error) {
			return jsonDigest(at(s.node, "schema_document"))
		})}},
		"DomainProfileDefinitionModel": {{path: []string{"coordinate", "definition_digest"}, placeholder: placeholder, compute: validated(func(_ *sealContext, view map[string]any) (any, error) {
			return domainProfileDefinitionDigest(view)
		})}},
		"AdmittedDomainProfileDefinitionModel": {{path: []string{"provenance", "source_digest"}, placeholder: placeholder, compute: validated(func(s *sealContext, _ map[string]any) (any, error) {
			return at(s.node, "definition", "coordinate", "definition_digest"), nil
		})}},
		"BackendRealizationEnvelopeModel": {
			{path: []string{termConfiguration, "configuration_digest"}, placeholder: placeholder, compute: validated(func(_ *sealContext, view map[string]any) (any, error) {
				return envelopeConfigurationDigest(envelopeDigestConfiguration(at(view, termConfiguration)))
			})},
			{path: []string{termDigest}, placeholder: placeholder, compute: validated(func(_ *sealContext, view map[string]any) (any, error) {
				return envelopeDigest(view)
			})},
		},
		"ParticipantOpacityModelCheckEvidenceModel": {
			{path: []string{"assumptions_digest"}, placeholder: placeholder, compute: viewDigest(fieldAssumptions)},
			{path: []string{"checker_configuration_digest"}, placeholder: placeholder, compute: viewDigest("checker_configuration")},
			{path: []string{"counterexample", "counterexample_digest"}, placeholder: placeholder, compute: validated(func(_ *sealContext, view map[string]any) (any, error) {
				return opacityModelCounterexampleDigest(view)
			})},
		},
		"ParticipantOpacityAnalysisEvidenceModel": {
			{path: []string{"checker_configuration_digest"}, placeholder: placeholder, compute: viewDigest("checker_configuration")},
			{path: []string{"counterexample", "counterexample_digest"}, placeholder: placeholder, compute: validated(func(_ *sealContext, view map[string]any) (any, error) {
				return opacityCounterexampleDigest(view)
			})},
		},
		"CandidateSynthesisInputModel": {{path: []string{termSource, "assertion_set_digest"}, placeholder: placeholder, compute: viewDigest("assertions")}},
		"MaterializationArchiveRecord": {{path: []string{"artifact", "uri"}, placeholder: "urn:sha256:" + strings.Repeat("0", 64), compute: validated(func(s *sealContext, _ map[string]any) (any, error) {
			return "urn:sha256:" + stringAt(s.node, "artifact", "checksum", "value"), nil
		})}},
		"ImpactScopeModel": {{path: []string{"scope_digest"}, placeholder: placeholder, compute: viewSelfDigest("scope_digest")}},
		"SemanticComparisonResultModel": {{path: []string{"impact_scope_digest"}, placeholder: placeholder, compute: validated(func(s *sealContext, _ map[string]any) (any, error) {
			return at(s.node, "impact_scope", "scope_digest"), nil
		})}},
		"DifficultyPolicyModel": {{path: []string{"policy_digest"}, placeholder: placeholder, compute: viewSelfDigest("policy_digest")}},
		"ParticipantConfigurationResultModel": {{path: []string{"configuration_digest"}, placeholder: placeholder, compute: validated(func(s *sealContext, _ map[string]any) (any, error) {
			return expectedConfigurationDigest(s.node)
		})}},
		"SemanticProjectionPredicateProfileModel": {
			{path: []string{"adapter_digest"}, placeholder: placeholder, compute: validated(func(s *sealContext, _ map[string]any) (any, error) {
				return projectionAdapterDigest(s.node)
			})},
			{path: []string{"profile_digest"}, placeholder: placeholder, compute: viewSelfDigest("profile_digest")},
		},
		"SemanticProjectionReportModel": {
			{path: []string{"frame_digest"}, placeholder: placeholder, compute: viewDigest("frame")},
			{path: []string{"summary", "frame_digest"}, placeholder: placeholder, compute: viewDigest("frame")},
			{path: []string{"summary", "predicate_profile_digest"}, placeholder: placeholder, compute: validated(func(_ *sealContext, view map[string]any) (any, error) {
				return at(view, "frame", "predicate_profile", "profile_digest"), nil
			})},
			{path: []string{"summary", "qualified_fraction"}, placeholder: "pending", compute: validated(func(_ *sealContext, view map[string]any) (any, error) {
				frame, err := jsonDigest(at(view, "frame"))
				if err != nil {
					return nil, err
				}
				return projectionQualifiedFraction(at(view, "summary"), frame)
			})},
		},
		"CandidateSynthesisProfileDefinitionModel": {{path: []string{"profile_digest"}, placeholder: placeholder, compute: viewSelfDigest("profile_digest")}},
		"CandidateSynthesisRecordModel": {
			{path: []string{"input_digest"}, placeholder: placeholder, compute: viewDigest("input")},
			{path: []string{"transformation_report", "source_digest"}, placeholder: placeholder, compute: viewDigest("input")},
		},
		"RealizedTimeModelProvenanceModel": {{path: []string{"declaration_digest"}, placeholder: placeholder, compute: validated(func(_ *sealContext, view map[string]any) (any, error) {
			declared := at(view, "declared_model")
			timeFactoryDefaults(declared)
			return declarationDigest(declared)
		})}},
		"MixedParticipantCompositionProfileModel": {{path: []string{"profile_digest"}, placeholder: placeholder, compute: viewSelfDigest("profile_digest")}},
		"ExperimentScenarioSelectionDescriptorModel": {{path: []string{"selection_id"}, placeholder: "selection-" + strings.Repeat("0", 64), compute: validated(func(s *sealContext, _ map[string]any) (any, error) {
			return expectedSelectionID(s.node)
		})}},
	}
}

// domainProfileDefinitionDigest digests the definition projection without
// its self-reference.
func domainProfileDefinitionDigest(view map[string]any) (string, error) {
	coordinate := at(view, "coordinate")
	return jsonDigest(map[string]any{
		"schema_version": "domain-profile-definition/v1",
		"identity": map[string]any{
			termNamespace: at(coordinate, termNamespace), termAuthority: at(coordinate, termAuthority),
			termProfileID: at(coordinate, termProfileID), termRevision: at(coordinate, termRevision),
		},
		"profile_schema":    at(view, "profile_schema"),
		"semantic_contract": at(view, "semantic_contract"),
		"allowed_contexts":  at(view, "allowed_contexts"),
	})
}

// insertMembers appends members to the objects at their JSON pointers and
// keeps every original byte, so member order and number spelling stay.
func insertMembers(data []byte, fills map[string][]sealedMember) ([]byte, error) {
	type frame struct {
		object, expectKey bool
		pointer           string
		count             int
	}
	insertions := map[int][]byte{}
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.UseNumber()
	var stack []frame
	next := ""
	for {
		token, err := decoder.Token()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return nil, invalid()
		}
		pointer := next
		if len(stack) > 0 {
			top := &stack[len(stack)-1]
			if top.expectKey && token != json.Delim('}') {
				key, ok := token.(string)
				if !ok {
					return nil, invalid()
				}
				top.expectKey = false
				next = top.pointer + "/" + jsonpointer.EscapeToken(key)
				continue
			}
		}
		switch token {
		case json.Delim('{'), json.Delim('['):
			object := token == json.Delim('{')
			stack = append(stack, frame{object: object, expectKey: object, pointer: pointer})
			if token == json.Delim('[') {
				next = pointer + "/0"
			}
			continue
		case json.Delim('}'):
			top := stack[len(stack)-1]
			if members := fills[top.pointer]; len(members) > 0 {
				text, encodeErr := encodeMembers(members, top.count > 0)
				if encodeErr != nil {
					return nil, encodeErr
				}
				insertions[int(decoder.InputOffset())-1] = text
				delete(fills, top.pointer)
			}
			stack = stack[:len(stack)-1]
		case json.Delim(']'):
			stack = stack[:len(stack)-1]
		}
		if len(stack) > 0 {
			top := &stack[len(stack)-1]
			top.count++
			top.expectKey = top.object
			if !top.object {
				next = top.pointer + "/" + strconv.Itoa(top.count)
			}
		}
	}
	if len(fills) > 0 {
		return nil, errSealInapplicable
	}
	offsets := make([]int, 0, len(insertions))
	for offset := range insertions {
		offsets = append(offsets, offset)
	}
	slices.Sort(offsets)
	var result bytes.Buffer
	previous := 0
	for _, offset := range offsets {
		result.Write(data[previous:offset])
		result.Write(insertions[offset])
		previous = offset
	}
	result.Write(data[previous:])
	return result.Bytes(), nil
}

func encodeMembers(members []sealedMember, separated bool) ([]byte, error) {
	var text bytes.Buffer
	for index, member := range members {
		if separated || index > 0 {
			text.WriteByte(',')
		}
		key, err := json.Marshal(member.key)
		if err != nil {
			return nil, invalid()
		}
		value, err := json.Marshal(member.value)
		if err != nil {
			return nil, invalid()
		}
		text.Write(key)
		text.WriteByte(':')
		text.Write(value)
	}
	return text.Bytes(), nil
}

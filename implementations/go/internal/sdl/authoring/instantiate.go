package authoring

import (
	"encoding/json"
	"errors"
	"fmt"
	"maps"
	"slices"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

const (
	instantiatedContract = "instantiated-scenario-v1"
	snapshotContract     = "instantiated-scenario-snapshot-v1"
	snapshotProfile      = "raes-sdl-instantiated-snapshot/v2"
)

type instantiationError struct{ findings []diagnostic.Diagnostic }

func (e *instantiationError) Error() string            { return "invalid-input: sdl-instantiation-invalid" }
func (e *instantiationError) Code() string             { return "sdl-instantiation-invalid" }
func (e *instantiationError) Category() fault.Category { return fault.InvalidInput }
func (e *instantiationError) Unwrap() error            { return fault.New(fault.InvalidInput, e.Code(), nil) }
func (e *instantiationError) Diagnostics() []diagnostic.Diagnostic {
	return copySemanticDiagnostics(e.findings)
}

func instantiationRefusal(messages ...string) error {
	findings := make([]diagnostic.Diagnostic, len(messages))
	for i, message := range messages {
		findings[i] = diagnostic.Diagnostic{Code: "sdl.instantiation", Domain: "sdl", Stage: "instantiation", Severity: termError, Message: message}
	}
	return &instantiationError{findings: findings}
}

// Instantiated reports native concrete admission of an immutable document.
func (d *Document) Instantiated() bool { return d.Validated() && d.contract == instantiatedContract }

// Instantiate binds one family without modifying it and re-admits the concrete result.
func (p *Parser) Instantiate(document *Document, parameters map[string]any, profile string) (*Document, error) {
	admitted, _, err := p.Validate(document)
	if err != nil {
		return nil, instantiationFailure(err)
	}
	if admitted.contract != authoringContract && admitted.contract != expandedContract {
		return nil, instantiationRefusal("Instantiation requires authored SDL; descriptions require explicit derivation.")
	}
	if len(admitted.semantic.variations) != 0 {
		return nil, instantiationRefusal("Scenario has unresolved variation points; recorded selection integration is required before instantiation.")
	}
	return p.instantiate(admitted, parameters, profile, nil)
}

func (p *Parser) instantiate(document *Document, parameters map[string]any, profile string, trial any) (*Document, error) {
	identity, err := document.CanonicalDigest()
	if err != nil {
		return nil, err
	}
	input := document
	if input.expanded != nil {
		input = input.expanded
	}
	value, err := p.modelValue(input)
	if err != nil {
		return nil, err
	}
	values, bindings, err := resolveInstantiation(value, input.semanticOrder(), parameters)
	if err != nil {
		return nil, err
	}
	payload, facts, err := p.boundInstantiation(input, value, values)
	if err != nil {
		return nil, err
	}
	provenance := instantiationProvenance(value, facts, identity, bindings, profile, trial)
	for _, field := range []string{variablesSection, variationPointsField, importsField, "module", "realization", "expansion_provenance"} {
		delete(payload, field)
	}
	provenance[termExplicitness], err = instantiatedExplicitness(document.semantic, payload)
	if err != nil {
		return nil, err
	}
	if len(array(provenance[termParameterDerivations])) == 0 {
		delete(provenance, termParameterDerivations)
	}
	payload["instantiation_provenance"] = provenance
	encoded, err := encode(instantiationOrder(payload, "", facts.order), compositionJSONWork(p.limits), false)
	if err != nil {
		return nil, err
	}
	result, err := p.admitInstantiated(encoded, input)
	return result, instantiationFailure(err)
}

// Keep declaration order through binding. The payload is already bounded by
// source admission and substitution; the JSON writer still enforces its byte
// ceiling. Sorting a map here would change subsequent compiler finding order.
func instantiationOrder(input any, pointer string, order map[string][]string) any {
	switch v := input.(type) {
	case map[string]any:
		result := make(ordered, 0, len(v))
		for _, name := range orderedKeys(v, order[pointer]) {
			result = append(result, field{name: name, value: instantiationOrder(v[name], pointer+"/"+jsonpointer.EscapeToken(name), order)})
		}
		return result
	case []any:
		result := make([]any, len(v))
		for i, item := range v {
			result[i] = instantiationOrder(item, pointer+"/"+strconv.Itoa(i), order)
		}
		return result
	default:
		return input
	}
}

func (p *Parser) boundInstantiation(input *Document, value, values map[string]any) (map[string]any, *importFacts, error) {
	facts, err := newImportFacts(input, value)
	if err != nil {
		return nil, nil, err
	}
	c := composition{parser: p}
	if err = c.captureImportConstraints(value, nil, facts); err != nil {
		return nil, nil, err
	}
	full, err := c.bindingPayload(value, facts.order)
	if err != nil {
		return nil, nil, fmt.Errorf("construct binding payload: %w", err)
	}
	pinned, hasPinned := full[controlAssetsSection]
	delete(full, controlAssetsSection)
	allowance := copyBudget{remaining: p.limits.MaxComposedBytes}
	substitute := substitution{values: values, keepUnknown: true, copies: &allowance, inline: map[string]string{}}
	bound, err := substitute.walk(full)
	if err != nil {
		return nil, nil, err
	}
	payload := object(bound)
	if hasPinned {
		payload[controlAssetsSection] = pinned
	}
	if containsVariable(payload) {
		unresolved := map[string]bool{}
		collectInstantiationTokens(payload, unresolved)
		return nil, nil, instantiationRefusal("Scenario contains unresolved variable references after instantiation: " + strings.Join(slices.Sorted(maps.Keys(unresolved)), ", ") + ".")
	}
	return payload, facts, nil
}

func instantiationProvenance(value map[string]any, facts *importFacts, identity string, bindings []any, profile string, trial any) map[string]any {
	provenance := map[string]any{
		"authored_digest":  map[string]any{termProfile: semanticProfile, "algorithm": "sha256", valueField: identity},
		"selected_profile": nil, termBindings: bindings, importsField: []any{},
		termCapabilityConstraints: []any{}, termParameterDerivations: []any{},
		termExplicitness: []any{}, termRealizationDesignations: facts.designation, termRealizationConstraints: facts.realization,
	}
	if profile != "" {
		provenance["selected_profile"] = profile
	}
	if trial != nil {
		provenance["trial"] = trial
	}
	if expanded := object(value["expansion_provenance"]); expanded != nil {
		for _, field := range []string{importsField, termCapabilityConstraints, termParameterDerivations, termRealizationDesignations, termRealizationConstraints} {
			if records, present := expanded[field]; present {
				provenance[field] = records
			}
		}
	}
	for _, constraint := range facts.constraints {
		provenance[termCapabilityConstraints] = append(array(provenance[termCapabilityConstraints]), map[string]any{kindField: constraint.Kind, fieldPointerField: constraint.Pointer, variationParameterKind: constraint.Parameter, allowedValuesField: constraint.Allowed})
	}
	provenance[termParameterDerivations] = append(array(provenance[termParameterDerivations]), facts.derivations...)
	return provenance
}

func instantiationFailure(err error) error {
	if findings, ok := errors.AsType[diagnostic.Error](err); ok {
		messages := []string{}
		for _, finding := range findings.Diagnostics() {
			messages = append(messages, finding.Message)
		}
		return instantiationRefusal(messages...)
	}
	return err
}

func (d *Document) semanticOrder() map[string][]string {
	order, _ := semanticOrder(d.modelBytes()) // Construction already guarantees valid JSON.
	return order
}

func resolveInstantiation(value map[string]any, order map[string][]string, parameters map[string]any) (map[string]any, []any, error) {
	variables := object(value[variablesSection])
	values, bindings, messages := map[string]any{}, []any{}, []string{}
	for _, name := range orderedKeys(variables, order["/variables"]) {
		definition := object(variables[name])
		candidate, origin, present := instantiationCandidate(name, definition, parameters)
		if !present {
			if definition["required"] == true {
				messages = append(messages, fmt.Sprintf("Variable '%s' is required and has no provided value or default.", name))
			}
			continue
		}
		candidate = instantiationNumber(candidate)
		if !variableType(candidate, text(definition["type"])) {
			messages = append(messages, fmt.Sprintf("Variable '%s' expects type '%s', got %s.", name, text(definition["type"]), pythonType(candidate)))
			continue
		}
		if !allowedValue(candidate, array(definition[allowedValuesField])) {
			messages = append(messages, fmt.Sprintf("Variable '%s' does not satisfy its allowed_values constraint.", name))
			continue
		}
		values[name] = candidate
		bindings = append(bindings, map[string]any{variationParameterKind: []any{name}, "origin": origin, valueField: candidate})
	}
	for _, name := range slices.Sorted(maps.Keys(parameters)) {
		if _, declared := variables[name]; !declared {
			messages = append(messages, fmt.Sprintf("Instantiation parameter '%s' is not a declared variable.", name))
		}
	}
	if len(messages) != 0 {
		return nil, nil, instantiationRefusal(messages...)
	}
	return values, bindings, nil
}

func instantiationCandidate(name string, definition, parameters map[string]any) (any, string, bool) {
	candidate, provided := parameters[name]
	if provided {
		return candidate, "provided", true
	}
	candidate = definition[defaultField]
	return candidate, "default", candidate != nil
}
func instantiationNumber(value any) any {
	switch number := value.(type) {
	case int:
		return json.Number(strconv.Itoa(number))
	case int64:
		return json.Number(strconv.FormatInt(number, 10))
	case uint64:
		return json.Number(strconv.FormatUint(number, 10))
	default:
		return value
	}
}
func pythonType(value any) string {
	switch value := value.(type) {
	case string:
		return "str"
	case bool:
		return "bool"
	case json.Number:
		if strings.ContainsAny(string(value), ".eE") {
			return termFloat
		}
		return "int"
	case float64:
		return termFloat
	case nil:
		return "NoneType"
	case []any:
		return "list"
	default:
		return "dict"
	}
}

func collectInstantiationTokens(value any, into map[string]bool) {
	switch v := value.(type) {
	case string:
		for _, name := range semanticVariableNames(v) {
			into[name] = true
		}
	case map[string]any:
		for _, child := range v {
			collectInstantiationTokens(child, into)
		}
	case []any:
		for _, child := range v {
			collectInstantiationTokens(child, into)
		}
	}
}

func instantiatedExplicitness(model *semanticModel, payload map[string]any) ([]any, error) {
	if err := model.loadIntent(); err != nil {
		return nil, err
	}
	result := []any{}
	for _, path := range model.intent.paths {
		record := model.intent.records[path]
		section, _, _ := strings.Cut(path, ".")
		_, retained := payload[section]
		phaseContainer := path == variablesSection || path == variationPointsField
		if !retained && !phaseContainer {
			continue
		}
		parameters := []any{}
		for _, name := range record.Variables {
			parameters = append(parameters, []any{name})
		}
		if len(parameters) > 0 {
			record.Provenance = "processor-derived"
			record.Reason = "parameter/default substitution preserved authored explicitness class"
		}
		result = append(result, map[string]any{"model_path": path, "classification": record.Classification, "provenance": record.Provenance, "reason": record.Reason, "parameters": parameters})
	}
	return mergeExpandedExplicitness(result, model.root), nil
}

// AdmitInstantiated checks untrusted serialized phase data and reruns semantics.
func (p *Parser) AdmitInstantiated(data []byte) (*Document, error) {
	return p.admitInstantiated(data, nil)
}

func (p *Parser) admitInstantiated(data []byte, origin *Document) (*Document, error) {
	if p == nil || p.models == nil {
		return nil, invalid()
	}
	value, err := ingress.Parse(data, ingress.Limits{MaxBytes: int(p.limits.MaxComposedBytes), MaxDepth: p.limits.MaxDepth * 2}, ingress.Object)
	if err != nil {
		return nil, err
	}
	payload := object(value)
	if containsVariable(payload) {
		return nil, instantiationRefusal("InstantiatedScenario must not contain unresolved variable references.")
	}
	if err = p.models.CheckSDLConstruction(instantiatedContract, "#", data, modelLimits(data)); err != nil {
		return nil, fmt.Errorf("check concrete model: %w", err)
	}
	options := p.options("instantiated.json", "reject")
	options.Limits.MaxInputBytes = p.limits.MaxComposedBytes
	parsed, err := source.Decode(data, options)
	if err != nil {
		return nil, err
	}
	fill := importDefaultWalk{queries: newScopeQueries(p, instantiatedContract, payload), remaining: compositionJSONWork(p.limits)}
	full, err := fill.value(payload, p.schemas[instantiatedContract], "#")
	if err != nil {
		return nil, err
	}
	encoded, modelData, err := p.construct(object(full), instantiatedContract, nil, parsed)
	if err != nil {
		return nil, fmt.Errorf("construct concrete model: %w", err)
	}
	document := &Document{contract: instantiatedContract, data: encoded, modelData: modelData, sourceName: "instantiated.json", source: parsed}
	if origin != nil {
		document.source, document.sourceName, document.importOrigins = origin.source, origin.sourceName, origin.importOrigins
	}
	if err = p.checkInstantiationProvenance(payload); err != nil {
		return nil, err
	}
	admitted, _, err := p.Validate(document)
	return admitted, err
}

// Snapshot returns the canonical instantiated envelope, without changing its owner.
func (d *Document) Snapshot() ([]byte, error) {
	if !d.Instantiated() {
		return nil, invalid()
	}
	return canonicalSemanticJSON(json.Marshal(struct {
		Profile  string          `json:"profile"`
		Scenario json.RawMessage `json:"scenario"`
	}{snapshotProfile, d.data}))
}

// AdmitSDLPhase implements the contract owner's native phase port.
func (p *Parser) AdmitSDLPhase(request admission.SDLPhaseRequest) (admission.SDLPhaseAdmission, error) {
	var document *Document
	var err error
	switch request.ContractID {
	case instantiatedContract:
		document, err = p.AdmitInstantiated(request.Source)
	case authoringContract, materializedContract:
		document, err = p.Decode(Request{Source: request.Source})
		if err == nil && document.contract != request.ContractID {
			err = invalid()
		}
		if err == nil {
			document, _, err = p.Validate(document)
		}
	case snapshotContract:
		return p.admitSnapshot(request)
	default:
		err = invalid()
	}
	if err != nil {
		return admission.SDLPhaseAdmission{}, err
	}
	projection := document.JSON()
	if request.ContractID == instantiatedContract {
		if err = p.models.CheckPortable(instantiatedContract, request.Source, modelLimits(request.Source)); err != nil {
			return admission.SDLPhaseAdmission{}, err
		}
		// Admission fills defaults privately. The phase boundary commits only
		// to the supplied fields, after independently checking the full model.
		projection = slices.Clone(request.Source)
	}
	return admission.SDLPhaseAdmission{ContractID: request.ContractID, SourceSHA256: digest.SHA256(request.Source), Document: projection}, nil
}

func (p *Parser) admitSnapshot(request admission.SDLPhaseRequest) (admission.SDLPhaseAdmission, error) {
	parsed, err := ingress.Parse(request.Source, ingress.Limits{MaxBytes: int(p.limits.MaxComposedBytes), MaxDepth: p.limits.MaxDepth * 2}, ingress.Object)
	if err != nil {
		return admission.SDLPhaseAdmission{}, err
	}
	value := object(parsed)
	if len(value) != 2 || value[termProfile] != snapshotProfile {
		return admission.SDLPhaseAdmission{}, invalid()
	}
	raw, err := json.Marshal(value[termScenario])
	if err != nil {
		return admission.SDLPhaseAdmission{}, err
	}
	_, err = p.AdmitInstantiated(raw)
	if err != nil {
		return admission.SDLPhaseAdmission{}, err
	}
	return admission.SDLPhaseAdmission{ContractID: snapshotContract, SourceSHA256: digest.SHA256(request.Source), Document: slices.Clone(request.Source)}, nil
}

func provenancePointer(root any, pointer string) (any, bool) {
	current := root
	for _, token := range jsonpointer.Tokens(pointer) {
		switch value := current.(type) {
		case map[string]any:
			var exists bool
			current, exists = value[token]
			if !exists {
				return nil, false
			}
		case []any:
			index, err := strconv.Atoi(token)
			if err != nil || index < 0 || strconv.Itoa(index) != token || index >= len(value) {
				return nil, false
			}
			current = value[index]
		default:
			return nil, false
		}
	}
	return current, true
}

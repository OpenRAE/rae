package authoring

import (
	"encoding/json"
	"fmt"
	"slices"
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

const (
	semanticProfile             = "raes-sdl-semantic/v2"
	materializedSemanticProfile = "raes-sdl-materialized/v1"
	canonicalModelErrorCode     = "sdl-canonical-model"
)

// Validated reports successful semantic admission of this immutable value.
func (d *Document) Validated() bool {
	return d != nil && d.source != nil && d.validated && d.semantic != nil
}

// Validate collects semantic errors and advisories. A successful call returns
// a new admitted handle and leaves the constructed input unchanged.
func (p *Parser) Validate(document *Document) (*Document, []diagnostic.Diagnostic, error) {
	if p == nil || p.models == nil || document == nil || document.source == nil || len(document.data) == 0 {
		return nil, nil, semanticInvalid()
	}
	input := document
	if document.expanded != nil {
		input = document.expanded
	}
	model, err := p.newSemanticModel(input)
	if err != nil {
		return nil, nil, err
	}
	if err := model.portableMaterialized(); err != nil {
		return nil, nil, fault.New(fault.InvalidInput, "sdl-materialized-portable-bounds", err)
	}
	collector := newSemanticCollector(input)
	if err := model.check(&collector); err != nil {
		return nil, nil, err
	}
	if len(collector.errors) != 0 {
		return nil, collector.advisories, &semanticError{findings: collector.errors}
	}
	admitted := *document
	admitted.semantic, admitted.validated = model, true
	return &admitted, collector.advisories, nil
}

// CanonicalBytes returns the versioned RFC 8785 semantic projection.
// A document must pass semantic admission before it can have an identity.
func (d *Document) CanonicalBytes() ([]byte, error) {
	if !d.Validated() {
		return nil, semanticInvalid()
	}
	if d.expanded != nil {
		return d.canonicalExpanded()
	}
	if d.contract == materializedContract {
		value := struct {
			Profile  string          `json:"profile"`
			Scenario json.RawMessage `json:"scenario"`
		}{materializedSemanticProfile, d.data}
		return canonicalSemanticJSON(json.Marshal(value))
	}
	var scenario map[string]json.RawMessage
	if err := json.Unmarshal(d.data, &scenario); err != nil {
		return nil, fault.New(fault.Operational, canonicalModelErrorCode, nil)
	}
	delete(scenario, "expansion_provenance")
	if raw := scenario[variationPointsField]; len(raw) != 0 {
		var points map[string]json.RawMessage
		if err := json.Unmarshal(raw, &points); err != nil {
			return nil, fault.New(fault.Operational, canonicalModelErrorCode, nil)
		}
		if len(points) == 0 {
			delete(scenario, variationPointsField)
		}
	}
	value := struct {
		Profile             string                     `json:"profile"`
		Scenario            map[string]json.RawMessage `json:"scenario"`
		ModuleVariables     map[string]json.RawMessage `json:"module_variable_specs"`
		ModuleNodeVariables map[string][]string        `json:"module_node_variable_refs"`
	}{semanticProfile, scenario, map[string]json.RawMessage{}, map[string][]string{}}
	return canonicalSemanticJSON(json.Marshal(value))
}

func canonicalSemanticJSON(encoded []byte, err error) ([]byte, error) {
	if err != nil {
		return nil, fault.New(fault.Operational, canonicalModelErrorCode, nil)
	}
	canonical, err := canonjson.JCS(encoded)
	if err != nil {
		return nil, fault.New(fault.InvalidInput, "sdl-canonical-domain", nil)
	}
	return canonical, nil
}

// CanonicalDigest returns the SHA-256 identity of the canonical semantic bytes.
func (d *Document) CanonicalDigest() (string, error) {
	canonical, err := d.CanonicalBytes()
	if err != nil {
		return "", err
	}
	return digest.SHA256(canonical), nil
}

type semanticError struct{ findings []diagnostic.Diagnostic }

func (e *semanticError) Error() string            { return "invalid-input: " + semanticRefusalCode }
func (e *semanticError) Code() string             { return semanticRefusalCode }
func (e *semanticError) Category() fault.Category { return fault.InvalidInput }
func (e *semanticError) Unwrap() error            { return semanticInvalid() }
func (e *semanticError) Diagnostics() []diagnostic.Diagnostic {
	return copySemanticDiagnostics(e.findings)
}

func copySemanticDiagnostics(input []diagnostic.Diagnostic) []diagnostic.Diagnostic {
	result := slices.Clone(input)
	for i := range result {
		if result[i].Range != nil {
			position := *result[i].Range
			result[i].Range = &position
		}
	}
	return result
}

type semanticOwner struct{ section, name string }
type semanticCollector struct {
	document           *Document
	errors, advisories []diagnostic.Diagnostic
	locations          map[semanticOwner]source.Range
	pointers           map[semanticOwner]string
}

func newSemanticCollector(document *Document) semanticCollector {
	collector := semanticCollector{document: document, locations: map[semanticOwner]source.Range{}, pointers: map[semanticOwner]string{}}
	if document == nil || document.source == nil || document.sourceName == "" {
		return collector
	}
	for _, section := range declarationSections() {
		for _, member := range document.source.View().Child(section).Members() {
			name, _ := member.Key.Scalar()
			if location, present := member.Key.Range(); present {
				collector.locations[semanticOwner{section, name}] = location
			}
		}
	}
	collector.forwarderLocations(document.source.View().Child(forwardingSection), "", []string{forwardingSection})
	for _, member := range document.source.View().Child(nodesSection).Members() {
		name, _ := member.Key.Scalar()
		collector.forwarderLocations(member.Value.Child(runtimeField).Child(forwardingSection), name, []string{nodesSection, name, runtimeField, forwardingSection})
	}
	return collector
}

func (c *semanticCollector) forwarderLocations(view source.View, node string, tokens []string) {
	for i, row := range view.Elements() {
		field := row.Child("forwarding_agent_id")
		id, _ := field.Scalar()
		owner := semanticOwner{forwardingSection, id}
		if node != "" {
			owner = semanticOwner{nodesSection, node + ".runtime." + forwardingSection + "." + id}
		}
		if location, present := field.Range(); present {
			c.locations[owner] = location
		}
		c.pointers[owner] = jsonpointer.FromTokens(appendPath(appendPath(tokens, strconv.Itoa(i)), "forwarding_agent_id"))
	}
}

func (c *semanticCollector) report(owner semanticOwner, message string) {
	c.errors = append(c.errors, c.finding(owner, message, "error"))
}
func (c *semanticCollector) finding(owner semanticOwner, message, severity string) diagnostic.Diagnostic {
	result := diagnostic.Diagnostic{Code: "sdl.semantic", Severity: severity, Stage: "semantic_validation", Message: message}
	if owner.section == "" {
		return result
	}
	result.Domain, result.Address = owner.section, owner.section+"."+owner.name
	result.Pointer = c.pointers[owner]
	if result.Pointer == "" {
		result.Pointer = jsonpointer.FromTokens([]string{owner.section, owner.name})
	}
	if c.document.sourceName != "" {
		if location, present := c.locations[owner]; present {
			result.Source = c.document.sourceName
			result.OriginalPointer = result.Pointer
			result.Range = &diagnostic.Range{StartLine: location.Start.Line, StartColumn: location.Start.Column, EndLine: location.End.Line, EndColumn: location.End.Column}
		}
	}
	if origin, present := c.document.importOrigins[owner]; present && origin.located {
		result.Pointer = origin.canonical
		result.Source = origin.source
		result.OriginalPointer = origin.pointer
		position := origin.position
		result.Range = &diagnostic.Range{StartLine: position.Start.Line, StartColumn: position.Start.Column, EndLine: position.End.Line, EndColumn: position.End.Column}
	}
	return result
}

func (c *semanticCollector) missingResources(name string) {
	message := fmt.Sprintf("Node '%s' is compute without 'resources'. This is valid SDL, but may be undeployable unless the backend supplies defaults.", name)
	c.advisories = append(c.advisories, c.finding(semanticOwner{nodesSection, name}, message, "warning"))
}

package validation

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"maps"
	"math"
	"strings"

	"github.com/santhosh-tekuri/jsonschema/v6"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

const (
	constructionStageInvalidCode = "sdl-construction-stage-invalid"
)

// Node's reference schema hook publishes these two semantic OS dependency
// clauses. The reference formatter performs construction without that stage.
const nodeSemanticClauses = "3778bdc61d14bbcb0626bf210050815770870a81d2c19a742c05f3709f33d18f"

func (v *Validator) loadSDLConstruction() error {
	v.construction = map[string]contract{}
	for _, id := range []string{"sdl-authoring-input-v1", sdlMaterializedContract, "instantiated-scenario-v1"} {
		published, present := v.contracts[id]
		if !present {
			continue // Small isolated schema fixtures need not contain SDL.
		}
		constructed, err := compileSDLConstruction(id, published)
		if err != nil {
			return err
		}
		v.construction[id] = constructed
		published.constructionWork = constructionGraphWork(published.schema)
		v.contracts[id] = published
	}
	return nil
}

func compileSDLConstruction(id string, published contract) (contract, error) {
	defs, _ := published.raw["$defs"].(map[string]any)
	node, _ := defs["Node"].(map[string]any)
	expected := nodeSemanticClauses
	if id == sdlMaterializedContract {
		expected = "0561d2939f767c14777c625fdf74ca9bc374203062b1d7f5e335799d560fa518"
		if !stageDigestMatches(defs["_r221"], "1c6a3f6fa1a26b7c577915a3a7e4bb7af706c46260ad4e40ed2a37ac16dc8c34") {
			return contract{}, failure(fault.Operational, constructionStageInvalidCode)
		}
	}
	if !stageDigestMatches(node["allOf"], expected) {
		return contract{}, failure(fault.Operational, constructionStageInvalidCode)
	}
	root := maps.Clone(published.raw)
	defs = maps.Clone(defs)
	node = maps.Clone(node)
	delete(node, "allOf")
	defs["Node"] = node
	root["$defs"] = defs
	root, err := applySDLFieldPatterns(id, root)
	if err != nil {
		return contract{}, err
	}
	annotations, err := constructionAnnotations(published.annotations)
	if err != nil {
		return contract{}, err
	}
	constructed, err := compileDocument(id, root, annotations)
	if err != nil {
		return contract{}, err
	}
	constructed.constructionWork = constructionGraphWork(constructed.schema)
	return constructed, nil
}

// CheckSDLConstruction checks an authored or materialized SDL construction
// view and its stock local rules, then visits owner model instances. Pointer
// selects the object root ("#") or a reachable value fragment. The published schema
// checks remain unchanged. This operation grants no SDL semantic authority.
func (v *Validator) CheckSDLConstruction(id, pointer string, data []byte, limits ingress.Limits, check func(SchemaInstance) error) error {
	return v.checkSDLConstruction(id, pointer, data, limits, check, false)
}

// CheckSDLLocalSemantics checks the native SDL model view and all stock local
// rules, including the root rules. It grants no contextual or phase authority.
func (v *Validator) CheckSDLLocalSemantics(id string, data []byte, limits ingress.Limits, check func(SchemaInstance) error) error {
	return v.checkSDLConstruction(id, "#", data, limits, check, true)
}

func (v *Validator) checkSDLConstruction(id, pointer string, data []byte, limits ingress.Limits, check func(SchemaInstance) error, rootRules bool) error {
	if v == nil || v.construction[id].schema == nil {
		return failure(fault.InvalidInput, "sdl-construction-contract-unknown")
	}
	if check == nil {
		return failure(fault.Operational, "contract-model-check-required")
	}
	if pointer != "#" && !strings.HasPrefix(pointer, "#/") {
		return failure(fault.InvalidInput, codeContractFragmentUnknown)
	}
	entry := v.construction[id]
	if rootRules {
		entry.annotations = v.contracts[id].annotations
	}
	schema := findSchemaFragment(entry.schema, pointer)
	if schema == nil {
		return failure(fault.InvalidInput, codeContractFragmentUnknown)
	}
	var root any
	var err error
	if pointer == "#" {
		root, err = ingress.Parse(data, limits, ingress.Object)
	} else {
		root, err = parseConstructionValue(data, limits)
	}
	if err != nil {
		return err
	}
	if !boundedNumbers(root) {
		return failure(fault.InvalidInput, "contract-number-limit")
	}
	if err = schema.Validate(root); err != nil {
		return failure(fault.InvalidInput, codeContractSchemaMismatch)
	}
	return v.checkConstructionInstances(id, schema, entry, root, data, check)
}

func parseConstructionValue(data []byte, limits ingress.Limits) (any, error) {
	if limits.MaxBytes < 1 || limits.MaxDepth < 0 {
		return nil, ingress.ErrLimits
	}
	if len(data) > limits.MaxBytes {
		return nil, &ingress.Error{Code: ingress.TooLarge}
	}
	trimmed := bytes.TrimSpace(data)
	if len(trimmed) > 0 && trimmed[0] == '{' {
		return ingress.Parse(data, limits, ingress.Object)
	}
	if len(trimmed) > 0 && trimmed[0] == '[' {
		return ingress.Parse(data, limits, ingress.Array)
	}
	// Preserve the existing ingress support for encoded object fragments.
	if len(trimmed) > 0 && trimmed[0] >= 0x80 {
		if object, err := ingress.Parse(data, limits, ingress.Object); err == nil {
			return object, nil
		}
	}
	return parseConstructionScalar(data, limits)
}

func parseConstructionScalar(data []byte, limits ingress.Limits) (any, error) {
	if len(data) > math.MaxInt-2 {
		return nil, &ingress.Error{Code: ingress.TooLarge}
	}
	wrapped := limits
	wrapped.MaxBytes = min(math.MaxInt-2, limits.MaxBytes) + 2
	if wrapped.MaxDepth > 0 && wrapped.MaxDepth < math.MaxInt {
		wrapped.MaxDepth++
	}
	root, err := ingress.Parse(append(append([]byte{'['}, data...), ']'), wrapped, ingress.Array)
	if err != nil {
		return nil, err
	}
	items, ok := root.([]any)
	if !ok || len(items) != 1 {
		return nil, &ingress.Error{Code: ingress.Invalid}
	}
	return items[0], nil
}

func (v *Validator) checkConstructionInstances(id string, schema *jsonschema.Schema, entry contract, root any, data []byte, check func(SchemaInstance) error) error {
	bound := math.MaxInt
	if len(data) <= math.MaxInt/entry.constructionWork {
		bound = len(data) * entry.constructionWork
	}
	invoked := map[ruleIdentity]bool{}
	options := semanticInvocationOptions{source: string(data)}
	if err := walkSchemaBound(visit{schema, root, ""}, bound, func(current visit) error {
		return v.invoke(id, current, root, nil, entry.annotations, invoked, options)
	}); err != nil {
		return err
	}
	return walkSchemaBound(visit{schema, root, ""}, bound, func(current visit) error {
		return entry.visitInstance(id, current, root, check)
	})
}

// Compilation uses only the packaged finite schema graph. A parsed JSON
// value has at most len(data) distinct paths; each can queue these graph edges.
func constructionGraphWork(root *jsonschema.Schema) int {
	seen := map[*jsonschema.Schema]bool{}
	pending := []*jsonschema.Schema{root}
	work := 0
	for len(pending) > 0 {
		current := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		if current == nil || seen[current] {
			continue
		}
		seen[current] = true
		work++
		for _, child := range compiledChildren(current) {
			if child != nil {
				work++
				pending = append(pending, child)
			}
		}
	}
	return work
}

func stageDigestMatches(value any, expected string) bool {
	raw, err := json.Marshal(value)
	if err != nil {
		return false
	}
	canonical, err := canonjson.Sorted(raw, true)
	return err == nil && fmt.Sprintf("%x", sha256.Sum256(canonical)) == expected
}

func constructionAnnotations(published map[string][]annotation) (map[string][]annotation, error) {
	for _, rule := range published["#"] {
		switch rule.ID {
		case "required-evidence-media-type-provable", "stateful-generated-artifact-semantics", "stateful-persistent-volume-semantics", "stateful-cross-resource-semantics", "initial-service-state-semantics", "participant-shared-time-source-bindings", "materialized-sdl-source-and-inventory-binding":
		default:
			return nil, failure(fault.Operational, constructionStageInvalidCode)
		}
	}
	result := maps.Clone(published)
	delete(result, "#")
	return result, nil
}

func (c contract) walkBound(size int) int {
	if c.constructionWork == 0 || size == 0 {
		return 100000
	}
	if size > math.MaxInt/c.constructionWork {
		return math.MaxInt
	}
	return size * c.constructionWork
}

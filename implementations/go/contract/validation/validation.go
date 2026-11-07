// Package validation admits contract payloads through the published schemas
// and explicit contract-family semantic rules. Schema validity grants no
// authentication, authorization, runtime or evidence authority.
package validation

import (
	"bytes"
	"encoding/json"
	"errors"
	"io/fs"
	"slices"
	"strings"

	"github.com/santhosh-tekuri/jsonschema/v6"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/corpus"
)

// Key selects exactly one owner rule, independent of implementation names.
type Key struct{ ContractID, InvariantID string }

// Invocation gives a rule its applicable instance, root and explicit context.
// A rule must not retain or mutate Root or Instance.
type Invocation struct {
	Key                     Key
	Path                    string
	Root, Instance, Context any
	Inputs                  []Input
	// Source is the immutable original JSON, after bounded schema validation.
	Source string
}

// Input is a contract and instance path declared by the published annotation.
type Input struct {
	ContractID string `json:"contract_id"`
	Path       string `json:"instance_path"`
}

// Rule is one family-owned semantic check. Context must come from its trusted
// owner; it is never resolved from payload claims by this package.
type Rule struct {
	Key             Key
	RequiresContext bool
	Contextual      bool
	Check           func(Invocation) error
}

type annotation struct {
	ID     string  `json:"id"`
	Inputs []Input `json:"inputs"`
}

type contract struct {
	schema           *jsonschema.Schema
	annotations      map[string][]annotation
	raw              map[string]any
	constructionWork int
}

// Validator has immutable compiled schemas and a copied rule registry. Methods
// are safe for concurrent use if the owner-supplied rules are safe too.
type Validator struct {
	contracts    map[string]contract
	construction map[string]contract
	rules        map[Key]Rule
}

// New compiles the packaged published bundle offline. Missing semantic rules
// are allowed at construction so later family ports can use CheckSchema;
// Validate refuses each missing applicable rule.
func New(rules []Rule) (*Validator, error) {
	source, err := corpus.Open()
	if err != nil {
		return nil, failure(fault.Operational, codeContractCorpusInvalid)
	}
	return load(source, rules)
}

func failure(category fault.Category, code string) error { return fault.New(category, code, nil) }

type offline struct{}

func (offline) Load(string) (any, error) {
	return nil, errors.New("external schema retrieval forbidden")
}

func load(source fs.FS, rules []Rule) (*Validator, error) {
	publications, err := readPublications(source)
	if err != nil {
		return nil, err
	}
	validator := &Validator{contracts: map[string]contract{}, rules: map[Key]Rule{}}
	for _, publication := range publications {
		if validator.contracts[publication.ID].schema != nil {
			return nil, failure(fault.Operational, codeContractCorpusInvalid)
		}
		compiled, err := compileContract(source, publication)
		if err != nil {
			return nil, err
		}
		validator.contracts[publication.ID] = compiled
	}
	if err := validator.checkReferences(); err != nil {
		return nil, err
	}
	if err := validator.loadSDLConstruction(); err != nil {
		return nil, err
	}
	return validator.WithRules(rules)
}

// Keys returns the distinct published host-contract and invariant pairs.
// The returned slice is independent of the immutable compiled catalog.
func (v *Validator) Keys() []Key {
	if v == nil {
		return nil
	}
	known := map[Key]bool{}
	for id, contract := range v.contracts {
		for _, row := range allAnnotations(contract) {
			known[Key{id, row.ID}] = true
		}
	}
	keys := make([]Key, 0, len(known))
	for key := range known {
		keys = append(keys, key)
	}
	slices.SortFunc(keys, func(a, b Key) int {
		if c := strings.Compare(a.ContractID, b.ContractID); c != 0 {
			return c
		}
		return strings.Compare(a.InvariantID, b.InvariantID)
	})
	return keys
}

// WithRules returns a new validator with a copied registry and the same
// immutable compiled schemas. It rejects unknown, duplicate and empty rules.
func (v *Validator) WithRules(rules []Rule) (*Validator, error) {
	if v == nil {
		return nil, failure(fault.Operational, "contract-rule-registration")
	}
	known := map[Key]bool{}
	for _, key := range v.Keys() {
		known[key] = true
	}
	bound := &Validator{contracts: v.contracts, construction: v.construction, rules: map[Key]Rule{}}
	for _, rule := range rules {
		if !known[rule.Key] || rule.Check == nil || bound.rules[rule.Key].Check != nil {
			return nil, failure(fault.Operational, "contract-rule-registration")
		}
		bound.rules[rule.Key] = rule
	}
	return bound, nil
}

// CheckLocal checks the published schema and local semantic rules only.
// It omits contextual rules and makes no full-conformance or admission claim.
func (v *Validator) CheckLocal(id string, data []byte, limits ingress.Limits) error {
	root, err := v.parse(id, data, limits)
	if err != nil {
		return err
	}
	return v.semanticSource(id, root, nil, false, string(data))
}

func allAnnotations(contract contract) []annotation {
	var result []annotation
	for _, rows := range contract.annotations {
		result = append(result, rows...)
	}
	return result
}

func (v *Validator) checkReferences() error {
	for id, contract := range v.contracts {
		if err := checkProfileReference(id, contract.raw); err != nil {
			return err
		}
		for _, row := range allAnnotations(contract) {
			for _, input := range row.Inputs {
				if v.contracts[input.ContractID].schema == nil {
					return failure(fault.Operational, codeContractInvariantInvalid)
				}
			}
		}
	}
	return nil
}

func checkProfileReference(id string, root map[string]any) error {
	profile, present := root["x-raes-semantic-profile"]
	if !present {
		return nil
	}
	fields, ok := profile.(map[string]any)
	if !ok || fields["contract_id"] != id || fields["keyword"] != "x-raes-invariants" || fields[keywordRequired] != true || fields["id"] != "raes-semantic-invariants-v1" || fields["entry_schema_contract_id"] != "raes-semantic-invariants-v1" {
		return failure(fault.Operational, codeContractInvariantInvalid)
	}
	return nil
}

type publication struct {
	ID   string `json:"contract_id"`
	Path string `json:"schema_path"`
}

func readPublications(source fs.FS) ([]publication, error) {
	var manifest struct {
		Directory string `json:"entries_directory"`
	}
	if err := readJSON(source, "schema-publication-manifest.json", &manifest); err != nil {
		return nil, err
	}
	directory, ok := strings.CutPrefix(manifest.Directory, "contracts/")
	if !ok || !fs.ValidPath(directory) {
		return nil, failure(fault.Operational, codeContractCorpusInvalid)
	}
	entries, err := fs.ReadDir(source, directory)
	if err != nil {
		return nil, failure(fault.Operational, codeContractCorpusInvalid)
	}
	var result []publication
	for _, entry := range entries {
		var row publication
		if err := readJSON(source, directory+"/"+entry.Name(), &row); err != nil {
			return nil, err
		}
		if row.ID == "" || !strings.HasPrefix(row.Path, "contracts/schemas/") || !fs.ValidPath(row.Path) {
			return nil, failure(fault.Operational, codeContractCorpusInvalid)
		}
		result = append(result, row)
	}
	if len(result) == 0 {
		return nil, failure(fault.Operational, "contract-corpus-empty")
	}
	return result, nil
}

func readJSON(source fs.FS, name string, target any) error {
	data, err := fs.ReadFile(source, name)
	if err != nil {
		return failure(fault.Operational, codeContractCorpusInvalid)
	}
	if err := json.Unmarshal(data, target); err != nil {
		return failure(fault.Operational, codeContractCorpusInvalid)
	}
	return nil
}

func compileContract(source fs.FS, publication publication) (contract, error) {
	raw, err := fs.ReadFile(source, strings.TrimPrefix(publication.Path, "contracts/"))
	if err != nil {
		return contract{}, failure(fault.Operational, codeContractCorpusInvalid)
	}
	doc, err := jsonschema.UnmarshalJSON(bytes.NewReader(raw))
	if err != nil {
		return contract{}, failure(fault.Operational, codeContractSchemaInvalid)
	}
	root, ok := doc.(map[string]any)
	if !ok {
		return contract{}, failure(fault.Operational, codeContractSchemaInvalid)
	}
	annotations := map[string][]annotation{}
	if err := collect(root, "#", annotations); err != nil {
		return contract{}, err
	}
	return compileDocument(publication.ID, root, annotations)
}

func compileDocument(id string, root map[string]any, annotations map[string][]annotation) (contract, error) {
	compiler := jsonschema.NewCompiler()
	compiler.DefaultDraft(jsonschema.Draft2020)
	compiler.UseLoader(offline{})
	compiler.UseRegexpEngine(compilePattern)
	location := "urn:raes:contract:" + id
	if err := compiler.AddResource(location, root); err != nil {
		return contract{}, failure(fault.Operational, codeContractSchemaInvalid)
	}
	compiled, err := compiler.Compile(location)
	if err != nil {
		return contract{}, failure(fault.Operational, codeContractSchemaInvalid)
	}
	return contract{schema: compiled, annotations: annotations, raw: root}, nil
}

// CheckSchema validates bounded JSON bytes against the published schema only.
// Format annotations do not become assertions on this surface.
func (v *Validator) CheckSchema(id string, data []byte, limits ingress.Limits) error {
	_, err := v.parse(id, data, limits)
	return err
}

// DecodeSchema checks structure and returns a fresh transport value. It also
// checks that encoding the binding preserves every supplied JSON value.
// This result carries no semantic admission claim.
func (v *Validator) DecodeSchema(id string, data []byte, limits ingress.Limits) (any, error) {
	if err := v.CheckSchema(id, data, limits); err != nil {
		return nil, err
	}
	return decodeTransport(id, data)
}

func decodeTransport(id string, data []byte) (any, error) {
	transport, err := binding.Decode(id, data)
	if err != nil {
		return nil, failure(fault.Operational, codeContractBindingMismatch)
	}
	encoded, err := json.Marshal(transport)
	if err != nil {
		return nil, failure(fault.Operational, codeContractBindingMismatch)
	}
	original, err := canonjson.Sorted(data, false)
	if err != nil {
		return nil, err
	}
	restored, err := canonjson.Sorted(encoded, false)
	if err != nil || !bytes.Equal(original, restored) {
		return nil, failure(fault.Operational, codeContractBindingMismatch)
	}
	return transport, nil
}

func (v *Validator) parse(id string, data []byte, limits ingress.Limits) (any, error) {
	if v == nil || v.contracts[id].schema == nil {
		return nil, failure(fault.InvalidInput, "contract-unknown")
	}
	root := ingress.Object
	if v.contracts[id].raw[keywordType] == "array" {
		root = ingress.Array
	}
	value, err := ingress.Parse(data, limits, root)
	if err != nil {
		return nil, err
	}
	if !boundedNumbers(value) {
		return nil, failure(fault.InvalidInput, "contract-number-limit")
	}
	if err := v.contracts[id].schema.Validate(value); err != nil {
		return nil, failure(fault.InvalidInput, codeContractSchemaMismatch)
	}
	return value, nil
}

// Value contains admitted bytes. Its zero value is not admitted. Methods
// return copies so mutation of transport objects cannot change admission.
type Value struct {
	id   string
	data []byte
}

// ContractID returns the contract identity, or empty for a zero value.
func (v Value) ContractID() string { return v.id }

// JSON returns a copy of the admitted input.
func (v Value) JSON() []byte { return slices.Clone(v.data) }

// Transport returns a new schema-derived transport representation.
func (v Value) Transport() (any, error) {
	if v.id == "" {
		return nil, failure(fault.InvalidInput, "contract-value-uninitialized")
	}
	return binding.Decode(v.id, v.data)
}

// Validate checks structure and all applicable registered semantic rules.
func (v *Validator) Validate(id string, data []byte, limits ingress.Limits, trustedContext any) (Value, error) {
	root, err := v.parse(id, data, limits)
	if err != nil {
		return Value{}, err
	}
	if err := v.semanticSource(id, root, trustedContext, true, string(data)); err != nil {
		return Value{}, err
	}
	if _, err := decodeTransport(id, data); err != nil {
		return Value{}, failure(fault.Operational, codeContractBindingMismatch)
	}
	return Value{id, slices.Clone(data)}, nil
}

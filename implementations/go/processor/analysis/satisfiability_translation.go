package analysis

import (
	"cmp"
	"encoding/json"
	"maps"
	"regexp"
	"slices"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

const (
	unsupportedDomain = "scenario-satisfiability.unsupported-domain"
	unsupportedTarget = "scenario-satisfiability.unsupported-target"
	resourceLimit     = "scenario-satisfiability.resource-limit"
)

var variableToken = regexp.MustCompile(`\$\{((?:(?:[A-Za-z][A-Za-z0-9_-]*|__private)\.)*[A-Za-z][A-Za-z0-9_-]*)\}`)

type variableOccurrence struct {
	address, name string
	embedded      bool
}
type translationDiagnostics struct {
	items    []diagnostic.Diagnostic
	overflow bool
}

func (d *translationDiagnostics) add(code, address, message string) {
	for _, item := range d.items {
		if item.Code == code && item.Address == address {
			return
		}
	}
	if d.overflow {
		return
	}
	item := diagnostic.Diagnostic{Code: code, Domain: "scenario-satisfiability", Address: address, Message: message, Severity: severityError}
	if len(d.items) < 64 {
		d.items = append(d.items, item)
		return
	}
	d.items[63] = diagnostic.Diagnostic{Code: resourceLimit, Domain: "scenario-satisfiability", Address: "", Message: "The analysis produced more unsupported diagnostics than the evidence profile permits.", Severity: severityError}
	d.overflow = true
}
func (d *translationDiagnostics) ordered() []diagnostic.Diagnostic {
	slices.SortFunc(d.items, func(a, b diagnostic.Diagnostic) int {
		if n := cmp.Compare(a.Address, b.Address); n != 0 {
			return n
		}
		return cmp.Compare(a.Code, b.Code)
	})
	return d.items
}
func variableOccurrences(value any, address string, result *[]variableOccurrence) {
	switch v := value.(type) {
	case map[string]any:
		for _, key := range slices.Sorted(maps.Keys(v)) {
			variableOccurrences(v[key], address+"/"+jsonpointer.EscapeToken(key), result)
		}
	case []any:
		for index, item := range v {
			variableOccurrences(item, address+"/"+strconv.Itoa(index), result)
		}
	case string:
		matches := variableToken.FindAllStringSubmatch(v, -1)
		seen := map[string]bool{}
		for _, match := range matches {
			if !seen[match[1]] {
				*result = append(*result, variableOccurrence{address, match[1], v != match[0]})
				seen[match[1]] = true
			}
		}
	}
}
func stableID(prefix, value string) string {
	return prefix + ":" + strings.TrimPrefix(digest.SHA256([]byte(value)), "sha256:")
}
func translateScenario(scenario sdl.Scenario, sourceDigest string) (constraintModel, []diagnostic.Diagnostic, error) {
	raw, err := sdl.ModelBytes(scenario)
	if err != nil {
		return constraintModel{}, nil, err
	}
	payload, err := decodeObject(raw, 16<<20)
	if err != nil {
		return constraintModel{}, nil, err
	}
	variables := object(payload["variables"])
	for _, key := range []string{"variables", termImports, "module", "expansion_provenance"} {
		delete(payload, key)
	}
	occurrences := []variableOccurrence{}
	variableOccurrences(payload, "", &occurrences)
	diagnostics := &translationDiagnostics{items: []diagnostic.Diagnostic{}}
	names, symbols, err := scenarioSymbols(variables, occurrences, diagnostics)
	if err != nil {
		return constraintModel{}, nil, err
	}
	authored, err := sdl.CanonicalDigest(scenario)
	if err != nil {
		return constraintModel{}, nil, err
	}
	model := constraintModel{Profile: "raes-finite-domain-constraints/v1", Theory: "raes-finite-domain-theory/v1", Translation: "raes-sdl-authoring-translation/v1", SourceDigest: sourceDigest, AuthoredDigest: map[string]any{fieldProfile: sdlSemanticProfile, fieldAlgorithm: "sha256", "value": authored}, Symbols: []constraintSymbol{}, Clauses: []constraintClause{}}
	appendClause := func(clause constraintClause) {
		if len(model.Clauses) < 512 {
			model.Clauses = append(model.Clauses, clause)
		} else {
			diagnostics.add(resourceLimit, "", "The analysis exceeds the clause limit.")
		}
	}
	for _, name := range names {
		symbol, ok := symbols[name]
		if !ok {
			continue
		}
		model.Symbols = append(model.Symbols, symbol)
		appendClause(constraintClause{ID: stableID(termDomain, name), Kind: "declared-domain", Symbol: symbol.ID, Address: "/variables/" + jsonpointer.EscapeToken(name), Allowed: symbol.Domain})
	}
	if err = translateTargets(occurrences, symbols, appendClause, diagnostics); err != nil {
		return constraintModel{}, nil, err
	}
	slices.SortFunc(model.Symbols, func(a, b constraintSymbol) int { return cmp.Compare(a.ID, b.ID) })
	slices.SortFunc(model.Clauses, func(a, b constraintClause) int { return cmp.Compare(a.ID, b.ID) })
	return model, diagnostics.ordered(), nil
}
func translateSymbol(name string, variable map[string]any, diagnostics *translationDiagnostics) (constraintSymbol, bool, error) {
	address := "/variables/" + jsonpointer.EscapeToken(name)
	sort := text(variable[termType])
	values := array(variable["allowed_values"])
	if sort == "number" {
		diagnostics.add(unsupportedDomain, address, "The variable sort is not supported by this profile.")
		return constraintSymbol{}, false, nil
	}
	if len(values) == 0 {
		if sort != "boolean" {
			diagnostics.add(unsupportedDomain, address, "The variable requires an explicit finite allowed-values domain.")
			return constraintSymbol{}, false, nil
		}
		values = []any{false, true}
	}
	keys := map[string]any{}
	for _, value := range values {
		raw, err := canonical(value)
		if err != nil {
			return constraintSymbol{}, false, err
		}
		keys[string(raw)] = value
	}
	if len(values) > 256 || len(keys) != len(values) {
		diagnostics.add(unsupportedDomain, address, "The variable domain is invalid or exceeds its limit.")
		return constraintSymbol{}, false, nil
	}
	ordered := make([]any, 0, len(keys))
	for _, key := range slices.Sorted(maps.Keys(keys)) {
		ordered = append(ordered, keys[key])
	}
	return constraintSymbol{ID: stableID("symbol", name), Variable: name, Sort: sort, Domain: ordered}, true, nil
}
func targetDomain(address string, symbol constraintSymbol, cache map[string]bool) ([]any, error) {
	parts := jsonpointer.Tokens(address)
	switch {
	case len(parts) == 3 && parts[0] == "nodes" && (parts[2] == "os" || parts[2] == "architecture") && symbol.Sort == "string":
		return nodeTargetDomain(parts[2], symbol.Domain, cache)
	case len(parts) == 5 && parts[0] == sectionInfrastructure && parts[2] == "acls" && parts[4] == "action" && symbol.Sort == "string":
		result := []any{}
		for _, value := range symbol.Domain {
			normalized := strings.ReplaceAll(strings.ToLower(strings.TrimSpace(text(value))), "_", "-")
			if normalized == "allow" || normalized == "deny" {
				result = append(result, value)
			}
		}
		return result, nil
	case len(parts) == 3 && parts[0] == sectionInfrastructure && parts[2] == "count" && symbol.Sort == "integer":
		return countTargetDomain(symbol.Domain)
	case len(parts) == 4 && parts[0] == sectionInfrastructure && parts[2] == "properties" && parts[3] == "internal" && symbol.Sort == "boolean":
		return symbol.Domain, nil
	default:
		return nil, nil // Nil means unsupported; an empty nonnil domain means unsatisfiable.
	}
}
func countTargetDomain(domain []any) ([]any, error) {
	result := []any{}
	for _, value := range domain {
		number, ok := value.(json.Number)
		if !ok {
			return nil, invalidAnalysis()
		}
		integer, err := number.Int64()
		if err == nil && integer >= 1 {
			result = append(result, value)
		}
	}
	return result, nil
}
func nodeTargetDomain(field string, domain []any, cache map[string]bool) ([]any, error) {
	result := []any{}
	for _, value := range domain {
		key := field + "\x00" + text(value)
		valid, exists := cache[key]
		if !exists {
			var err error
			valid, err = validNodeTarget(field, value)
			if err != nil {
				return nil, err
			}
			cache[key] = valid
		}
		if valid {
			result = append(result, value)
		}
	}
	return result, nil
}
func validNodeTarget(field string, value any) (bool, error) {
	owner, err := analysisOwner()
	if err != nil {
		return false, err
	}
	node, err := admission.AdmitFragment(owner, admission.RealizationValue, map[string]any{termType: "compute", field: value}, ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 32})
	if err != nil {
		return false, err
	}
	normalized, _, err := sdl.NormalizeNodeValue(node)
	if err != nil {
		if category, ok := fault.CategoryOf(err); ok && category == fault.InvalidInput {
			return false, nil
		}
		return false, err
	}
	return !variableToken.MatchString(text(object(normalized.Document())[field])), nil
}

func scenarioSymbols(variables map[string]any, occurrences []variableOccurrence, diagnostics *translationDiagnostics) ([]string, map[string]constraintSymbol, error) {
	referenced := map[string]bool{}
	for _, occurrence := range occurrences {
		referenced[occurrence.name] = true
	}
	names := []string{}
	for name, value := range variables {
		if referenced[name] || object(value)["required"] == true {
			names = append(names, name)
		}
	}
	slices.Sort(names)
	if len(names) > 128 {
		diagnostics.add(resourceLimit, "/variables", "The analysis exceeds the symbol limit.")
		names = names[:128]
	}
	symbols := map[string]constraintSymbol{}
	for _, name := range names {
		symbol, ok, err := translateSymbol(name, object(variables[name]), diagnostics)
		if err != nil {
			return nil, nil, err
		}
		if ok {
			symbols[name] = symbol
		}
	}
	return names, symbols, nil
}

func translateTargets(occurrences []variableOccurrence, symbols map[string]constraintSymbol, appendClause func(constraintClause), diagnostics *translationDiagnostics) error {
	var err error
	cache := map[string]bool{}
	for _, occurrence := range occurrences {
		symbol, ok := symbols[occurrence.name]
		var allowed []any
		if ok && !occurrence.embedded {
			allowed, err = targetDomain(occurrence.address, symbol, cache)
			if err != nil {
				return err
			}
		}
		if allowed == nil {
			diagnostics.add(unsupportedTarget, occurrence.address, "The variable occurrence is outside the selected translation profile.")
			continue
		}
		appendClause(constraintClause{ID: stableID("target", occurrence.address), Kind: "target-domain", Symbol: symbol.ID, Address: occurrence.address, Allowed: allowed})
	}

	return nil
}

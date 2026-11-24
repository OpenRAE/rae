package admission

import (
	"encoding/json"
	"maps"
	"regexp"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/base/domain"
	"github.com/OpenRAE/rae/implementations/go/internal/base/graph"
)

func (e *Validator) envelopeRules() map[string]definition {
	return map[string]definition{"realization-envelope-canonical-semantics-valid": {check: e.envelope}}
}
func (e *Validator) envelope(i validation.Invocation) error {
	v, err := e.defaulted(termRealizationEnvelopeV1, i.Instance)
	if err != nil {
		return err
	}
	if checkErr := envelopeExpression(at(v, "expression")); checkErr != nil {
		return checkErr
	}
	if checkErr := e.envelopeConfiguration(at(v, termConfiguration)); checkErr != nil {
		return checkErr
	}
	if checkErr := e.envelopeConcerns(v); checkErr != nil {
		return checkErr
	}
	configuration := envelopeDigestConfiguration(at(v, termConfiguration))
	actual, err := envelopeConfigurationDigest(configuration)
	if err != nil {
		return err
	}
	if actual != stringAt(configuration, "configuration_digest") {
		return invalid()
	}
	expected, err := envelopeDigest(v)
	if err != nil {
		return err
	}
	return require(expected == stringAt(v, termDigest))
}

// envelopeDigestConfiguration is the material configuration projection that
// the envelope digests cover.
func envelopeDigestConfiguration(raw any) map[string]any {
	configuration := maps.Clone(object(raw))
	if at(configuration, "operating_systems") == nil {
		configuration["operating_systems"] = []any{}
	}
	if len(array(configuration["process_resource_limits"])) == 0 {
		delete(configuration, "process_resource_limits")
	}
	return configuration
}

// envelopeConfigurationDigest digests a material configuration projection
// without its own digest.
func envelopeConfigurationDigest(configuration map[string]any) (string, error) {
	content := maps.Clone(configuration)
	delete(content, "configuration_digest")
	actual, err := envelopeSortedJSON(content)
	if err != nil {
		return "", err
	}
	return digest.SHA256([]byte(actual)), nil
}

// envelopeDigest digests a defaulted envelope without its self-digest.
func envelopeDigest(v any) (string, error) {
	payload := maps.Clone(object(v))
	payload["expression"] = envelopeExpressionDigestView(at(v, "expression"))
	payload[termConfiguration] = envelopeDigestConfiguration(at(v, termConfiguration))
	delete(payload, termDigest)
	canonical, err := envelopeSortedJSON(payload)
	if err != nil {
		return "", err
	}
	return digest.SHA256([]byte(canonical)), nil
}

func envelopeExpressionDigestView(v any) any {
	expression := maps.Clone(object(v))
	domains := maps.Clone(object(expression[termDomains]))
	for name, input := range domains {
		descriptor := object(input)
		if stringAt(descriptor, termKind) != termNumericInterval {
			continue
		}
		normalized := maps.Clone(descriptor)
		normalized["lower"] = envelopeFloat(normalized["lower"])
		normalized["upper"] = envelopeFloat(normalized["upper"])
		domains[name] = normalized
	}
	expression[termDomains] = domains
	for _, name := range []string{"witness_policy", "source_ref", "contract_id", "digest"} {
		if _, supplied := expression[name]; !supplied {
			expression[name] = nil
		}
	}
	if policy := object(expression["witness_policy"]); policy != nil {
		policy = maps.Clone(policy)
		if _, supplied := policy["seed"]; !supplied {
			policy["seed"] = nil
		}
		expression["witness_policy"] = policy
	}
	return expression
}
func (e *Validator) vocabularyTerm(id, term string) bool { return e.authority.Permits(id, term) }
func (e *Validator) envelopeConfiguration(v any) error {
	if !fieldsUnique(v, "supported_node_types", "supported_os_families", "supported_content_types", "supported_account_features", "supported_domain_profiles") || len(rowSet(at(v, "process_resource_limits"), "resource")) != len(array(at(v, "process_resource_limits"))) || len(rowTupleSet(at(v, "operating_systems"), "family", "distribution")) != len(array(at(v, "operating_systems"))) {
		return invalid()
	}
	if !e.vocabularyTerm("provisioner-node-architectures", stringAt(v, termArchitecture)) {
		return invalid()
	}
	for _, entry := range array(at(v, "operating_systems")) {
		if !set(at(v, "supported_os_families"))[stringAt(entry, "family")] {
			return invalid()
		}
	}
	for _, field := range []string{"memory_mib", "vcpus"} {
		if at(v, field, "maximum") != nil && numericGreater(at(v, field, "minimum"), at(v, field, "maximum")) {
			return invalid()
		}
	}
	return nil
}
func (e *Validator) envelopeConcerns(v any) error {
	concerns := array(at(v, "concerns"))
	if len(rowSet(concerns, "concern")) != len(concerns) || len(concerns) != 12 {
		return invalid()
	}
	for _, claim := range concerns {
		if err := e.envelopeConcern(v, claim); err != nil {
			return err
		}
	}
	return nil
}

var envelopePath = regexp.MustCompile(`^[^.\[\]]+(?:\.[^.\[\]]+|\[[0-9]+\])*$`)

func envelopeExpression(v any) error {
	domains := object(at(v, termDomains))
	edges := map[string][]string{}
	if err := envelopeDomainGraph(domains, edges); err != nil {
		return err
	}
	if graph.HasCycle(edges) {
		return invalid()
	}
	if err := envelopeBindings(v, domains); err != nil {
		return err
	}
	for name, value := range object(at(v, "witness_policy", "selections")) {
		parsed, err := envelopeDomain(domains[name])
		if err != nil {
			return invalid()
		}
		ok, err := domain.In(value, parsed)
		if err != nil || !ok {
			return invalid()
		}
	}
	return nil
}
func scopeRank(v any) string {
	return strconv.Itoa(map[string]int{kindScenario: 0, "topology": 1, "app": 1, termNode: 2, "field": 3}[text(v)])
}
func envelopeBindings(v any, domains map[string]any) error {
	seen := map[string]any{}
	for _, binding := range array(at(v, termBindings)) {
		if !envelopePath.MatchString(stringAt(binding, "path")) || (stringAt(binding, "posture") == termOpen) != (at(binding, fieldDomain) == nil) {
			return invalid()
		}
		descriptor := domains[stringAt(binding, fieldDomain)]
		if at(binding, fieldDomain) != nil && descriptor == nil {
			return invalid()
		}
		if stringAt(binding, "posture") == postureExact && !singletonDomain(descriptor) {
			return invalid()
		}
		key := join(stringAt(binding, "path"), scopeRank(at(binding, "scope")))
		meaning := []any{at(binding, fieldDomain), at(binding, "posture"), defaultMember(binding, "overrideable", false)}
		if previous, ok := seen[key]; ok && !equal(previous, meaning) {
			return invalid()
		}
		seen[key] = meaning
	}
	return envelopeClosure(v)
}

func singletonDomain(v any) bool {
	switch stringAt(v, termKind) {
	case postureExact:
		return true
	case termEnum:
		return len(array(at(v, "values"))) == 1
	case typeBoolean:
		return at(v, "value") != nil
	case termNumericInterval:
		return numericEqual(at(v, "lower"), at(v, "upper"))
	case termGovernedReference:
		return len(array(at(v, "allowed_refs"))) == 1
	default:
		return false
	}
}
func envelopeDomain(v any) (domain.Domain, error) { //nolint:ireturn // The closed domain algebra has several concrete variants.
	switch stringAt(v, termKind) {
	case postureExact:
		return domain.Exact{Value: at(v, "value")}, nil
	case termEnum:
		return domain.Enumeration{Values: array(at(v, "values"))}, nil
	case typeBoolean:
		var value *bool
		if at(v, "value") != nil {
			selected := boolean(at(v, "value"))
			value = &selected
		}
		return domain.Boolean{Value: value}, nil
	case termGovernedReference:
		return domain.References{Authority: stringAt(v, termAuthority), Allowed: stringsOf(at(v, "allowed_refs"))}, nil
	case termRecord:
		fields := map[string]string{}
		for key, target := range object(at(v, termFields)) {
			fields[key] = text(target)
		}
		return domain.Record{Fields: fields, Extra: boolean(at(v, "extra"))}, nil
	case termNumericInterval:
		lower, lok := at(v, "lower").(json.Number)
		upper, uok := at(v, "upper").(json.Number)
		if !lok || !uok {
			return nil, invalid()
		}
		lo, lerr := lower.Float64()
		hi, herr := upper.Float64()
		if lerr != nil || herr != nil {
			return nil, invalid()
		}
		kind := domain.Number
		if stringAt(v, "numeric_type") == termInteger {
			kind = domain.Integer
		}
		return domain.Interval{Type: kind, Lower: lo, Upper: hi, LowerClosed: boolean(defaultMember(v, "lower_closed", true)), UpperClosed: boolean(defaultMember(v, "upper_closed", true))}, nil
	default:
		return nil, invalid()
	}
}

func envelopeDomainGraph(domains map[string]any, edges map[string][]string) error {
	for name, descriptor := range domains {
		parsed, err := envelopeDomain(descriptor)
		if err != nil || parsed.Validate() != nil {
			return invalid()
		}
		edges[name] = nil
		if stringAt(descriptor, termKind) == termRecord {
			for _, target := range object(at(descriptor, termFields)) {
				if domains[text(target)] == nil {
					return invalid()
				}
				edges[name] = append(edges[name], text(target))
			}
		}
	}
	return nil
}

func envelopeClosure(v any) error {
	closure := map[string]string{}
	for _, overlay := range array(at(v, "closure")) {
		if stringAt(overlay, "path") != "" && !envelopePath.MatchString(stringAt(overlay, "path")) {
			return invalid()
		}
		key := join(stringAt(overlay, "path"), scopeRank(at(overlay, "scope")))
		value := stringAt(overlay, "closure")
		if previous, ok := closure[key]; ok && previous != value {
			return invalid()
		}
		closure[key] = value
	}
	return nil
}

func (e *Validator) envelopeConcern(v, claim any) error {
	if !fieldsUnique(claim, "transformations") || (stringAt(claim, "disposition") == termTransformed) != (len(array(at(claim, "transformations"))) > 0) {
		return invalid()
	}
	unsupported := stringAt(claim, "disposition") == statusUnsupported
	if unsupported != (stringAt(claim, "observation_strength") == postureNone) || unsupported != (at(claim, "mechanism") == nil) {
		return invalid()
	}
	if stringAt(claim, "concern") == "compute-substrate" && at(claim, "mechanism") != nil && !e.vocabularyTerm("compute-substrates", stringAt(claim, "mechanism")) {
		return invalid()
	}
	if stringAt(claim, "concern") == "operating-system" {
		if len(array(at(v, termConfiguration, "operating_systems"))) > 0 {
			if stringAt(claim, "disposition") != "realized" || stringAt(claim, "observation_strength") != "guest-observed" {
				return invalid()
			}
		} else if !unsupported {
			return invalid()
		}
	}

	return nil
}

// Envelope identities use the reference ASCII sorted-JSON profile.
// Other legacy digest families keep their separately declared profiles.
func envelopeSortedJSON(input any) (string, error) {
	raw, err := json.Marshal(input)
	if err != nil {
		return "", invalid()
	}
	canonical, err := canonjson.Sorted(raw, true)
	if err != nil {
		return "", invalid()
	}
	return string(canonical), nil
}

// Numeric interval models construct floats even when their JSON input uses
// integer tokens. Keep that constructor step separate from canonical encoding.
func envelopeFloat(input any) any {
	number, ok := input.(json.Number)
	if !ok {
		return input
	}
	parsed, err := number.Float64()
	if err != nil {
		return input
	}
	rendered := strconv.FormatFloat(parsed, 'g', -1, 64)
	if !strings.ContainsAny(rendered, ".eE") {
		rendered += ".0"
	}
	return json.Number(rendered)
}

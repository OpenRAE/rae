package admission

import (
	"encoding/json"
	"slices"
	"strings"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

// ObservationDemandResolution contains sealed effective demands and policy conflicts.
type ObservationDemandResolution struct {
	Effective   []Fragment
	Diagnostics []diagnostic.Diagnostic
}
type observationSelector struct {
	Scope      string       `json:"semantic_scope"`
	Excluded   []string     `json:"excluded_scopes"`
	Components []string     `json:"component_refs"`
	Kind       string       `json:"data_kind"`
	Names      []string     `json:"names"`
	Windows    []string     `json:"window_refs"`
	Coverage   *string      `json:"coverage_profile"`
	MaxItems   *json.Number `json:"max_items"`
}
type observationRule struct {
	ID         string               `json:"rule_id"`
	Scope      string               `json:"scope"`
	Purpose    string               `json:"purpose"`
	Mode       *string              `json:"mode"`
	Selector   *observationSelector `json:"selector"`
	Collection *string              `json:"collection"`
	Retention  *string              `json:"retention"`
	Export     *string              `json:"export"`
	Basis      *string              `json:"basis"`
	Redaction  *string              `json:"redaction"`
	Integrity  *string              `json:"integrity"`
	Prohibited []string             `json:"prohibited_stages"`
	Required   bool                 `json:"required"`
	Authority  string               `json:"authority_ref"`
}
type observationEffective struct {
	Scope      string                `json:"scope"`
	Purpose    string                `json:"purpose"`
	Mode       string                `json:"mode"`
	Selectors  []observationSelector `json:"selectors"`
	Collection string                `json:"collection"`
	Retention  string                `json:"retention"`
	Export     string                `json:"export"`
	Basis      string                `json:"basis"`
	Redaction  *string               `json:"redaction"`
	Integrity  *string               `json:"integrity"`
	Prohibited []string              `json:"prohibited_stages"`
	Required   bool                  `json:"required"`
	Origins    map[string]string     `json:"origins"`
}
type observationNormalizer struct {
	limits      ConstraintLimits
	operations  int
	exhausted   bool
	diagnostics []diagnostic.Diagnostic
}

func (n *observationNormalizer) spend() bool {
	if n.exhausted || 1 > n.limits.MaxOperations-n.operations {
		n.exhausted = true
		return false
	}
	n.operations++
	return true
}
func observationContains(parent, child string) bool {
	return parent == child || parent == "" || strings.HasPrefix(child, parent+"/")
}
func observationDepth(scope string) int { return strings.Count(scope, "/") }
func observationAxis(rule observationRule, axis string) *string {
	switch axis {
	case "mode":
		return rule.Mode
	case termCollection:
		return rule.Collection
	case termRetention:
		return rule.Retention
	case termExport:
		return rule.Export
	case termBasis:
		return rule.Basis
	case termRedaction:
		return rule.Redaction
	case termIntegrity:
		return rule.Integrity
	}
	return nil
}
func observationRuleLess(a, b observationRule) int {
	if value := strings.Compare(a.Authority, b.Authority); value != 0 {
		return value
	}
	return strings.Compare(a.ID, b.ID)
}
func (n *observationNormalizer) conflict(scope, axis string, rules []observationRule) {
	if len(n.diagnostics) >= n.limits.MaxDiagnostics {
		return
	}
	origins := make([]string, len(rules))
	for i, rule := range rules {
		origins[i] = rule.Authority + ":" + rule.ID
	}
	slices.Sort(origins)
	address := scope
	if address == "" {
		address = "observation-demand.root"
	}
	n.diagnostics = append(n.diagnostics, diagnostic.Diagnostic{Code: "observation.authority-conflict", Domain: "observation-demand", Address: address, Severity: termError, Message: "Independent observation authorities conflict on '" + axis + "' (" + strings.Join(origins, ", ") + ")."})
}
func (n *observationNormalizer) candidates(rules []observationRule, axis string) ([]observationRule, []observationRule) {
	declared, forbidden := []observationRule{}, []observationRule{}
	mandatory := false
	depth := -1
	for _, rule := range rules {
		if !n.spend() {
			break
		}
		value := observationAxis(rule, axis)
		if value == nil || *value == "inherit" {
			continue
		}
		if *value == termForbid {
			forbidden = append(forbidden, rule)
			continue
		}
		declared = append(declared, rule)
		mandatory = mandatory || rule.Required
		depth = max(depth, observationDepth(rule.Scope))
	}
	candidates := []observationRule{}
	for _, rule := range declared {
		if mandatory && rule.Required || !mandatory && observationDepth(rule.Scope) == depth {
			candidates = append(candidates, rule)
		}
	}
	return candidates, forbidden
}
func (n *observationNormalizer) axis(rules []observationRule, axis, fallback, scope string) (string, string) {
	candidates, forbidden := n.candidates(rules, axis)
	if len(candidates) == 0 {
		origin := "root-default"
		if len(forbidden) > 0 {
			ids := []string{}
			for _, rule := range forbidden {
				ids = append(ids, rule.ID)
			}
			slices.Sort(ids)
			origin = strings.Join(ids, ",")
		}
		return fallback, origin
	}
	slices.SortFunc(candidates, observationRuleLess)
	value := *observationAxis(candidates[0], axis)
	conflict := false
	ids := []string{}
	for _, rule := range candidates {
		ids = append(ids, rule.ID)
		conflict = conflict || *observationAxis(rule, axis) != value
	}
	if conflict {
		n.conflict(scope, axis, candidates)
	}
	slices.Sort(ids)
	return value, strings.Join(ids, ",")
}
func clipObservationSelector(selector observationSelector, scope string) *observationSelector {
	var selected string
	switch {
	case observationContains(selector.Scope, scope):
		selected = scope
	case observationContains(scope, selector.Scope):
		selected = selector.Scope
	default:
		return nil
	}
	for _, excluded := range selector.Excluded {
		if observationContains(excluded, selected) {
			return nil
		}
	}
	result := selector
	if result.Components == nil {
		result.Components = []string{}
	}
	if result.Windows == nil {
		result.Windows = []string{}
	}
	result.Scope = selected
	result.Excluded = []string{}
	for _, excluded := range selector.Excluded {
		if observationContains(selected, excluded) {
			result.Excluded = append(result.Excluded, excluded)
		}
	}
	return &result
}
func observationNullable(value string) *string {
	if value == "" {
		return nil
	}
	return &value
}
func (n *observationNormalizer) effective(rules []observationRule, scope, purpose string, selected *observationRule) observationEffective {
	applicable := n.applicable(rules, scope, purpose)
	fallbackMode, fallbackBasis := observationDefaults(purpose, selected)
	mode, modeOrigin := n.axis(applicable, "mode", fallbackMode, scope)
	effectiveRules := n.effectiveRules(applicable, mode)
	selectors := observationSelectedSelectors(selected, effectiveRules, scope)
	values, origins := n.effectiveAxes(effectiveRules, observationAxisSelection{scope: scope, purpose: purpose, mode: mode, fallbackBasis: fallbackBasis, modeOrigin: modeOrigin, selected: selected, selectors: selectors})
	mode, selectors = n.lifecycle(mode, selectors, values, scope, applicable)
	prohibited, required := observationProhibitions(applicable)
	return observationEffective{Scope: scope, Purpose: purpose, Mode: mode, Selectors: selectors, Collection: values[termCollection], Retention: values[termRetention], Export: values[termExport], Basis: values[termBasis], Redaction: observationNullable(values[termRedaction]), Integrity: observationNullable(values[termIntegrity]), Prohibited: prohibited, Required: required, Origins: origins}
}

func (n *observationNormalizer) applicable(rules []observationRule, scope, purpose string) []observationRule {
	applicable := []observationRule{}
	for _, rule := range rules {
		if !n.spend() {
			break
		}
		if rule.Purpose == purpose && observationContains(rule.Scope, scope) {
			applicable = append(applicable, rule)
		}
	}
	return applicable
}

func observationDefaults(purpose string, selected *observationRule) (string, string) {
	fallbackMode, fallbackBasis := postureNone, "observed"
	if purpose == termOperational {
		fallbackMode, fallbackBasis = "operational-only", termOperational
	}
	if purpose == termRealizationDescription {
		fallbackBasis = termBackendSelected
	}
	if selected != nil && purpose != termOperational {
		fallbackMode = termSelected
	}
	return fallbackMode, fallbackBasis
}

func (n *observationNormalizer) effectiveRules(applicable []observationRule, mode string) []observationRule {
	effectiveRules := applicable
	if mode == postureNone {
		winners, _ := n.candidates(applicable, "mode")
		if len(winners) > 0 {
			slices.SortFunc(winners, observationRuleLess)
			depth := observationDepth(winners[0].Scope)
			effectiveRules = []observationRule{}
			for _, rule := range applicable {
				if observationDepth(rule.Scope) >= depth {
					effectiveRules = append(effectiveRules, rule)
				}
			}
		}
	}
	return effectiveRules
}

func observationSelectedSelectors(selected *observationRule, effectiveRules []observationRule, scope string) []observationSelector {
	selectors := []observationSelector{}
	if selected != nil && selected.Selector != nil {
		for _, rule := range effectiveRules {
			if rule.ID == selected.ID {
				if clipped := clipObservationSelector(*selected.Selector, scope); clipped != nil {
					selectors = append(selectors, *clipped)
				}
				break
			}
		}
	}
	return selectors
}

type observationAxisSelection struct {
	scope, purpose, mode, fallbackBasis, modeOrigin string
	selected                                        *observationRule
	selectors                                       []observationSelector
}

func (n *observationNormalizer) effectiveAxes(effectiveRules []observationRule, selection observationAxisSelection) (map[string]string, map[string]string) {
	collectionDefault := termDisable
	if selection.purpose != termRealizationDescription && (selection.mode == termSelected || selection.mode == "exhaustive" || selection.mode == "operational-only") && len(selection.selectors) > 0 {
		collectionDefault = termRequire
	}
	origins := map[string]string{"mode": selection.modeOrigin}
	if selection.selected != nil {
		origins["selector"], origins["authority"] = selection.selected.ID, selection.selected.Authority
	}
	values := map[string]string{}
	for _, axis := range []string{termCollection, termRetention, termExport, termBasis, termRedaction, termIntegrity} {
		fallback := ""
		switch axis {
		case termCollection:
			fallback = collectionDefault
		case termRetention, termExport:
			fallback = termDisable
		case termBasis:
			fallback = selection.fallbackBasis
		}
		values[axis], origins[axis] = n.axis(effectiveRules, axis, fallback, selection.scope)
	}
	return values, origins
}

func (n *observationNormalizer) lifecycle(mode string, selectors []observationSelector, values map[string]string, scope string, applicable []observationRule) (string, []observationSelector) {
	disabled := func() {
		values[termCollection], values[termRetention], values[termExport] = termDisable, termDisable, termDisable
	}
	switch {
	case mode == postureNone:
		if len(selectors) > 0 || values[termCollection] == termRequire || values[termRetention] == termRequire || values[termExport] == termRequire {
			n.conflict(scope, "mode/lifecycle", applicable)
		}
		selectors = []observationSelector{}
		disabled()
	case (mode == termSelected || mode == "exhaustive") && len(selectors) == 0:
		n.conflict(scope, "mode/selectors", applicable)
		mode = postureNone
		disabled()
	case (values[termRetention] == termRequire || values[termExport] == termRequire) && values[termCollection] != termRequire:
		n.conflict(scope, "collection/lifecycle", applicable)
		disabled()
	}
	return mode, selectors
}

func observationProhibitions(applicable []observationRule) ([]string, bool) {
	prohibited := []string{}
	required := false
	for _, rule := range applicable {
		required = required || rule.Required
		prohibited = append(prohibited, rule.Prohibited...)
		for _, axis := range []string{termCollection, termRetention, termExport} {
			if v := observationAxis(rule, axis); v != nil && *v == termForbid {
				prohibited = append(prohibited, axis)
			}
		}
	}
	slices.Sort(prohibited)
	prohibited = slices.Compact(prohibited)
	return prohibited, required
}

func observationRuleApplies(rule, selected observationRule) bool {
	if rule.ID == selected.ID {
		return true
	}
	inherited := rule.Selector == nil || !rule.Required && rule.Scope != selected.Scope && observationContains(rule.Scope, selected.Scope)
	independent := rule.Selector == nil && (rule.Required || len(rule.Prohibited) > 0 || rule.Collection != nil && *rule.Collection == termForbid || rule.Retention != nil && *rule.Retention == termForbid || rule.Export != nil && *rule.Export == termForbid)
	return rule.Authority == selected.Authority && inherited || independent
}
func (n *observationNormalizer) scope(rules []observationRule, scope, purpose string) []observationEffective {
	applicable := n.applicable(rules, scope, purpose)
	selected := observationSelectedRules(applicable, scope)
	if len(selected) == 0 {
		selectorless := []observationRule{}
		for _, rule := range applicable {
			if rule.Selector == nil {
				selectorless = append(selectorless, rule)
			}
		}
		return []observationEffective{n.effective(selectorless, scope, purpose, nil)}
	}
	effective, policies := []observationEffective{}, [][]observationRule{}
	for _, chosen := range selected {
		policy := n.selectedPolicy(applicable, chosen)
		policies = append(policies, policy)
		effective = append(effective, n.effective(policy, scope, purpose, &chosen))
	}
	n.scopeConflicts(effective, policies, scope, selected)
	return effective
}
func observationSelectedRules(applicable []observationRule, scope string) []observationRule {
	depths := map[string]int{}
	for _, rule := range applicable {
		if rule.Selector != nil && !rule.Required {
			depths[rule.Authority] = max(depths[rule.Authority], observationDepth(rule.Scope))
		}
	}
	selected := []observationRule{}
	for _, rule := range applicable {
		if rule.Selector != nil && (rule.Required || observationDepth(rule.Scope) == depths[rule.Authority]) && clipObservationSelector(*rule.Selector, scope) != nil {
			selected = append(selected, rule)
		}
	}
	slices.SortFunc(selected, observationRuleLess)
	return selected
}

func (n *observationNormalizer) selectedPolicy(applicable []observationRule, chosen observationRule) []observationRule {
	policy := []observationRule{}
	for _, rule := range applicable {
		if !n.spend() {
			break
		}
		if observationRuleApplies(rule, chosen) {
			policy = append(policy, rule)
		}
	}
	return policy
}

func (n *observationNormalizer) scopeConflicts(effective []observationEffective, policies [][]observationRule, scope string, selected []observationRule) {
	for i := range effective {
		for j := i + 1; j < len(effective); j++ {
			if !n.spend() {
				break
			}
			if n.overlapConflict(effective[i], effective[j], policies[i], policies[j]) {
				n.conflict(scope, "overlapping-selector/lifecycle", selected)
			}
		}
	}
}

func observationSelectorOverlap(a, b observationSelector) bool {
	if a.Kind != b.Kind || !observationIntersects(a.Names, b.Names) {
		return false
	}
	if len(a.Components) > 0 && len(b.Components) > 0 && !observationIntersects(a.Components, b.Components) {
		return false
	}
	return clipObservationSelector(a, b.Scope) != nil && clipObservationSelector(b, a.Scope) != nil
}
func observationIntersects(a, b []string) bool {
	for _, value := range a {
		if slices.Contains(b, value) {
			return true
		}
	}
	return false
}
func (n *observationNormalizer) overlapConflict(a, b observationEffective, left, right []observationRule) bool {
	if !n.selectorsOverlap(a.Selectors, b.Selectors) {
		return false
	}
	for _, axis := range []string{termCollection, termRetention, termExport} {
		if n.overlapAxisConflict(a, b, left, right, axis) {
			return true
		}
	}
	return false
}

func (n *observationNormalizer) selectorsOverlap(left, right []observationSelector) bool {
	overlaps := false
	for _, one := range left {
		for _, two := range right {
			if !n.spend() {
				return false
			}
			if observationSelectorOverlap(one, two) {
				overlaps = true
				break
			}
		}
	}
	return overlaps
}

func (n *observationNormalizer) overlapAxisConflict(a, b observationEffective, left, right []observationRule, axis string) bool {
	av, bv := a.Collection, b.Collection
	if axis == termRetention {
		av, bv = a.Retention, b.Retention
	}
	if axis == termExport {
		av, bv = a.Export, b.Export
	}
	if av == termRequire && slices.Contains(b.Prohibited, axis) || bv == termRequire && slices.Contains(a.Prohibited, axis) {
		return true
	}
	if a.Required && b.Required && av != bv {
		rules := right
		if av == termDisable {
			rules = left
		}
		declared, _ := n.candidates(rules, axis)
		if len(declared) > 0 {
			return true
		}
	}
	return false
}

func (n *observationNormalizer) partition(demands []observationEffective) []observationEffective {
	output := []observationEffective{}
	for i, demand := range demands {
		selectors := []observationSelector{}
		for _, selector := range demand.Selectors {
			if selected, owned := n.partitionSelector(demands, i, selector); !owned {
				selectors = append(selectors, selected)
			}
		}
		if len(selectors) == 0 && len(demand.Selectors) > 0 {
			continue
		}
		demand.Selectors = selectors
		output = append(output, demand)
	}
	return output
}

func (n *observationNormalizer) partitionSelector(demands []observationEffective, index int, selector observationSelector) (observationSelector, bool) {
	demand := demands[index]
	excluded := slices.Clone(selector.Excluded)
	for j, candidate := range demands {
		if !n.spend() {
			break
		}
		if candidate.Purpose != demand.Purpose {
			continue
		}
		if candidate.Scope != demand.Scope && candidate.Scope == selector.Scope {
			return selector, true
		}
		if index != j && candidate.Scope != selector.Scope && observationContains(selector.Scope, candidate.Scope) {
			excluded = append(excluded, candidate.Scope)
		}
	}
	slices.Sort(excluded)
	selector.Excluded = slices.Compact(excluded)
	return selector, false
}

// NormalizeObservationDemands resolves policy without collecting data or
// interpreting capability as authority. Each result has exact native ownership.
func NormalizeObservationDemands(v *Validator, document binding.ObservationDemandV1, targetScopes []string, limits ConstraintLimits) (ObservationDemandResolution, error) {
	result := ObservationDemandResolution{Effective: []Fragment{}, Diagnostics: []diagnostic.Diagnostic{}}
	if v == nil || limits.Validate() != nil || len(targetScopes) == 0 || len(targetScopes) > limits.MaxMembers {
		return result, fragmentInvalid()
	}
	if !observationTargetScopesValid(targetScopes, limits) {
		return result, fragmentInvalid()
	}
	wireLimits := ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}
	if err := CheckTransport(document, wireLimits); err != nil {
		return result, err
	}
	raw, err := json.Marshal(document)
	if err != nil {
		return result, fragmentInvalid()
	}
	if err := v.CheckPortable("observation-demand-v1", raw, wireLimits); err != nil {
		return result, err
	}
	var wire struct {
		Rules []observationRule `json:"rules"`
	}
	if json.Unmarshal(raw, &wire) != nil || len(wire.Rules) > limits.MaxNodes {
		return result, fragmentInvalid()
	}
	purposes := []string{"experimental"}
	for i := range wire.Rules {
		rule := &wire.Rules[i]
		if rule.Authority == "" {
			rule.Authority = termAuthor
		}
		purposes = append(purposes, rule.Purpose)
	}
	slices.Sort(purposes)
	purposes = slices.Compact(purposes)
	normalizer := observationNormalizer{limits: limits, diagnostics: []diagnostic.Diagnostic{}}
	effective := normalizer.compile(wire.Rules, targetScopes, purposes)
	if normalizer.exhausted || effective == nil {
		return result, fragmentInvalid()
	}
	effective = normalizer.partition(effective)
	if normalizer.exhausted {
		return result, fragmentInvalid()
	}
	return normalizer.project(v, effective, wireLimits)
}

func observationTargetScopesValid(targetScopes []string, limits ConstraintLimits) bool {
	seen := map[string]bool{}
	for _, scope := range targetScopes {
		if seen[scope] || !utf8.ValidString(scope) || len(scope) > limits.MaxScalarBytes || scope != jsonpointer.FromTokens(jsonpointer.Tokens(scope)) {
			return false
		}
		seen[scope] = true
	}
	return true
}

func (n *observationNormalizer) compile(rules []observationRule, targetScopes, purposes []string) []observationEffective {
	effective := []observationEffective{}
	for _, scope := range targetScopes {
		for _, purpose := range purposes {
			if !n.purposeApplies(rules, scope, purpose) {
				continue
			}
			effective = append(effective, n.scope(rules, scope, purpose)...)
			if len(effective) > n.limits.MaxNodes || n.exhausted {
				return nil
			}
		}
	}
	return effective
}

func (n *observationNormalizer) purposeApplies(rules []observationRule, scope, purpose string) bool {
	if purpose == "experimental" {
		return true
	}
	for _, rule := range rules {
		if !n.spend() {
			break
		}
		if rule.Purpose == purpose && observationContains(rule.Scope, scope) {
			return true
		}
	}
	return false
}

func (n *observationNormalizer) project(v *Validator, effective []observationEffective, wireLimits ingress.Limits) (ObservationDemandResolution, error) {
	result := ObservationDemandResolution{Effective: []Fragment{}, Diagnostics: []diagnostic.Diagnostic{}}
	for _, demand := range effective {
		encoded, err := json.Marshal(demand)
		if err != nil {
			return result, fragmentInvalid()
		}
		var value any
		if json.Unmarshal(encoded, &value) != nil {
			return result, fragmentInvalid()
		}
		fragment, err := AdmitFragment(v, EffectiveObservationDemand, value, wireLimits)
		if err != nil {
			return result, err
		}
		result.Effective = append(result.Effective, fragment)
	}
	result.Diagnostics = n.diagnostics
	return result, nil
}

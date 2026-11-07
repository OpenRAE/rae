package admission

import (
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func (e *Validator) injectDocument(id string, data []byte) (any, error) {
	v, err := e.contextDocument(id, data)
	if err != nil {
		return nil, err
	}
	return e.defaulted(id, v)
}
func (e *Validator) injectRetry(i validation.Invocation) error {
	c, ok := i.Context.(InjectRetryContext)
	if !ok {
		return contextRequired()
	}
	occurrence, err := e.injectDocument(contractInjectOccurrence, c.InjectOccurrence())
	if err != nil {
		return err
	}
	request, err := e.defaulted("inject-trigger-request-v1", i.Instance)
	if err != nil {
		return err
	}
	if c.ActorID() != stringAt(occurrence, termAdmission, "actor_id") || !equal(at(request, "request_key"), at(occurrence, "request", "request_key")) {
		return invalid()
	}
	return require(equal(request, at(occurrence, "request")))
}
func (e *Validator) injectClaims(i validation.Invocation) error {
	c, ok := i.Context.(InjectClaimsContext)
	if !ok {
		return contextRequired()
	}
	raw := c.InjectClaims()
	if len(raw) > 1024 {
		return invalid()
	}
	claims := make([]any, 0, len(raw))
	for _, data := range raw {
		claim, err := e.injectDocument(contractInjectOccurrence, data)
		if err != nil {
			return err
		}
		claims = append(claims, claim)
	}
	if len(claims) > 0 {
		found := false
		current, err := e.defaulted(contractInjectOccurrence, i.Instance)
		if err != nil {
			return err
		}
		for _, claim := range claims {
			if equal(current, claim) {
				found = true
			}
		}
		if !found {
			return invalid()
		}
	}
	return injectUniqueClaims(claims)
}
func injectUniqueClaims(claims []any) error {
	sets := map[string]map[string]bool{}
	store := ""
	for _, claim := range claims {
		current := join(stringAt(claim, "request", "target_scope"), stringAt(claim, "request", "run_scope"))
		if store != "" && store != current {
			return invalid()
		}
		store = current
		position, err := jsonDigest(at(claim, termOrder, "position"))
		if err != nil {
			return err
		}
		keys := map[string]string{
			termRetry:    join(stringAt(claim, termAdmission, "actor_id"), stringAt(claim, termAdmission, "operation_kind"), stringAt(claim, "request", "request_key")),
			"occurrence": stringAt(claim, "request", "occurrence_id"), "operation": stringAt(claim, "operation_id"), "position": position, "predecessor": stringAt(claim, termOrder, "predecessor"),
		}
		if stringAt(claim, "request", "placement", termKind) == placementSchedule {
			keys["slot"] = stringAt(claim, "request", "placement", "slot")
		}
		if err := injectClaimKeys(sets, keys); err != nil {
			return err
		}
	}
	return nil
}

func (e *Validator) injectSources(c InjectOutcomeContext) (any, any, error) {
	occurrence, err := e.injectDocument(contractInjectOccurrence, c.InjectOccurrence())
	if err != nil {
		return nil, nil, err
	}
	request, err := e.backendDocument(termBackendOperationRequestV1, c.OperationRequest())
	if err != nil {
		return nil, nil, err
	}
	return occurrence, request, nil
}
func (e *Validator) injectOutcome(i validation.Invocation) error {
	c, ok := i.Context.(InjectOutcomeContext)
	if !ok {
		return contextRequired()
	}
	occurrence, request, err := e.injectSources(c)
	if err != nil {
		return err
	}
	outcome, err := e.defaulted(termInjectOccurrenceOutcomeV1, i.Instance)
	if err != nil {
		return err
	}
	return injectOutcomeJoin(occurrence, request, outcome)
}
func injectReference(occurrence any) (any, error) {
	digest, err := jsonDigest(occurrence)
	if err != nil {
		return nil, err
	}
	return map[string]any{termContractID: contractInjectOccurrence, termArtifactID: at(occurrence, "request", "occurrence_id"), termDigest: digest}, nil
}
func injectInvocation(occurrence, request any) error {
	ref, err := injectReference(occurrence)
	if err != nil {
		return err
	}
	if !equal(ref, at(request, "command")) || !equal(at(request, "binding", "operation_id"), at(occurrence, "operation_id")) || !equal(at(request, "binding", "context"), at(occurrence, termAdmission)) {
		return invalid()
	}
	if err := injectRequirements(occurrence, request); err != nil {
		return err
	}
	return injectInvocationScope(occurrence, request)
}

func injectOutcomeJoin(occurrence, request, outcome any) error {
	if err := injectInvocation(occurrence, request); err != nil {
		return err
	}
	if err := backendResponseJoin(request, at(outcome, "response"), nil); err != nil {
		return err
	}
	if !equal(at(outcome, "occurrence"), at(request, "command")) {
		return invalid()
	}
	bindings := make([]any, 0, len(array(at(outcome, termBindings))))
	for _, row := range array(at(outcome, termBindings)) {
		bindings = append(bindings, at(row, "binding"))
		if stringAt(request, "binding", "effect_scope", termKind) == scopeResources && !subset(stringsOf(at(row, termEffects, "residual_scope")), set(at(request, "binding", "effect_scope", "addresses"))) {
			return invalid()
		}
	}
	return require(equal(bindings, at(occurrence, "request", termBindings)))
}
func (e *Validator) injectCorrelation(i validation.Invocation) error {
	c, ok := i.Context.(InjectCorrelationContext)
	if !ok {
		return contextRequired()
	}
	occurrence, request, err := e.injectSources(c)
	if err != nil {
		return err
	}
	outcome, err := e.injectDocument(termInjectOccurrenceOutcomeV1, c.InjectOutcome())
	if err != nil {
		return err
	}
	if checkErr := injectOutcomeJoin(occurrence, request, outcome); checkErr != nil {
		return checkErr
	}
	message := at(outcome, "response", "message")
	if stringAt(message, termKind) != messageOutcome || stringAt(message, "proposed_state") != outcomeSucceeded || at(message, termResult) == nil {
		return invalid()
	}
	digest, err := jsonDigest(outcome)
	if err != nil {
		return err
	}
	expected := map[string]any{"occurrence": at(outcome, "occurrence"), messageOutcome: map[string]any{termContractID: termInjectOccurrenceOutcomeV1, termArtifactID: at(occurrence, "request", "occurrence_id"), termDigest: digest}, termResult: at(message, termResult), termSchemaVersion: "inject-occurrence-correlation/v1"}
	actual, err := e.defaulted("inject-occurrence-correlation-v1", i.Instance)
	if err != nil {
		return err
	}
	return require(equal(actual, expected))
}

func injectCorrelationModel(v any) error {
	return require(stringAt(v, "occurrence", "contract_id") == contractInjectOccurrence && stringAt(v, "outcome", "contract_id") == termInjectOccurrenceOutcomeV1 && equal(at(v, "occurrence", "artifact_id"), at(v, "outcome", "artifact_id")))
}

func injectRequirements(occurrence, request any) error {
	for _, requirement := range array(at(occurrence, "evidence_requirements")) {
		found := false
		for _, selected := range array(at(request, "requirement_refs")) {
			if equal(requirement, selected) {
				found = true
			}
		}
		if !found {
			return invalid()
		}
	}
	return nil
}

func injectClaimKeys(sets map[string]map[string]bool, keys map[string]string) error {
	for name, key := range keys {
		if sets[name] == nil {
			sets[name] = map[string]bool{}
		}
		if sets[name][key] {
			return invalid()
		}
		sets[name][key] = true
	}
	return nil
}

func injectInvocationScope(occurrence, request any) error {
	ids := injectIdentities(occurrence)
	for _, field := range []string{termAttemptID, "invocation_id"} {
		for _, id := range ids {
			if stringAt(request, "binding", field) == id {
				return invalid()
			}
		}
	}
	if stringAt(request, "binding", "effect_scope", termKind) == scopeResources {
		addresses := set(at(request, "binding", "effect_scope", "addresses"))
		for _, binding := range array(at(occurrence, "request", termBindings)) {
			if !addresses[stringAt(binding, "binding")] {
				return invalid()
			}
		}
	}
	return nil
}

package authoring

import (
	"bytes"
	"encoding/json"
	"maps"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

const renameProfile = "rename-sdl-declaration/v1"
const removeProfile = "remove-sdl-declaration/v1"

type transformationRequest struct {
	Operation string `json:"operation_profile"`
	Request   struct {
		Target string `json:"target_address"`
		Name   string `json:"new_local_name"`
	} `json:"request"`
	Policy struct {
		Losses []string `json:"allowed_loss_kinds"`
	} `json:"policy"`
	Bindings []json.RawMessage `json:"binding_documents"`
}
type transformation struct {
	parser                                       *Parser
	source                                       *Document
	request                                      transformationRequest
	sourceDigest, policyDigest, derivationDigest string
	section, old, next, after                    string
	declaration                                  declaration
}

// Transform atomically applies an exact declaration request. The result bytes
// contain its published report and transformed linked binding documents.
func (p *Parser) Transform(document *Document, request []byte) (*Document, []byte, error) {
	if !document.Validated() || document.contract != authoringContract && document.contract != expandedContract {
		return nil, nil, invalid()
	}
	operation, err := p.newTransformation(document, request)
	if err != nil {
		return nil, nil, err
	}
	if result := operation.selectTarget(); result != nil {
		return operation.finish(nil, result, nil)
	}
	if operation.request.Operation == removeProfile {
		return operation.remove()
	}
	return operation.rename()
}
func (p *Parser) newTransformation(document *Document, raw []byte) (*transformation, error) {
	request, err := p.transformationRequest(raw)
	if err != nil {
		return nil, err
	}
	if document.expanded != nil {
		document = document.expanded
	}
	source, _, err := p.Validate(document)
	if err != nil {
		return nil, err
	}
	sourceDigest, err := source.CanonicalDigest()
	if err != nil {
		return nil, err
	}
	losses := request.Policy.Losses
	if losses == nil {
		losses = []string{}
	}
	policyDigest, err := jsonIdentity(map[string]any{termAllowedLossKinds: losses})
	if err != nil {
		return nil, err
	}
	requestPayload := map[string]any{"target_address": request.Request.Target}
	if request.Operation == renameProfile {
		requestPayload["new_local_name"] = request.Request.Name
	}
	derivation, err := jsonIdentity(map[string]any{termOperationProfile: request.Operation, termPolicyDigest: policyDigest, "request": requestPayload, termSourceDigest: sourceDigest})
	if err != nil {
		return nil, err
	}
	return &transformation{parser: p, source: source, request: request, sourceDigest: sourceDigest, policyDigest: policyDigest, derivationDigest: derivation}, nil
}
func (p *Parser) transformationRequest(raw []byte) (transformationRequest, error) {
	decoded, err := ingress.Parse(raw, ingress.Limits{MaxBytes: int(p.limits.MaxInputBytes), MaxDepth: p.limits.MaxDepth}, ingress.Object)
	if err != nil || !closed(object(decoded), []string{termOperationProfile, "request"}, []string{policyField, "binding_documents"}) {
		return transformationRequest{}, invalid()
	}
	var request transformationRequest
	if json.Unmarshal(raw, &request) != nil {
		return transformationRequest{}, invalid()
	}
	if request.Operation != renameProfile && request.Operation != removeProfile {
		return transformationRequest{}, invalid()
	}
	required := []string{"target_address"}
	if request.Operation == renameProfile {
		required = append(required, "new_local_name")
	}
	if !closed(object(object(decoded)["request"]), required, nil) || request.Request.Target == "" || len(request.Request.Target) > 4096 {
		return transformationRequest{}, invalid()
	}
	if request.Operation == renameProfile && !portableIdentifier(request.Request.Name) {
		return transformationRequest{}, invalid()
	}
	if policy, present := object(decoded)[policyField]; present && !closed(object(policy), nil, []string{termAllowedLossKinds}) {
		return transformationRequest{}, invalid()
	}
	if !request.validPolicy() {
		return transformationRequest{}, invalid()
	}
	return request, nil
}
func (request transformationRequest) validPolicy() bool {
	if !slices.IsSorted(request.Policy.Losses) || len(slices.Compact(slices.Clone(request.Policy.Losses))) != len(request.Policy.Losses) {
		return false
	}
	for _, kind := range request.Policy.Losses {
		if kind != termDeclarationRemoved && kind != termSemanticOmission {
			return false
		}
	}
	if request.Operation == renameProfile && len(request.Policy.Losses) > 0 {
		return false
	}
	return true
}
func portableIdentifier(value string) bool {
	if len(value) == 0 || len(value) > 64 {
		return false
	}
	return strings.Trim(value, "abcdefghijklmnopqrstuvwxyz0123456789_-") == "" && value[0] != '_' && value[0] != '-'
}
func jsonIdentity(value any) (string, error) {
	raw, err := json.Marshal(value)
	if err != nil {
		return "", invalid()
	}
	canonical, err := canonjson.JCS(raw)
	if err != nil {
		return "", err
	}
	return digest.SHA256(canonical), nil
}
func (t *transformation) selectTarget() map[string]any {
	address := t.request.Request.Target
	declaration, present := t.source.semantic.index.declarations[address]
	section, key, qualified := strings.Cut(address, ".")
	if !present || !qualified || !slices.Contains(declarationSections(), section) || len(declaration.tokens) != 2 || declaration.tokens[0] != section || declaration.tokens[1] != key {
		return t.refused("target-not-exact", "The request target is not an exact supported declaration address.", []string{termSourceAdmitted}, false, false)
	}
	t.section, t.old, t.declaration = section, key, declaration
	if t.request.Operation == removeProfile {
		return nil
	}
	if section == nodesSection && len(t.request.Request.Name) > 35 {
		return t.refused("target-unsupported", "The requested replacement is outside the declaration's supported identity boundary.", []string{termSourceAdmitted, termTargetExact}, true, false)
	}
	prefix := ""
	if index := strings.LastIndex(key, "."); index >= 0 {
		prefix = key[:index+1]
	}
	t.next = prefix + t.request.Request.Name
	t.after = section + "." + t.next
	if _, collision := t.source.semantic.index.declarations[t.after]; collision && t.after != address {
		return t.refused("identity-collision", "The requested replacement collides with an existing canonical declaration.", []string{termSourceAdmitted, termTargetExact, termTargetSupported}, true, false)
	}
	return nil
}
func (t *transformation) rename() (*Document, []byte, error) {
	candidate, err := t.candidate(t.source, t.old, t.next, false)
	if err != nil {
		return t.finish(nil, t.refused(termTargetInvalid, "The complete transformed candidate failed structural or semantic admission.", []string{termSourceAdmitted, termTargetExact, termTargetInjective, termTargetSupported}, true, false), nil)
	}
	bindings, err := t.retargetBindings(candidate)
	if err != nil {
		return t.finish(nil, t.refused("linked-artifact-stale", "A supplied linked artifact does not resolve against the exact source and target identities.", []string{termSourceAdmitted, termTargetExact, termTargetInjective, termTargetSupported}, true, false), nil)
	}
	if !t.roundTrip(candidate) {
		return t.finish(nil, t.refused("preservation-failed", "The transformed candidate did not satisfy the identity-transport round-trip relation.", []string{termLinkedArtifactsCurrent, termSourceAdmitted, termTargetAdmitted, termTargetExact, termTargetInjective, termTargetSupported}, true, false), nil)
	}
	report := t.success(candidate, []string{termLinkedArtifactsCurrent, termSourceAdmitted, termTargetExact, termTargetInjective, termTargetSupported}, []string{"identity-map-bijective", "linked-artifacts-retargeted", "round-trip-canonical-identity", termTargetAdmitted})
	report[termIdentityMap] = []any{map[string]any{"declaration_kind": t.declaration.collisionKind, "before": t.request.Request.Target, "after": t.after}}
	return t.finish(candidate, report, bindings)
}
func (t *transformation) remove() (*Document, []byte, error) {
	passed := []string{termSourceAdmitted, termTargetExact}
	if !slices.Contains(t.request.Policy.Losses, termDeclarationRemoved) {
		return t.finish(nil, t.refused("loss-not-authorized", "Declaration removal requires explicit authorization of its exact loss kind.", passed, true, true), nil)
	}
	passed = append(passed, termLossAuthorized)
	if len(t.request.Bindings) > 0 {
		return t.finish(nil, t.refused("linked-artifact-unsupported", "Declaration removal cannot silently discard or retarget supplied concept bindings.", passed, true, true), nil)
	}
	candidate, err := t.candidate(t.source, t.old, "", true)
	if err != nil {
		return t.finish(nil, t.refused(termTargetInvalid, "The complete transformed candidate failed structural or semantic admission.", passed, true, true), nil)
	}
	report := t.success(candidate, []string{termLossAuthorized, termSourceAdmitted, termTargetExact}, []string{termTargetAdmitted})
	report[termLosses] = []any{t.loss("warning")}
	return t.finish(candidate, report, nil)
}
func (t *transformation) candidate(source *Document, old, next string, remove bool) (*Document, error) {
	decoded, err := ingress.Parse(source.JSON(), modelLimits(source.data), ingress.Object)
	if err != nil {
		return nil, err
	}
	payload := object(decoded)
	if remove {
		delete(object(payload[t.section]), old)
	} else {
		if err = t.renamePayload(payload, old, next); err != nil {
			return nil, err
		}
	}
	rewriteTransformationExports(payload, t.section, old, next, remove)
	if source.contract == expandedContract {
		changes := provenancePathChanges{}
		changes.declaration(t.section, old, next, remove)
		if t.section == nodesSection {
			changes.declaration(infrastructureField, old, next, remove)
		}
		reconcileProvenancePaths(payload, changes)
		return t.parser.rebuildFamily(payload, source)
	}
	raw, err := json.Marshal(payload)
	if err != nil {
		return nil, invalid()
	}
	constructed, err := t.parser.Decode(Request{Source: raw, Name: source.sourceName})
	if err != nil {
		return nil, err
	}
	admitted, _, err := t.parser.Validate(constructed)
	return admitted, err
}
func (t *transformation) renamePayload(payload map[string]any, old, next string) error {
	symbols := identitySymbols(payload)
	symbols[t.section][old] = next
	oldAddress, newAddress := t.section+"."+old, t.section+"."+next
	for alias, target := range symbols[termNamed] {
		switch {
		case target == old:
			symbols[termNamed][alias] = next
		case target == oldAddress:
			symbols[termNamed][alias] = newAddress
		case strings.HasPrefix(target, oldAddress+"."):
			symbols[termNamed][alias] = newAddress + strings.TrimPrefix(target, oldAddress)
		}
	}
	symbols[termNamed][old] = next
	symbols[termNamed][oldAddress] = newAddress
	addNestedSymbols(payload, symbols)
	if err := rewriteOwnedReferencesWithBudget(payload, symbols, &copyBudget{remaining: t.parser.limits.MaxComposedBytes}); err != nil {
		return err
	}
	if err := rewritePolicyReferences(payload, symbols, ""); err != nil {
		return err
	}
	if err := rewriteDeclarationKeys(payload, symbols); err != nil {
		return err
	}
	return nil
}
func identitySymbols(value map[string]any) importSymbols {
	symbols := importSymbols{}
	for _, section := range declarationSections() {
		symbols[section] = map[string]string{}
		for name := range object(value[section]) {
			symbols[section][name] = name
		}
	}
	entities := map[string]bool{}
	collectEntityNames(object(value[entitiesField]), "", entities)
	for name := range entities {
		symbols[entitiesField][name] = name
	}
	symbols[forwardingSection] = map[string]string{}
	for _, item := range array(value[forwardingSection]) {
		name := text(object(item)[termForwardingAgentID])
		symbols[forwardingSection][name] = name
	}
	completeSymbols(value, symbols)
	return symbols
}
func rewriteTransformationExports(payload map[string]any, section, old, next string, remove bool) {
	exports := object(object(payload["module"])["exports"])
	if values, present := exports[section]; present {
		result := []any{}
		for _, name := range array(values) {
			if name != old {
				result = append(result, name)
			} else if !remove {
				result = append(result, next)
			}
		}
		exports[section] = result
	}
}
func (t *transformation) roundTrip(candidate *Document) bool {
	if _, present := candidate.semantic.index.declarations[t.request.Request.Target]; present {
		return false
	}
	declaration, present := candidate.semantic.index.declarations[t.after]
	if !present || declaration.collisionKind != t.declaration.collisionKind || len(candidate.semantic.index.declarations) != len(t.source.semantic.index.declarations) {
		return false
	}
	reversed, err := t.candidate(candidate, t.next, t.old, false)
	if err != nil {
		return false
	}
	before, err := t.source.CanonicalBytes()
	if err != nil {
		return false
	}
	after, err := reversed.CanonicalBytes()
	return err == nil && bytes.Equal(before, after)
}
func (t *transformation) finish(output *Document, report map[string]any, bindings []any) (*Document, []byte, error) {
	return t.parser.operationResult(output, report, bindings)
}
func (p *Parser) operationResult(output *Document, report map[string]any, bindings []any) (*Document, []byte, error) {
	raw, err := json.Marshal(report)
	if err != nil {
		return nil, nil, invalid()
	}
	if err = p.models.CheckPortable("artifact-transformation-report-v1", raw, modelLimits(raw)); err != nil {
		return nil, nil, err
	}
	if bindings == nil {
		bindings = []any{}
	}
	envelope, err := json.Marshal(map[string]any{"report": report, "binding_documents": bindings})
	return output, envelope, err
}
func (t *transformation) baseReport() map[string]any {
	profile, outcome, limitation := "sdl-declaration-identity-transport/v1", termFailed, "Finite verification does not establish behavioral equivalence."
	if t.request.Operation == removeProfile {
		profile, outcome, limitation = "explicit-loss-accounting/v1", termNotApplicable, "Removal does not preserve the selected declaration."
	}
	return map[string]any{termSchemaVersion: termArtifactTransformationReportV1, termOperationProfile: t.request.Operation, termStatus: termRefused, termArtifactKind: termSdlAuthoring, termSourceProfile: termSdlAuthoringInputV1, termTargetProfile: termSdlAuthoringInputV1, termCanonicalizationProfile: semanticProfile, termSourceDigest: t.sourceDigest, termTargetDigest: nil, termPolicyDigest: t.policyDigest, termDerivationDigest: t.derivationDigest, termPreconditions: []any{}, termPostconditions: []any{}, termAffectedIdentities: []any{}, termIdentityMap: []any{}, termPreservation: map[string]any{termProfile: profile, termOutcome: outcome, termEvidenceDigests: []any{}, termLimitations: []any{limitation}}, termLosses: []any{}, termDiagnostics: []any{}}
}
func transformationCheck(id, outcome string, codes ...string) map[string]any {
	if codes == nil {
		codes = []string{}
	}
	return map[string]any{"check_id": id, termOutcome: outcome, "diagnostic_codes": codes}
}
func transformationDiagnostic(code, message, address, severity string) map[string]any {
	return operationDiagnostic("artifact-transformation."+code, message, address, severity)
}
func operationDiagnostic(code, message, address, severity string) map[string]any {
	return map[string]any{"code": code, termDomain: "artifact-transformation", "address": address, "message": message, "severity": severity}
}
func (t *transformation) loss(severity string) map[string]any {
	return map[string]any{"kind": termDeclarationRemoved, "affected_identity": t.request.Request.Target, "diagnostic": transformationDiagnostic(termDeclarationRemoved, "The selected declaration is absent from the transformed artifact.", "", severity)}
}
func (t *transformation) refused(code, message string, passed []string, affected, includeLoss bool) map[string]any {
	report := t.baseReport()
	failed := map[string]string{"target-not-exact": termTargetExact, "target-unsupported": termTargetSupported, "identity-collision": termTargetInjective, "linked-artifact-stale": termLinkedArtifactsCurrent, termTargetInvalid: termTargetAdmitted, "preservation-failed": "round-trip-canonical-identity", "loss-not-authorized": termLossAuthorized, "linked-artifact-unsupported": "linked-artifacts-supported"}[code]
	checks := map[string]any{}
	for _, id := range passed {
		checks[id] = transformationCheck(id, termPassed)
	}
	checks[failed] = transformationCheck(failed, termFailed, "artifact-transformation."+code)
	for _, id := range slices.Sorted(maps.Keys(checks)) {
		report[termPreconditions] = append(array(report[termPreconditions]), checks[id])
	}
	if affected || t.request.Operation == removeProfile {
		report[termAffectedIdentities] = []any{t.request.Request.Target}
	}
	if includeLoss {
		report[termLosses] = []any{t.loss(termError)}
	}
	report[termDiagnostics] = []any{transformationDiagnostic(code, message, "/request/target_address", termError)}
	return report
}
func (t *transformation) success(output *Document, preconditions, postconditions []string) map[string]any {
	report := t.baseReport()
	targetDigest, _ := output.CanonicalDigest()
	report[termTargetDigest], report[termStatus] = targetDigest, termSuccess
	report[termAffectedIdentities] = []any{t.request.Request.Target}
	for _, id := range preconditions {
		report[termPreconditions] = append(array(report[termPreconditions]), transformationCheck(id, termPassed))
	}
	for _, id := range postconditions {
		report[termPostconditions] = append(array(report[termPostconditions]), transformationCheck(id, termPassed))
	}
	preservation := object(report[termPreservation])
	evidence := slices.Compact(slices.Sorted(slices.Values([]string{t.sourceDigest, targetDigest})))
	preservation[termEvidenceDigests] = evidence
	if t.request.Operation == renameProfile {
		preservation[termOutcome] = "verified"
		preservation[termLimitations] = []any{"Finite structural and semantic verification does not establish behavioral equivalence."}
	}
	return report
}

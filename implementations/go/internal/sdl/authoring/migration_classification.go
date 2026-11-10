package authoring

import (
	"bytes"
	"encoding/json"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

const classificationMigrationProfile = "externalize-sdl-classifications/v1"

func classificationMessage(code string) string {
	switch code {
	case termSourceInvalid:
		return "Legacy source is invalid or unsupported; migrate uncomposed authoring sources with concrete classification values. See docs/migration/external-classifications.md."
	case "context-required":
		return "Supply one complete external concept assertion per legacy association, with exact source-pointer provenance and pinned local scheme snapshots."
	case "context-invalid":
		return "Assertion context must preserve each exact source subject and source pointer without missing, duplicate, stale, or extra mappings."
	case "loss-not-authorized":
		return "Vulnerability declaration removal requires declaration-removed authorization; an unreferenced declaration also requires semantic-omission authorization."
	case "target-invalid":
		return "The native SDL must independently pass structural and semantic validation; migrate references to removed declarations explicitly."
	case "native-projection-changed":
		return "Normalize legacy native fields with the source-version formatter before migration; migration must preserve the native projection exactly."
	case "binding-admission-failed":
		return "Supply exact current scheme snapshots and complete valid assertions; unavailable, stale, ambiguous, superseded, or unknown concepts cannot complete migration."
	}
	return "Classification migration was refused."
}

type classificationMigration struct {
	parser                                               *Parser
	context                                              migrationBindings
	allowed                                              []string
	sourceDigest, contextDigest, policyDigest, canonical string
}

func (p *Parser) migrateClassifications(data, raw []byte) (*Document, []byte, error) {
	operation, err := p.classificationContext(raw)
	if err != nil {
		return nil, nil, err
	}
	operation.sourceDigest, operation.canonical = digest.SHA256(data), "raw-utf8/v1"
	source, err := p.legacyClassificationSource(data)
	if err != nil {
		return operation.finish(nil, nil, nil, nil, termSourceInvalid)
	}
	operation.sourceDigest, operation.canonical = source.digest, semanticProfile
	if len(source.records) > 0 && operation.context.bindings == nil {
		return operation.finish(nil, nil, nil, nil, "context-required")
	}
	if !classificationContextMatches(source, operation.context.bindings) {
		return operation.finish(nil, nil, nil, nil, "context-invalid")
	}
	losses, ok := classificationLosses(source, operation.allowed)
	if !ok {
		return operation.finish(nil, nil, nil, nil, "loss-not-authorized")
	}
	target, err := p.admitMigrationPayload(source.native)
	if err != nil {
		return operation.finish(nil, nil, nil, nil, "target-invalid")
	}
	var normalized any
	if err = json.Unmarshal(target.JSON(), &normalized); err != nil {
		return nil, nil, err
	}
	before, err := jsonIdentity(source.native)
	if err != nil {
		return nil, nil, err
	}
	after, err := jsonIdentity(normalized)
	if err != nil {
		return nil, nil, err
	}
	if before != after {
		return operation.finish(nil, nil, nil, nil, "native-projection-changed")
	}
	documents, err := operation.bindings(source, target)
	if err != nil {
		return operation.finish(nil, nil, nil, nil, "binding-admission-failed")
	}
	affected := source.declarationIDs()
	for _, record := range source.records {
		affected = append(affected, record.subject)
	}
	slices.Sort(affected)
	return operation.finish(target, documents, losses, slices.Compact(affected), "")
}

func (p *Parser) classificationContext(raw []byte) (*classificationMigration, error) {
	if bytes.Equal(bytes.TrimSpace(raw), []byte("null")) {
		raw = []byte("{}")
	}
	decoded, err := ingress.Parse(raw, ingress.Limits{MaxBytes: int(p.limits.MaxInputBytes), MaxDepth: p.limits.MaxDepth}, ingress.Object)
	if err != nil || !closed(object(decoded), nil, []string{termBindings, termExisting, termSnapshots, policyField}) {
		return nil, invalid()
	}
	value := object(decoded)
	context, err := p.migrationBindingContext(value)
	if err != nil {
		return nil, err
	}
	policy := map[string]any{termAllowedLossKinds: []any{}}
	if provided, present := value[policyField]; present {
		if !closed(object(provided), nil, []string{termAllowedLossKinds}) {
			return nil, invalid()
		}
		maps.Copy(policy, object(provided))
	}
	var wire struct {
		Losses []string `json:"allowed_loss_kinds"`
	}
	encoded, err := json.Marshal(policy)
	if err != nil || json.Unmarshal(encoded, &wire) != nil || wire.Losses == nil || !slices.IsSorted(wire.Losses) || len(slices.Compact(slices.Clone(wire.Losses))) != len(wire.Losses) {
		return nil, invalid()
	}
	for _, loss := range wire.Losses {
		if loss != termDeclarationRemoved && loss != "semantic-omission" {
			return nil, invalid()
		}
	}
	policyDigest, err := jsonIdentity(policy)
	if err != nil {
		return nil, err
	}
	contextDigest, err := jsonIdentity(map[string]any{termBindings: context.bindings, termExisting: context.existing, termSnapshots: context.snapshots})
	return &classificationMigration{parser: p, context: context, allowed: wire.Losses, contextDigest: contextDigest, policyDigest: policyDigest}, err
}

func classificationContextMatches(source *legacyClassifications, document any) bool {
	if document == nil {
		return len(source.records) == 0
	}
	bindings := object(object(document)[termBindings])
	if len(bindings) != len(source.records) {
		return false
	}
	used := map[string]bool{}
	for _, record := range source.records {
		candidates := []map[string]any{}
		for _, raw := range bindings {
			binding := object(raw)
			if classificationBindingMatches(binding, source.digest, record.pointer) {
				candidates = append(candidates, binding)
			}
		}
		if len(candidates) != 1 {
			return false
		}
		binding := candidates[0]
		id := text(binding["binding_id"])
		subject := object(binding["subject"])
		if used[id] || subject["canonical_ref"] != record.subject || subject["artifact_digest"] != source.digest || record.declaration != "" && object(binding["scheme"])["concept_id"] != record.identifier {
			return false
		}
		used[id] = true
	}
	return true
}

func classificationLosses(source *legacyClassifications, allowed []string) ([]any, bool) {
	declarations := source.declarationIDs()
	if len(declarations) > 0 && !slices.Contains(allowed, termDeclarationRemoved) {
		return nil, false
	}
	referenced := map[string]bool{}
	for _, record := range source.records {
		referenced[record.declaration] = true
	}
	losses := []any{}
	for _, id := range declarations {
		losses = append(losses, classificationLoss(termDeclarationRemoved, id, termDeclarationRemoved, "The historical classification declaration is retained only in the source artifact."))
	}
	for _, id := range declarations {
		if referenced[id] {
			continue
		}
		if !slices.Contains(allowed, "semantic-omission") {
			return nil, false
		}
		losses = append(losses, classificationLoss("semantic-omission", id, "unreferenced-classification", "An unreferenced classification was omitted under explicit loss authorization."))
	}
	return losses, true
}
func classificationLoss(kind, id, code, message string) map[string]any {
	return map[string]any{"kind": kind, "affected_identity": id, "diagnostic": operationDiagnostic("classification-migration."+code, message, "", "warning")}
}
func classificationBindingMatches(binding map[string]any, digest, pointer string) bool {
	for _, raw := range array(object(binding["provenance"])["source_refs"]) {
		ref := object(raw)
		if ref["ref_kind"] == "authoring-input" && ref["ref_digest"] == digest && ref["ref_path"] == pointer {
			return true
		}
	}
	return false
}
func (c *classificationMigration) bindings(source *legacyClassifications, target *Document) ([]any, error) {
	targetDigest, err := target.CanonicalDigest()
	if err != nil {
		return nil, err
	}
	into, from := conceptSubjects(target, targetDigest), conceptSubjects(target, source.digest)
	seen := map[string]bool{}
	for _, subject := range into {
		if seen[subject.CanonicalRef] {
			return nil, invalid()
		}
		seen[subject.CanonicalRef] = true
	}
	documents := []any{}
	if c.context.bindings != nil {
		documents = append(documents, c.context.bindings)
	}
	documents = append(documents, c.context.existing...)
	raw, err := bindingJSON(documents)
	if err != nil {
		return nil, err
	}
	return c.parser.retargetBindingDocuments(from, into, source.digest, targetDigest, "", "", raw, c.context.resolved, true)
}

func (c *classificationMigration) finish(output *Document, documents, losses []any, affected []string, code string) (*Document, []byte, error) {
	derivation, err := jsonIdentity(map[string]any{termOperationProfile: classificationMigrationProfile, termSourceDigest: c.sourceDigest, termPolicyDigest: c.policyDigest, "context_digest": c.contextDigest})
	if err != nil {
		return nil, nil, err
	}
	status, outcome, preserved := termRefused, termFailed, termFailed
	var target any
	postconditions, diagnostics := []any{}, []any{}
	codes := []string{}
	evidence := []string{c.sourceDigest}
	if output != nil {
		status, outcome, preserved = termSuccess, termPassed, "verified"
		targetDigest, digestErr := output.CanonicalDigest()
		if digestErr != nil {
			return nil, nil, digestErr
		}
		target = targetDigest
		evidence = append(evidence, targetDigest)
		for _, document := range documents {
			identity, err := jsonIdentity(document)
			if err != nil {
				return nil, nil, err
			}
			evidence = append(evidence, identity)
		}
		postconditions = append(postconditions, transformationCheck("target-and-bindings-admitted", termPassed))
	} else {
		fullCode := "classification-migration." + code
		codes = append(codes, fullCode)
		diagnostics = append(diagnostics, operationDiagnostic(fullCode, classificationMessage(code), "", termError))
	}
	if losses == nil {
		losses = []any{}
	}
	if affected == nil {
		affected = []string{}
	}
	slices.Sort(evidence)
	report := map[string]any{termSchemaVersion: termArtifactTransformationReportV1, termOperationProfile: classificationMigrationProfile, termStatus: status, termArtifactKind: termSdlAuthoring, termSourceProfile: "sdl-legacy-classifications/v1", termTargetProfile: termSdlAuthoringInputV1, termCanonicalizationProfile: c.canonical, termSourceDigest: c.sourceDigest, termTargetDigest: target, termPolicyDigest: c.policyDigest, termDerivationDigest: derivation, termPreconditions: []any{transformationCheck("migration-context", outcome, codes...)}, termPostconditions: postconditions, termAffectedIdentities: affected, termIdentityMap: []any{}, termLosses: losses, termPreservation: map[string]any{termProfile: "native-configuration-and-explicit-assertions/v1", termOutcome: preserved, termEvidenceDigests: slices.Compact(evidence), termLimitations: []string{"Native projection equality and binding admission do not prove realization or participant disclosure."}}, termDiagnostics: diagnostics}
	return c.parser.operationResult(output, report, documents)
}

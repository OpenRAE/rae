package authoring

import (
	"bytes"
	"encoding/json"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

const progressiveMigrationProfile = "adopt-progressive-sdl-semantics/v1"
const legacyRevision = "raes-legacy-semantics/384e8b19"
const progressiveRevision = "raes-progressive-semantics/v1"

type sentinelDecision struct {
	Pointer        string  `json:"pointer"`
	Interpretation string  `json:"interpretation"`
	Identity       *string `json:"identity"`
	Rationale      string  `json:"rationale"`
}
type semanticMigrationContext struct {
	SourceDigest        string             `json:"source_digest"`
	SourceRevision      string             `json:"source_revision"`
	TargetRevision      string             `json:"target_revision"`
	Adopt               bool               `json:"adopt_recursive_constraints"`
	AdmissionContract   string             `json:"admission_contract"`
	ObservationContract string             `json:"observation_contract"`
	Rationale           string             `json:"rationale"`
	Decisions           []sentinelDecision `json:"sentinel_decisions"`
}

// Migrate adopts explicitly selected semantics. It never interprets legacy
// source as executable current SDL or invents an author's missing decision.
func (p *Parser) Migrate(data, context []byte) (*Document, []byte, error) {
	operation, authorRaw, err := p.migrationOperationContext(context)
	if err != nil {
		return nil, nil, err
	}
	switch operation {
	case participantMigrationProfile:
		return p.migrateParticipants(data, authorRaw)
	case mixedMigrationProfile:
		if !bytes.Equal(authorRaw, []byte("null")) {
			return nil, nil, invalid()
		}
		return p.migrateMixedControl(data)
	case classificationMigrationProfile:
		return p.migrateClassifications(data, authorRaw)
	case progressiveMigrationProfile:
		return p.migrateProgressiveContext(data, authorRaw)
	case "":
	default:
		return nil, nil, invalid()
	}
	author, err := p.semanticMigrationContext(context)
	if err != nil {
		return nil, nil, err
	}
	return p.migrateProgressive(data, author, migrationBindings{existing: []any{}, snapshots: []any{}})
}
func (p *Parser) migrationOperationContext(raw []byte) (string, []byte, error) {
	if len(raw) == 0 || bytes.Equal(bytes.TrimSpace(raw), []byte("null")) {
		return "", raw, nil
	}
	decoded, err := ingress.Parse(raw, ingress.Limits{MaxBytes: int(p.limits.MaxInputBytes), MaxDepth: p.limits.MaxDepth}, ingress.Object)
	if err != nil {
		return "", nil, err
	}
	value := object(decoded)
	operation, present := value[termOperationProfile]
	if !present {
		return "", raw, nil
	}
	if !closed(value, []string{termOperationProfile}, []string{"context"}) {
		return "", nil, invalid()
	}
	name, ok := operation.(string)
	if !ok || name == "" {
		return "", nil, invalid()
	}
	author, err := json.Marshal(value["context"])
	return name, author, err
}
func (p *Parser) migrateProgressiveContext(data, raw []byte) (*Document, []byte, error) {
	value, err := ingress.Parse(raw, ingress.Limits{MaxBytes: int(p.limits.MaxInputBytes), MaxDepth: p.limits.MaxDepth}, ingress.Object)
	if err != nil || !closed(object(value), nil, []string{"author", termBindings, termSnapshots}) {
		return nil, nil, invalid()
	}
	authorRaw, err := json.Marshal(object(value)["author"])
	if err != nil {
		return nil, nil, err
	}
	author, err := p.semanticMigrationContext(authorRaw)
	if err != nil {
		return nil, nil, err
	}
	linked := map[string]any{termSnapshots: object(value)[termSnapshots]}
	if linked[termSnapshots] == nil {
		delete(linked, termSnapshots)
	}
	if bindings, present := object(value)[termBindings]; present {
		linked[termExisting] = bindings
	}
	context, err := p.migrationBindingContext(linked)
	if err != nil {
		return nil, nil, err
	}
	return p.migrateProgressive(data, author, context)
}
func (p *Parser) migrateProgressive(data []byte, author *semanticMigrationContext, context migrationBindings) (*Document, []byte, error) {
	source, output, code := p.adoptProgressive(data, author)
	sourceProfile := legacyRevision
	if output != nil && author == nil {
		sourceProfile = progressiveRevision
	}
	documents := []any{}
	if output != nil {
		var err error
		documents, err = p.progressiveBindings(source, output, context)
		if err != nil {
			output = nil
			documents = []any{}
			code = termSourceOrTargetInvalid
			sourceProfile = legacyRevision
		}
	}
	linkedDigest, err := jsonIdentity(map[string]any{termBindings: context.existing, "schemes": context.snapshots})
	if err != nil {
		return nil, nil, err
	}
	report, err := progressiveMigrationReport(data, author, output, code, sourceProfile, linkedDigest)
	if err != nil {
		return nil, nil, err
	}
	return p.operationResult(output, report, documents)
}
func (p *Parser) progressiveBindings(source, target *Document, context migrationBindings) ([]any, error) {
	if len(context.existing) == 0 {
		return []any{}, nil
	}
	fromDigest, err := source.CanonicalDigest()
	if err != nil {
		return nil, err
	}
	toDigest, err := target.CanonicalDigest()
	if err != nil {
		return nil, err
	}
	raw, err := bindingJSON(context.existing)
	if err != nil {
		return nil, err
	}
	return p.retargetBindingDocuments(bindingRetarget{from: conceptSubjects(source, fromDigest), into: conceptSubjects(target, toDigest), sourceDigest: fromDigest, targetDigest: toDigest}, raw, context.resolved, true)
}
func (p *Parser) semanticMigrationContext(raw []byte) (*semanticMigrationContext, error) {
	if len(raw) == 0 || bytes.Equal(bytes.TrimSpace(raw), []byte("null")) {
		return nil, nil //nolint:nilnil // Null represents valid absence in this operation contract.
	}
	limits := ingress.Limits{MaxBytes: int(p.limits.MaxInputBytes), MaxDepth: p.limits.MaxDepth}
	if err := p.models.CheckPortable("sdl-semantic-migration-context-v1", raw, limits); err != nil {
		return nil, err
	}
	author := &semanticMigrationContext{SourceRevision: legacyRevision, TargetRevision: progressiveRevision, Decisions: []sentinelDecision{}}
	if json.Unmarshal(raw, author) != nil {
		return nil, invalid()
	}
	return author, nil
}
func (p *Parser) adoptProgressive(data []byte, author *semanticMigrationContext) (*Document, *Document, string) {
	options := source.DefaultOptions()
	options.Limits = p.limits
	document, err := source.Decode(data, options)
	if err != nil {
		return nil, nil, termSourceOrTargetInvalid
	}
	raw := object(document.Value())
	if raw["semantic_revision"] == progressiveRevision {
		if author != nil {
			return nil, nil, termSourceMismatch
		}
		output, admissionErr := p.admitMigrationTarget(raw)
		if admissionErr != nil {
			return nil, nil, termSourceOrTargetInvalid
		}
		return output, output, ""
	}
	if author == nil {
		return nil, nil, "context-required"
	}
	if author.SourceDigest != digest.SHA256(data) {
		return nil, nil, termSourceMismatch
	}
	if raw == nil || raw["semantic_revision"] != nil && raw["semantic_revision"] != legacyRevision {
		return nil, nil, termSourceOrTargetInvalid
	}
	if nonemptyJSON(raw[importsField]) {
		return nil, nil, "migrate-modules-independently"
	}
	input, err := p.progressiveSourceDocument(raw)
	if err != nil {
		return nil, nil, termSourceOrTargetInvalid
	}
	payload, code := applySentinelDecisions(input, author.Decisions)
	if code != "" {
		return nil, nil, code
	}
	payload["semantic_revision"] = progressiveRevision
	output, err := p.admitMigrationTarget(payload)
	if err != nil {
		return nil, nil, termSourceOrTargetInvalid
	}
	return input, output, ""
}
func (p *Parser) progressiveSourceDocument(raw map[string]any) (*Document, error) {
	payload := maps.Clone(raw)
	delete(payload, "semantic_revision")
	encoded, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	formatted, err := p.Format(Request{Source: encoded})
	if err != nil {
		return nil, err
	}
	input, err := p.Decode(Request{Source: formatted.Content})
	if err != nil {
		return nil, err
	}
	input, _, err = p.Validate(input)
	return input, err
}
func (p *Parser) admitMigrationTarget(raw map[string]any) (*Document, error) {
	output, err := p.admitMigrationPayload(raw)
	if err != nil {
		return nil, err
	}
	if _, err = output.CanonicalDigest(); err != nil {
		return nil, err
	}
	return output, nil
}
func (p *Parser) admitMigrationPayload(payload map[string]any) (*Document, error) {
	raw, err := json.Marshal(payload)
	if err != nil {
		return nil, invalid()
	}
	document, err := p.Decode(Request{Source: raw})
	if err != nil {
		return nil, err
	}
	admitted, _, err := p.Validate(document)
	return admitted, err
}
func progressiveMigrationReport(data []byte, author *semanticMigrationContext, output *Document, code, sourceProfile, linkedDigest string) (map[string]any, error) {
	sourceDigest := digest.SHA256(data)
	policyDigest, err := jsonIdentity(author)
	if err != nil {
		return nil, err
	}
	derivation, err := jsonIdentity(map[string]any{"operation": progressiveMigrationProfile, "source": sourceDigest, policyField: policyDigest, "linked_context": linkedDigest})
	if err != nil {
		return nil, err
	}
	status, outcome := termRefused, termFailed
	var targetDigest any
	postconditions := []any{}
	if output != nil {
		status, outcome = termSuccess, termPassed
		identity, err := output.CanonicalDigest()
		if err != nil {
			return nil, err
		}
		targetDigest = identity
		postconditions = append(postconditions, transformationCheck("current-target-admission", termPassed))
	}
	affected := []string{}
	if author != nil {
		for _, decision := range author.Decisions {
			affected = append(affected, decision.Pointer)
		}
	}
	slices.Sort(affected)
	diagnostics := []any{}
	if code != "" {
		diagnostics = append(diagnostics, operationDiagnostic("semantic-migration."+code, "Explicit semantic migration was refused; review the source-bound decisions and migration guide.", "", termError))
	}
	return map[string]any{termSchemaVersion: termArtifactTransformationReportV1, termOperationProfile: progressiveMigrationProfile, termStatus: status, termArtifactKind: termSdlAuthoring, termSourceProfile: sourceProfile, termTargetProfile: progressiveRevision, termCanonicalizationProfile: "sdl-progressive-migration-digest-pair/v1", termSourceDigest: sourceDigest, termTargetDigest: targetDigest, termPolicyDigest: policyDigest, termDerivationDigest: derivation, termPreconditions: []any{transformationCheck("source-and-author-context", outcome)}, termPostconditions: postconditions, termAffectedIdentities: affected, termIdentityMap: []any{}, termPreservation: map[string]any{termProfile: "explicit-semantic-revision-adoption/v1", termOutcome: termNotApplicable, termEvidenceDigests: []any{}, termLimitations: []any{"Author adoption changes recursive, admission and observation semantics; no cross-version equivalence or current execution claim is made."}}, termLosses: []any{}, termDiagnostics: diagnostics}, nil
}

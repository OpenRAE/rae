package authoring

import (
	"bytes"
	"encoding/json"
	"maps"
	"slices"
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

const participantMigrationProfile = "adopt-participant-identity/v1"

type participantMigrationContext struct {
	SourceDigest string             `json:"source_digest"`
	Objectives   map[string]*string `json:"entity_objectives"`
}

func (p *Parser) migrateParticipants(data, raw []byte) (*Document, []byte, error) {
	author, err := p.participantContext(raw)
	if err != nil {
		return nil, nil, err
	}
	policyDigest, err := jsonIdentity(author)
	if err != nil {
		return nil, nil, err
	}
	output, code, pointer := p.participantCandidate(data, author)
	affected := []string{}
	if author != nil {
		affected = append(affected, slices.Sorted(maps.Keys(author.Objectives))...)
	}
	diagnostics := []any{}
	if code != "" {
		diagnostics = append(diagnostics, operationDiagnostic("participant-migration."+code, "Participant migration refused; review source-bound decisions and docs/migration/participant-identity.md.", pointer, termError))
	}
	report, err := simpleMigrationReport(data, output, migrationReportProfile{operation: participantMigrationProfile, source: "sdl-participant-relations/pre-1338", canonical: "participant-migration-digest-pair/v1", preservation: "explicit-participant-relations/v1", precondition: "source-and-author-decisions", postcondition: "canonical-target-admitted", limitations: []string{"Authored relation migration is not evidence of realized action or cross-version equivalence."}}, policyDigest, affected, diagnostics)
	if err != nil {
		return nil, nil, err
	}
	return p.operationResult(output, report, nil)
}
func (p *Parser) participantCandidate(data []byte, author *participantMigrationContext) (*Document, string, string) {
	options := source.DefaultOptions()
	options.Limits = p.limits
	decoded, err := source.Decode(data, options)
	if err != nil {
		return nil, termSourceOrTargetInvalid, ""
	}
	payload := object(decoded.Value())
	if code, pointer := participantSourceIssue(payload); code != "" {
		return nil, code, pointer
	}
	if code, pointer := participantDecisionIssue(payload, author, digest.SHA256(data)); code != "" {
		return nil, code, pointer
	}
	if code, pointer := adoptParticipantRelations(payload, decoded, author); code != "" {
		return nil, code, pointer
	}
	if code, pointer := unresolvedParticipantRelation(payload, decoded); code != "" {
		return nil, code, pointer
	}
	output, err := p.admitMigrationPayload(payload)
	if err != nil {
		return nil, termSourceOrTargetInvalid, ""
	}
	if _, err = output.CanonicalDigest(); err != nil {
		return nil, termSourceOrTargetInvalid, ""
	}
	return output, "", ""
}
func (p *Parser) participantContext(raw []byte) (*participantMigrationContext, error) {
	if bytes.Equal(bytes.TrimSpace(raw), []byte("null")) {
		return nil, nil //nolint:nilnil // Null represents valid absence in this operation contract.
	}
	decoded, err := ingress.Parse(raw, ingress.Limits{MaxBytes: int(p.limits.MaxInputBytes), MaxDepth: p.limits.MaxDepth}, ingress.Object)
	if err != nil || !closed(object(decoded), []string{termSourceDigest}, []string{"entity_objectives"}) {
		return nil, invalid()
	}
	author := &participantMigrationContext{Objectives: map[string]*string{}}
	if json.Unmarshal(raw, author) != nil || !digest.Valid(author.SourceDigest) || len(author.Objectives) > 10000 {
		return nil, invalid()
	}
	if _, present := object(decoded)["entity_objectives"]; present && object(object(decoded)["entity_objectives"]) == nil {
		return nil, invalid()
	}
	return author, nil
}
func participantSourceIssue(payload map[string]any) (string, string) {
	if payload == nil {
		return termSourceInvalid, ""
	}
	if nonemptyJSON(payload[importsField]) {
		return "source-unsupported", "/imports"
	}
	if _, present := payload["materialization_provenance"]; present {
		return "source-unsupported", "/materialization_provenance"
	}
	for _, section := range []string{agentsSection, objectivesSection, variationPointsField} {
		if raw, present := payload[section]; present && object(raw) == nil {
			return termSourceInvalid, ""
		}
	}
	return "", ""
}
func nonemptyJSON(value any) bool {
	switch v := value.(type) {
	case nil:
		return false
	case bool:
		return v
	case string:
		return v != ""
	case []any:
		return len(v) > 0
	case map[string]any:
		return len(v) > 0
	case json.Number:
		number, err := strconv.ParseFloat(string(v), 64)
		return err != nil || number != 0
	}
	return true
}
func participantDecisionIssue(payload map[string]any, author *participantMigrationContext, sourceDigest string) (string, string) {
	decisions := map[string]*string{}
	if author != nil {
		if author.SourceDigest != sourceDigest {
			return termSourceMismatch, "/context/source_digest"
		}
		decisions = author.Objectives
	}
	required := map[string]bool{}
	for name, raw := range object(payload[objectivesSection]) {
		if _, legacy := object(raw)["entity"]; legacy {
			required[jsonpointer.FromTokens([]string{objectivesSection, name})] = true
		}
	}
	missing := []string{}
	for pointer := range required {
		if _, present := decisions[pointer]; !present {
			missing = append(missing, pointer)
		}
	}
	if len(missing) > 0 {
		slices.Sort(missing)
		return "decision-required", missing[0]
	}
	for pointer := range decisions {
		if !required[pointer] {
			return "decision-mismatch", "/context/entity_objectives"
		}
	}
	return "", ""
}
func adoptParticipantRelations(payload map[string]any, document *source.Document, author *participantMigrationContext) (string, string) {
	for _, section := range []string{agentsSection, objectivesSection} {
		mapping := detachParticipantDeclarations(object(payload[section]))
		payload[section] = mapping
		for _, name := range orderedKeys(mapping, document.View().Child(section).Keys()) {
			value := object(mapping[name])
			pointer := jsonpointer.FromTokens([]string{section, name})
			var code string
			if section == agentsSection {
				code = adoptAgentRelation(value)
			} else {
				code = adoptObjectiveRelation(value, pointer, author)
			}
			if code != "" {
				return code, pointer
			}
		}
	}
	for _, raw := range object(payload[variationPointsField]) {
		target := object(object(raw)[targetField])
		switch target["slot"] {
		case "objectives.agent":
			target["slot"] = "objectives.assigned_participant"
		case "objectives.entity":
			target["slot"] = "objectives.owner"
		}
	}
	return "", ""
}
func detachParticipantDeclarations(mapping map[string]any) map[string]any {
	detached := map[string]any{}
	for name, raw := range mapping {
		if value := object(raw); value != nil {
			raw = maps.Clone(value)
		}
		detached[name] = raw
	}
	return detached
}
func adoptAgentRelation(value map[string]any) string {
	if _, legacy := value["entity"]; !legacy {
		return ""
	}
	if _, present := value["affiliations"]; present {
		return termConflictingFields
	}
	if _, present := value["role"]; present {
		return termConflictingFields
	}
	entity, ok := value["entity"].(string)
	if !ok || entity == "" {
		return termSourceInvalid
	}
	delete(value, "entity")
	value["affiliations"] = []any{entity}
	return ""
}
func adoptObjectiveRelation(value map[string]any, pointer string, author *participantMigrationContext) string {
	_, oldAgent := value["agent"]
	_, oldEntity := value["entity"]
	if !oldAgent && !oldEntity {
		return ""
	}
	if _, present := value[termOwner]; present {
		return termConflictingFields
	}
	if _, present := value["assigned_participant"]; present {
		return termConflictingFields
	}
	if oldAgent && oldEntity {
		return termConflictingFields
	}
	field, target := "entity", termOwner
	if oldAgent {
		field, target = "agent", "assigned_participant"
	}
	name, ok := value[field].(string)
	if !ok || name == "" {
		return termSourceInvalid
	}
	delete(value, field)
	value[target] = name
	if oldEntity && author != nil {
		if assignment := author.Objectives[pointer]; assignment != nil {
			value["assigned_participant"] = *assignment
		}
	}
	return ""
}
func unresolvedParticipantRelation(payload map[string]any, document *source.Document) (string, string) {
	for _, section := range []string{agentsSection, objectivesSection} {
		fields := []string{"affiliations", "role", termActions}
		if section == objectivesSection {
			fields = []string{termOwner, "assigned_participant", termActions}
		}
		for _, name := range orderedKeys(object(payload[section]), document.View().Child(section).Keys()) {
			if field := unresolvedParticipantField(object(object(payload[section])[name]), fields); field != "" {
				return "unresolved-reference", jsonpointer.FromTokens([]string{section, name, field})
			}
		}
	}
	return "", ""
}

func unresolvedParticipantField(value map[string]any, fields []string) string {
	for _, field := range fields {
		items, ok := value[field].([]any)
		if !ok {
			items = []any{value[field]}
		}
		if slices.ContainsFunc(items, variable) {
			return field
		}
	}
	return ""
}

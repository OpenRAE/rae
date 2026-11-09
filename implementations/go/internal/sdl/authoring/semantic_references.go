package authoring

import (
	"fmt"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type semanticPurpose uint8

const (
	referenceDeclared semanticPurpose = iota
	referenceTarget
	referenceObjectiveSubject
	referenceActionTarget
	referenceSharedState
	referenceRelationship
	referenceParticipant
	referenceNode
	referenceIdentityDomain
	referenceIdentityForest
	referenceIdentityAuthority
	referenceIdentityFacade
	referenceDeploymentTenant
	referenceNodeService
	referenceApplication
	referenceDatabase
	referenceMail
	referenceObservation
	referenceAuthorityAnchor
	referenceAuthorityScope
)

func (p semanticPurpose) label() string {
	return [...]string{"a reference", "a target", "an objective subject", "an action target", "shared state", "a relationship endpoint", "a participant endpoint", "a node endpoint", "an identity domain endpoint", "an identity forest endpoint", "an identity authority endpoint", "an identity facade endpoint", "a deployment tenant endpoint", "a node service endpoint", "a runtime application endpoint", "a database endpoint", "a mail service endpoint", "an observation subject", "an authority anchor", "an authority scope"}[p]
}
func (p semanticPurpose) domain() semanticPurpose {
	if p == referenceDeclared || p == referenceAuthorityAnchor {
		return referenceDeclared
	}
	return referenceTarget
}
func (p semanticPurpose) permits(d declaration) bool {
	switch p {
	case referenceDeclared, referenceAuthorityAnchor:
		return d.declared
	case referenceTarget, referenceRelationship, referenceObservation:
		return d.target
	case referenceObjectiveSubject:
		return d.objectiveSubject()
	case referenceActionTarget:
		return d.action
	case referenceSharedState:
		return d.action && d.kind != agentsSection && d.kind != entitiesField
	case referenceAuthorityScope:
		return d.authority
	case referenceParticipant:
		return d.kind == agentsSection
	case referenceNode:
		return d.kind == nodesSection
	case referenceIdentityDomain:
		return d.kind == identityDomainsField
	case referenceIdentityForest:
		return d.kind == identityForestsField
	case referenceIdentityAuthority:
		return d.kind == identityDomainsField || d.kind == identityForestsField
	case referenceIdentityFacade:
		return d.kind == identityFacadesField
	case referenceDeploymentTenant:
		return d.kind == deploymentTenantsField
	case referenceNodeService:
		return d.kind == servicesField
	case referenceApplication:
		return d.kind == applicationsField
	case referenceDatabase:
		return d.kind == databaseServicesField || d.kind == "database_services.databases"
	case referenceMail:
		return d.kind == mailServicesField || strings.HasPrefix(d.kind, mailServicesField+".")
	}
	return false
}

func eligibleReference(d declaration, purposes []semanticPurpose) bool {
	for _, purpose := range purposes {
		if !purpose.permits(d) {
			return false
		}
	}
	return true
}
func purposeLabels(purposes []semanticPurpose) string {
	labels := make([]string, len(purposes))
	for i, purpose := range purposes {
		labels[i] = purpose.label()
	}
	return strings.Join(labels, " and as ")
}
func referenceElement(purposes []semanticPurpose) string {
	if len(purposes) == 1 {
		p := purposes[0]
		if p == referenceDeclared || p == referenceAuthorityAnchor {
			return "element"
		}
		if p == referenceTarget || p == referenceRelationship || p == referenceObservation {
			return "targetable element"
		}
	}
	return "element eligible as " + purposeLabels(purposes)
}

type semanticReferenceResult struct{ domain, eligible, declared []string }

func (m *semanticModel) referenceResult(reference string, purposes []semanticPurpose) semanticReferenceResult {
	var result semanticReferenceResult
	for address, candidate := range m.index.aliases[reference] {
		if candidate.declared {
			result.declared = append(result.declared, address)
		}
		if !purposes[0].domain().permits(candidate) {
			continue
		}
		result.domain = append(result.domain, address)
		if eligibleReference(candidate, purposes) {
			result.eligible = append(result.eligible, address)
		}
	}
	slices.Sort(result.domain)
	slices.Sort(result.eligible)
	slices.Sort(result.declared)
	return result
}
func (r semanticReferenceResult) ambiguity(purposes []semanticPurpose) string {
	var refused []string
	for _, address := range r.domain {
		if !slices.Contains(r.eligible, address) {
			refused = append(refused, address)
		}
	}
	detail := ""
	if len(refused) > 0 {
		detail = "; not eligible as " + purposeLabels(purposes) + ": " + strings.Join(refused, ", ")
	}
	return strings.Join(r.eligible, ", ") + detail
}
func (m *semanticModel) failedPurposes(reference string, result semanticReferenceResult, purposes []semanticPurpose) []semanticPurpose {
	if len(result.domain) != 1 {
		return purposes
	}
	var failed []semanticPurpose
	for _, purpose := range purposes {
		if !purpose.permits(m.index.aliases[reference][result.domain[0]]) {
			failed = append(failed, purpose)
		}
	}
	if len(failed) == 0 {
		return purposes
	}
	return failed
}

// Narrow purposes preserve ambiguity in their wider resolution domain.
func (m *semanticModel) namedReference(c *semanticCollector, owner semanticOwner, label, field, reference string, purposes ...semanticPurpose) {
	if variable(reference) {
		return
	}
	m.requireNamedReference(c, owner, label, field, reference, purposes...)
}
func (m *semanticModel) requireNamedReference(c *semanticCollector, owner semanticOwner, label, field, reference string, purposes ...semanticPurpose) {
	result := m.referenceResult(reference, purposes)
	if len(result.eligible) == 0 {
		detail := ""
		if len(result.declared) > 0 {
			detail = "; it names " + strings.Join(result.declared, ", ")
		}
		failed := m.failedPurposes(reference, result, purposes)
		c.report(owner, fmt.Sprintf("%s %s '%s' does not reference any defined %s%s", label, field, reference, referenceElement(failed), detail))
		return
	}
	if len(result.domain) > 1 {
		c.report(owner, fmt.Sprintf("%s %s '%s' is ambiguous; use one of: %s", label, field, reference, result.ambiguity(purposes)))
	}
}

func relationshipTypePurposes(kind string) [2]semanticPurpose {
	switch kind {
	case domainControllerType, joinsDomainType:
		return [2]semanticPurpose{referenceNode, referenceIdentityDomain}
	case forestTrustsType:
		return [2]semanticPurpose{referenceIdentityForest, referenceIdentityForest}
	case directoryFederatesType:
		return [2]semanticPurpose{referenceIdentityAuthority, referenceIdentityFacade}
	case placedOnCarrierType:
		return [2]semanticPurpose{referenceNode, referenceNode}
	case usesSharedServiceType:
		return [2]semanticPurpose{referenceDeploymentTenant, referenceNodeService}
	case participantField:
		return [2]semanticPurpose{referenceParticipant, referenceParticipant}
	default:
		return [2]semanticPurpose{referenceRelationship, referenceRelationship}
	}
}
func mergeEndpointPurposes(current [2][]semanticPurpose, pair [2]semanticPurpose) [2][]semanticPurpose {
	for i, purpose := range pair {
		if purpose != referenceRelationship && !slices.Contains(current[i], purpose) {
			current[i] = append(current[i], purpose)
		}
	}
	return current
}
func (m *semanticModel) relationshipPurposes(name string) [2][]semanticPurpose {
	r := fieldValue(m.transport.Relationships)[name]
	purposes := mergeEndpointPurposes([2][]semanticPurpose{}, relationshipTypePurposes(string(fieldValue(r.Type))))
	for _, detail := range []struct {
		active bool
		kind   string
	}{
		{hasField(r.DomainController), domainControllerType}, {hasField(r.DomainJoin), joinsDomainType}, {hasField(r.ForestTrust), forestTrustsType}, {hasField(r.IdentityFederation), directoryFederatesType}, {hasField(r.CarrierPlacement), placedOnCarrierType}, {hasField(r.SharedService), usesSharedServiceType},
	} {
		if detail.active {
			purposes = mergeEndpointPurposes(purposes, relationshipTypePurposes(detail.kind))
		}
	}
	if hasField(r.DatabaseAccess) {
		purposes = mergeEndpointPurposes(purposes, [2]semanticPurpose{referenceApplication, referenceDatabase})
	}
	if hasField(r.MailAccess) {
		purposes = mergeEndpointPurposes(purposes, [2]semanticPurpose{referenceRelationship, referenceMail})
	}
	for i := range purposes {
		if len(purposes[i]) == 0 {
			purposes[i] = []semanticPurpose{referenceRelationship}
		}
		slices.Sort(purposes[i])
	}
	return purposes
}
func (m *semanticModel) checkRelationships(c *semanticCollector) {
	for _, r := range m.relationships {
		name := r.name
		if r.participant != nil {
			m.checkParticipantRelationship(c, r)
			continue
		}
		purposes := m.relationshipPurposes(name)
		owner, label := semanticOwner{relationshipsField, name}, "Relationship '"+name+"'"
		m.namedReference(c, owner, label, sourceField, r.source, purposes[0]...)
		m.namedReference(c, owner, label, targetField, r.target, purposes[1]...)
	}
}

//nolint:ireturn // Each use returns its concrete schema-derived field type, without a runtime interface.
func fieldValue[T any](field binding.Field[T]) T  { value, _ := field.Value(); return value }
func hasField[T any](field binding.Field[T]) bool { return field.Present() && !field.Null() }

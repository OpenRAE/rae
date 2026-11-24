package processor

import (
	"encoding/json"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

type serviceMaterializationSource struct {
	SchemaVersion                string   `json:"schema_version"`
	TargetServiceRef             string   `json:"target_service_ref"`
	InterfaceProfile             string   `json:"interface_profile"`
	ProfileVersion               string   `json:"profile_version"`
	SharedServiceRelationshipRef string   `json:"shared_service_relationship_ref"`
	OrderingContentRefs          []string `json:"ordering_content_refs"`
	ReadbackAssertionRefs        []string `json:"readback_assertion_refs"`
	EvidenceRequirementRefs      []string `json:"evidence_requirement_refs"`
	ObservationBoundaryRefs      []string `json:"observation_boundary_refs"`
	Requirements                 struct {
		Operation      string            `json:"operation"`
		ConflictPolicy string            `json:"conflict_policy"`
		Readback       string            `json:"readback"`
		FieldSemantics map[string]string `json:"field_semantics"`
	} `json:"requirements"`
}
type serviceMaterializationWire struct {
	TargetServiceAddress         string            `json:"target_service_address"`
	InterfaceProfile             string            `json:"interface_profile"`
	ProfileVersion               string            `json:"profile_version"`
	ContentType                  string            `json:"content_type"`
	Operation                    string            `json:"operation"`
	ConflictPolicy               string            `json:"conflict_policy"`
	Readback                     string            `json:"readback"`
	FieldSemantics               map[string]string `json:"field_semantics,omitempty"`
	CanonicalContentDigest       string            `json:"canonical_content_digest"`
	CanonicalFieldSchemaDigest   string            `json:"canonical_field_schema_digest,omitempty"`
	SharedServiceRelationshipRef string            `json:"shared_service_relationship_ref"`
	ConsumerTenantRef            string            `json:"consumer_tenant_ref"`
	MutableStateOwner            string            `json:"mutable_state_owner"`
	ResetGenerationOwner         string            `json:"reset_generation_owner"`
	ReadbackAssertionAddresses   []string          `json:"readback_assertion_addresses"`
	EvidenceRequirementRefs      []string          `json:"evidence_requirement_refs"`
	ObservationBoundaryAddresses []string          `json:"observation_boundary_addresses"`
}

func (state *compilerState) compileServiceMaterialization(raw json.RawMessage, target, contentType string, content json.RawMessage, owner string) (*ServiceMaterialization, any, []string, []diagnostic.Diagnostic) {
	if len(raw) == 0 || string(raw) == termNull {
		return nil, nil, nil, nil
	}
	var source serviceMaterializationSource
	if err := json.Unmarshal(raw, &source); err != nil {
		state.err = invalidCompiled()
		return nil, nil, nil, nil
	}
	if source.SchemaVersion == "domain-profile-binding/v1" {
		return &ServiceMaterialization{ProfileBinding: domainProfileBinding(raw)}, nil, nil, nil
	}
	nodeName, serviceName := state.materializationServiceTarget(source.TargetServiceRef)
	if nodeName == "" || nodeName != target {
		return nil, nil, nil, []diagnostic.Diagnostic{compileDiagnostic("provisioning.content-service-target-ref-unbound", termProvisioning, owner, "Service materialization target does not resolve on the content target node.")}
	}
	wire := serviceMaterializationWire{TargetServiceAddress: state.address(termProvision, termNode, nodeName, "service", serviceName), InterfaceProfile: source.InterfaceProfile, ProfileVersion: source.ProfileVersion, ContentType: contentType, Operation: source.Requirements.Operation, ConflictPolicy: source.Requirements.ConflictPolicy, Readback: source.Requirements.Readback, CanonicalContentDigest: state.canonicalDigest(content), SharedServiceRelationshipRef: source.SharedServiceRelationshipRef, ReadbackAssertionAddresses: []string{}, EvidenceRequirementRefs: nonNilStrings(source.EvidenceRequirementRefs), ObservationBoundaryAddresses: []string{}}
	for _, ref := range source.ReadbackAssertionRefs {
		wire.ReadbackAssertionAddresses = append(wire.ReadbackAssertionAddresses, state.address(termEvaluation, termAssertion, ref))
	}
	for _, ref := range source.ObservationBoundaryRefs {
		wire.ObservationBoundaryAddresses = append(wire.ObservationBoundaryAddresses, state.address(termParticipant, termObservationBoundary, ref))
	}
	state.materializationServiceRelationship(source.SharedServiceRelationshipRef, &wire)
	if state.err != nil {
		return nil, nil, nil, nil
	}
	if source.Requirements.FieldSemantics != nil {
		wire.FieldSemantics = source.Requirements.FieldSemantics
		wire.CanonicalFieldSchemaDigest = state.canonicalDigest(rawJSON(struct {
			InterfaceProfile string            `json:"interface_profile"`
			ProfileVersion   string            `json:"profile_version"`
			ProjectionScope  string            `json:"projection_scope"`
			FieldSemantics   map[string]string `json:"field_semantics"`
		}{source.InterfaceProfile, source.ProfileVersion, "declared-fields", wire.FieldSemantics}))
	}
	dependencies := []string{}
	for _, ref := range source.OrderingContentRefs {
		dependencies = append(dependencies, state.address(termProvision, termContent, ref))
	}
	facts := &ServiceMaterialization{TargetServiceAddress: wire.TargetServiceAddress, InterfaceProfile: wire.InterfaceProfile, ProfileVersion: wire.ProfileVersion, ContentType: wire.ContentType, Operation: wire.Operation, ConflictPolicy: wire.ConflictPolicy, Readback: wire.Readback, CanonicalContentDigest: wire.CanonicalContentDigest, CanonicalFieldSchemaDigest: wire.CanonicalFieldSchemaDigest, SharedServiceRelationshipRef: wire.SharedServiceRelationshipRef, ConsumerTenantRef: wire.ConsumerTenantRef, MutableStateOwner: wire.MutableStateOwner, ResetGenerationOwner: wire.ResetGenerationOwner, ReadbackAssertionAddresses: wire.ReadbackAssertionAddresses, EvidenceRequirementRefs: wire.EvidenceRequirementRefs, ObservationBoundaryAddresses: wire.ObservationBoundaryAddresses, FieldSemantics: wire.FieldSemantics}
	return facts, wire, dependencies, nil
}
func (state *compilerState) materializationServiceTarget(ref string) (string, string) {
	nodes := fieldValue(state.input.model.Nodes)
	nodeName, serviceName := "", ""
	for _, name := range orderedNames(nodes, state.names(termNodes)) {
		for _, service := range fieldValue(nodes[name].Services) {
			candidate := rawString(fieldValue(service.Name))
			if candidate != "" && ref == "nodes."+name+".services."+candidate {
				nodeName, serviceName = name, candidate
				break
			}
		}
	}
	return nodeName, serviceName
}
func (state *compilerState) materializationServiceRelationship(ref string, wire *serviceMaterializationWire) {
	if ref != "" {
		relationName := state.sectionName(ref, "relationships")
		relation := fieldValue(state.input.model.Relationships)[relationName]
		var detail struct {
			MutableStateOwner    string `json:"mutable_state_owner"`
			ResetGenerationOwner string `json:"reset_generation_owner"`
		}
		if raw := fieldValue(relation.SharedService); len(raw) > 0 && string(raw) != termNull {
			if err := json.Unmarshal(raw, &detail); err != nil {
				state.err = invalidCompiled()
				return
			}
			wire.ConsumerTenantRef = strings.TrimPrefix(fieldValue(relation.Source), "deployment_tenants.")
			wire.MutableStateOwner = detail.MutableStateOwner
			wire.ResetGenerationOwner = detail.ResetGenerationOwner
		}
	}
}

func (state *compilerState) canonicalDigest(raw []byte) string {
	canonical, err := canonjson.JCS(raw)
	if err != nil {
		state.err = invalidCompiled()
		return ""
	}
	return digest.SHA256(canonical)
}

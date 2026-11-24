package planning

import (
	"encoding/json"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
)

const preparationContract = "backend-realization-preparation-v1"

type preparationAuthority struct {
	Contract       string          `json:"contract_id"`
	ManifestDigest string          `json:"manifest_digest"`
	NodeCollection json.RawMessage `json:"node_collection,omitempty"`
}

func (plan *executionPlan) attachPreparation(model processor.CompiledScenario, entries map[string]snapshotEntry) ([]diagnostic.Diagnostic, error) {
	if !slices.Contains(fieldValue(plan.manifest.SupportedContractVersions), preparationContract) {
		return nil, nil
	}
	owner, err := planOwner()
	if err != nil {
		return nil, err
	}
	normalized, err := admission.NormalizeBackendManifest(owner, plan.manifest)
	if err != nil {
		return nil, err
	}
	canonical, err := canonjson.JCS(rawProjection(normalized))
	if err != nil {
		return nil, err
	}
	authority := preparationAuthority{Contract: preparationContract, ManifestDigest: digest.SHA256(canonical)}
	members, err := plan.collectionMembers(entries, "")
	if err != nil {
		return nil, err
	}
	collection, err := realization.CompileNodeCollection(model.Original, members)
	if err != nil {
		if category, _ := fault.CategoryOf(err); category != fault.InvalidInput {
			return nil, err
		}
		plan.preparation = rawProjection(authority)
		return []diagnostic.Diagnostic{planDiagnostic("realization.invalid-node-collection", termProvisioning, "nodes", "Portable node membership cannot be represented by a bounded collection authority.")}, nil
	}
	if collection != nil {
		authority.NodeCollection = rawProjection(collection.Document())
		if err := plan.retainOpenCollectionNodes(collection, entries); err != nil {
			return nil, err
		}
	}
	plan.preparation = rawProjection(authority)
	return nil, nil
}

func (plan *executionPlan) collectionMembers(entries map[string]snapshotEntry, retainDeleted string) ([]realization.NodeCollectionMember, error) {
	members := []realization.NodeCollectionMember{}
	for _, operation := range plan.operations[termProvisioning] {
		if operation.Action == termDelete && operation.Address != retainDeleted {
			continue
		}
		resource, exists := plan.resources[operation.Address]
		if exists {
			members = append(members, realization.NodeCollectionMember{Address: operation.Address, Kind: operation.Kind, Name: resource.facts.Name})
			continue
		}
		member, err := snapshotCollectionMember(entries[operation.Address])
		if err != nil {
			return nil, err
		}
		members = append(members, member)
	}
	return members, nil
}
func (plan *executionPlan) retainOpenCollectionNodes(authority admission.Fragment, entries map[string]snapshotEntry) error {
	kept := make([]planOperation, 0, len(plan.operations[termProvisioning]))
	for _, operation := range plan.operations[termProvisioning] {
		if operation.Action != termDelete || operation.Kind != termNode && operation.Kind != termNetwork {
			kept = append(kept, operation)
			continue
		}
		members, err := plan.collectionMembers(entries, operation.Address)
		if err != nil {
			return err
		}
		admitted, err := realization.NodeCollectionAdmits(authority, members)
		if err != nil {
			return err
		}
		if !admitted {
			kept = append(kept, operation)
		}
	}
	plan.operations[termProvisioning] = kept
	return nil
}

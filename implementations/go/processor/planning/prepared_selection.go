package planning

import (
	"bytes"
	"encoding/json"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/domain"
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
)

// PreparedSelection is an owner-issued supported choice under the original plan.
type PreparedSelection interface {
	Provisioning() binding.ProvisioningPlanV1
	preparedSelection()
}
type preparedSelection struct {
	original             *executionPlan
	selected             binding.ProvisioningPlanV1
	operations           []planOperation
	authorities          []realization.Authority
	authorityByAddress   map[string][]realization.Authority
	requirementByConcern map[preparedConcernKey]realization.Requirement
	nodePresence         map[string]map[string][]string
	concernPaths         map[string][]string
}

type preparedConcernKey struct{ address, fieldPath, kind string }

func (*preparedSelection) preparedSelection() {
	// This unexported marker seals the handle to its native owner.
}
func (selection *preparedSelection) Provisioning() binding.ProvisioningPlanV1 {
	return copyTransport(selection.selected)
}

// CheckPreparedSelection binds a supported choice to the exact original plan,
// its independent target, and the retained predecessor. A violation returns no
// handle; admission asserts neither delivery nor execution.
//
//nolint:ireturn // This API returns an opaque native admission handle.
func CheckPreparedSelection(original ExecutionPlan, selected binding.ProvisioningPlanV1) (PreparedSelection, string, error) {
	plan, ok := original.(*executionPlan)
	if !ok || plan == nil || !plan.Valid() || len(plan.preparation) == 0 {
		return nil, "", invalidPlan()
	}
	if err := admission.CheckPreparationOperations(selected); err != nil {
		return nil, "", err
	}
	if err := checkTransport("provisioning-plan-v1", selected); err != nil {
		return nil, "", err
	}
	operations, err := preparedOperations(selected)
	if err != nil {
		return nil, "", err
	}
	selection := &preparedSelection{original: plan, selected: copyTransport(selected), operations: operations}
	selection.indexAuthority()
	violation, err := selection.profileViolation()
	if err != nil || violation != "" {
		return nil, violation, err
	}
	violation, err = selection.authorityViolation()
	if err != nil || violation != "" {
		return nil, violation, err
	}
	violation, err = selection.realizationViolation()
	if err != nil || violation != "" {
		return nil, violation, err
	}
	return selection, "", nil
}

func (selection *preparedSelection) indexAuthority() {
	view := selection.original.model.View()
	selection.authorities = view.RealizationAuthority
	selection.authorityByAddress = map[string][]realization.Authority{}
	selection.requirementByConcern = map[preparedConcernKey]realization.Requirement{}
	selection.nodePresence = map[string]map[string][]string{}
	selection.concernPaths = map[string][]string{}
	for _, descriptor := range realization.ConcernDescriptors() {
		selection.concernPaths[descriptor.Kind] = descriptor.AuthoredPath
	}
	for _, authority := range selection.authorities {
		selection.authorityByAddress[authority.Address] = append(selection.authorityByAddress[authority.Address], authority)
	}
	for _, requirement := range view.RealizationRequirements {
		selection.requirementByConcern[preparedConcernKey{requirement.Address, requirement.FieldPath, requirement.Kind}] = requirement
	}
}
func preparedOperations(selected binding.ProvisioningPlanV1) ([]planOperation, error) {
	raw, err := json.Marshal(fieldValue(selected.Operations))
	if err != nil {
		return nil, invalidPlan()
	}
	var operations []planOperation
	if json.Unmarshal(raw, &operations) != nil {
		return nil, invalidPlan()
	}
	return operations, nil
}
func preparedPayload(raw []byte) (map[string]any, error) {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var result map[string]any
	if decoder.Decode(&result) != nil {
		return nil, invalidPlan()
	}
	return result, nil
}
func (selection *preparedSelection) authorityViolation() (string, error) {
	before, err := preparedPayload(rawProjection(selection.original.provisioning))
	if err != nil {
		return "", err
	}
	after, err := preparedPayload(rawProjection(selection.selected))
	if err != nil {
		return "", err
	}
	delete(before, "operations")
	delete(after, "operations")
	if !preparedJSONEqual(before, after) {
		return "Backend preparation changed submitted operation authority.", nil
	}
	candidates := map[string]planOperation{}
	for _, operation := range selection.operations {
		candidates[operation.Address] = operation
	}
	for _, operation := range selection.original.operations[termProvisioning] {
		candidate, exists := candidates[operation.Address]
		if !exists {
			return "Backend preparation omitted a submitted operation.", nil
		}
		operation.Payload = nil
		candidate.Payload = nil
		operation.Profiles = nil
		candidate.Profiles = nil
		first, err := preparedPayload(rawProjection(operation))
		if err != nil {
			return "", err
		}
		second, err := preparedPayload(rawProjection(candidate))
		if err != nil {
			return "", err
		}
		if !preparedJSONEqual(first, second) {
			return "Backend preparation changed submitted operation authority.", nil
		}
	}
	return selection.collectionViolation()
}
func (selection *preparedSelection) realizationViolation() (string, error) {
	candidates := map[string]planOperation{}
	for _, operation := range selection.operations {
		candidates[operation.Address] = operation
	}
	for _, operation := range selection.original.operations[termProvisioning] {
		candidate := candidates[operation.Address]
		before, err := preparedPayload(operation.Payload)
		if err != nil {
			return "", err
		}
		after, err := preparedPayload(candidate.Payload)
		if err != nil {
			return "", err
		}
		violation, err := selection.operationRealizationViolation(operation.Address, before, after)
		if err != nil || violation != "" {
			return violation, err
		}
	}
	return selection.offerViolation()
}
func (selection *preparedSelection) operationRealizationViolation(address string, before, after map[string]any) (string, error) {
	for _, authority := range selection.authorityByAddress[address] {
		if authority.Posture == "closed" {
			continue
		}
		violation, err := selection.preparedAuthorityValueViolation(authority, before, after)
		if err != nil || violation != "" {
			return violation, err
		}
	}
	if !preparedJSONEqual(before, after) {
		return "Backend preparation changed a value outside realization authority.", nil
	}
	return "", nil
}
func (selection *preparedSelection) preparedAuthorityValueViolation(authority realization.Authority, before, after map[string]any) (string, error) {
	expected, hasExpected := preparedPointer(before, authority.PayloadPath)
	actual, hasActual := preparedPointer(after, authority.PayloadPath)
	if !hasActual {
		if hasExpected {
			return "Backend preparation omitted a declared concern.", nil
		}
		return "", nil
	}
	requirement, found := selection.requirementByConcern[preparedConcernKey{authority.Address, authority.FieldPath, authority.Concern}]
	if !found {
		return "", invalidPlan()
	}
	admitted, err := preparedConcernAdmits(requirement, expected, actual)
	if err != nil {
		return "", err
	}
	if !admitted {
		return "Backend preparation does not satisfy the recursive constraints.", nil
	}
	removePreparedPointer(before, authority.PayloadPath)
	removePreparedPointer(after, authority.PayloadPath)
	return "", nil
}

func preparedConcernAdmits(requirement realization.Requirement, expected, actual any) (bool, error) {
	owner, err := planOwner()
	if err != nil {
		return false, err
	}
	before, err := admission.AdmitFragment(owner, admission.RealizationValue, expected, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	if err != nil {
		return false, err
	}
	after, err := admission.AdmitFragment(owner, admission.RealizationValue, actual, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	if err != nil {
		return false, err
	}
	return realization.SelectionAdmits(requirement, before, after)
}
func preparedPointer(root map[string]any, path []string) (any, bool) {
	var current any = root
	for _, token := range path {
		record, ok := current.(map[string]any)
		if !ok {
			return nil, false
		}
		child, present := record[token]
		if !present {
			return nil, false
		}
		current = child
	}
	return current, true
}
func removePreparedPointer(root map[string]any, path []string) {
	if len(path) == 0 {
		return
	}
	for _, token := range path[:len(path)-1] {
		child, ok := root[token].(map[string]any)
		if !ok {
			return
		}
		root = child
	}
	delete(root, path[len(path)-1])
}
func preparedJSONEqual(before, after any) bool {
	switch first := before.(type) {
	case nil:
		return after == nil
	case map[string]any:
		return preparedMapEqual(first, after)
	case []any:
		return preparedSequenceEqual(first, after)
	default:
		return domain.Equal(before, after)
	}
}
func preparedMapEqual(first map[string]any, input any) bool {
	second, ok := input.(map[string]any)
	if !ok || len(first) != len(second) {
		return false
	}
	for key, item := range first {
		value, present := second[key]
		if !present || !preparedJSONEqual(item, value) {
			return false
		}
	}
	return true
}
func preparedSequenceEqual(first []any, input any) bool {
	second, ok := input.([]any)
	if !ok || len(first) != len(second) {
		return false
	}
	for i, item := range first {
		if !preparedJSONEqual(item, second[i]) {
			return false
		}
	}
	return true
}

func (selection *preparedSelection) collectionViolation() (string, error) {
	extra := selection.extraOperations()
	var preparation preparationAuthority
	if json.Unmarshal(selection.original.preparation, &preparation) != nil {
		return "", invalidPlan()
	}
	if len(preparation.NodeCollection) == 0 {
		if len(extra) > 0 {
			return "Backend preparation has no enclosing collection authority.", nil
		}
		return "", nil
	}
	for _, operation := range extra {
		if operation.Kind != termNode && operation.Kind != termNetwork {
			return "Backend preparation exceeded its portable node collection universe.", nil
		}
	}
	violation, err := selection.collectionMembershipViolation(preparation)
	if err != nil || violation != "" {
		return violation, err
	}
	return selection.portableNodeViolation()
}
func (selection *preparedSelection) extraOperations() []planOperation {
	originals := map[string]bool{}
	for _, operation := range selection.original.operations[termProvisioning] {
		originals[operation.Address] = true
	}
	extra := []planOperation{}
	for _, operation := range selection.operations {
		if !originals[operation.Address] {
			extra = append(extra, operation)
		}
	}
	return extra
}
func (selection *preparedSelection) collectionMembershipViolation(preparation preparationAuthority) (string, error) {
	owner, err := planOwner()
	if err != nil {
		return "", err
	}
	document, err := planRawValue(preparation.NodeCollection)
	if err != nil {
		return "", err
	}
	authority, err := admission.AdmitFragment(owner, admission.PortableNodeCollectionAuthority, document, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	if err != nil {
		return "", err
	}
	members, err := selection.liveCollectionMembers()
	if err != nil {
		return "", err
	}
	admitted, err := realization.NodeCollectionAdmits(authority, members)
	if err != nil {
		return "", err
	}
	if !admitted {
		return "Backend preparation does not satisfy enclosing node collection authority.", nil
	}
	return "", nil
}

func (selection *preparedSelection) liveCollectionMembers() ([]realization.NodeCollectionMember, error) {
	members := []realization.NodeCollectionMember{}
	submitted := map[string]bool{}
	for _, operation := range selection.operations {
		submitted[operation.Address] = true
		if operation.Action == termDelete {
			continue
		}
		member, err := snapshotCollectionMember(snapshotEntry{Address: operation.Address, Kind: operation.Kind, Payload: operation.Payload})
		if err != nil {
			return nil, err
		}
		members = append(members, member)
	}
	for address, raw := range fieldValue(selection.original.context.Snapshot.Entries) {
		if submitted[address] {
			continue
		}
		var entry snapshotEntry
		if json.Unmarshal(raw, &entry) != nil {
			return nil, invalidPlan()
		}
		if entry.Domain != termProvisioning {
			continue
		}
		member, err := snapshotCollectionMember(entry)
		if err != nil {
			return nil, err
		}
		members = append(members, member)
	}
	return members, nil
}
func (selection *preparedSelection) profileViolation() (string, error) {
	bindings := []binding.DomainProfileBindingV1{}
	for _, operation := range selection.operations {
		for _, profile := range operation.Profiles {
			if operation.Action == termDelete || fieldValue(fieldValue(profile.Owner).CanonicalAddress) != "#/resources/"+operation.Address {
				return "Backend preparation changed a profile owner.", nil
			}
			bindings = append(bindings, profile)
		}
	}
	authority := selection.original.profileAuthority
	if authority == nil {
		if len(bindings) > 0 {
			return "Backend preparation invented profile authority.", nil
		}
		return "", nil
	}
	context := selection.original.context.ProfileContext
	if context == nil {
		return "Backend preparation returned invalid profile bindings.", nil
	}
	owner, err := planOwner()
	if err != nil {
		return "", err
	}
	admitted, err := admission.CheckPlanProfileSelection(owner, *authority, bindings, *context)
	if err != nil || !admitted {
		return "Backend preparation returned invalid profile bindings.", nil //nolint:nilerr // Candidate semantic refusal is reported as the stable relation violation.
	}
	return "", nil
}
func (selection *preparedSelection) offerViolation() (string, error) {
	envelope := selection.original.context.RealizationEnvelope
	if envelope == nil {
		return "Backend preparation requires a selected realization envelope.", nil
	}
	owner, err := planOwner()
	if err != nil {
		return "", err
	}
	operations := map[string]planOperation{}
	for _, operation := range selection.operations {
		operations[operation.Address] = operation
		if !selection.preparedOperationOperatingSystemSupported(operation) {
			return "Backend preparation selected an unsupported joint operating-system identity.", nil
		}
	}
	for _, authority := range selection.authorities {
		operation, present := operations[authority.Address]
		if !present {
			return "Backend preparation omitted an offered realization dimension.", nil
		}
		admitted, err := selection.preparedOperationOffer(owner, *envelope, authority, operation)
		if err != nil {
			return "", err
		}
		if !admitted {
			return "Backend preparation selected a value outside its configured offer.", nil
		}
	}
	return "", nil
}

func (selection *preparedSelection) preparedOperationOperatingSystemSupported(operation planOperation) bool {
	if operation.Kind != termNode {
		return true
	}
	payload, err := preparedPayload(operation.Payload)
	return err == nil && preparedOperatingSystemSupported(payload, selection.original.manifest)
}

func (selection *preparedSelection) preparedOperationOffer(owner *admission.Validator, envelope binding.RealizationEnvelopeV1, authority realization.Authority, operation planOperation) (bool, error) {
	payload, err := preparedPayload(operation.Payload)
	if err != nil {
		return false, err
	}
	selected, _ := preparedPointer(payload, authority.PayloadPath)
	fragment, err := admission.AdmitFragment(owner, admission.RealizationValue, selected, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	if err != nil {
		return false, err
	}
	presence, err := selection.preparedOfferPresence(authority, payload)
	if err != nil {
		return false, err
	}
	return admission.RealizationOfferAdmits(owner, envelope, authority.FieldPath, fragment, presence)
}

func (selection *preparedSelection) preparedOfferPresence(authority realization.Authority, payload map[string]any) (map[string][]string, error) {
	authored := selection.concernPaths[authority.Concern]
	if len(authored) == 0 || authored[0] != "runtime" {
		return nil, nil //nolint:nilnil // Scalar and non-runtime concerns have no typed presence view.
	}
	presence, found := selection.nodePresence[authority.Address]
	if !found {
		name, ok := payload["name"].(string)
		if !ok {
			return nil, invalidPlan()
		}
		node, _ := preparedPointer(payload, []string{"spec", termNode})
		_, _, nativePresence, err := compilePortableNode(node, name, authority.Address)
		if err != nil {
			return nil, err
		}
		presence = nativePresence
		selection.nodePresence[authority.Address] = presence
	}
	prefix := strings.Join(authored, ".")
	rebased := map[string][]string{}
	for path, fields := range presence {
		if path == prefix || strings.HasPrefix(path, prefix+".") || strings.HasPrefix(path, prefix+"[") {
			rebased[strings.TrimPrefix(strings.TrimPrefix(path, prefix), ".")] = fields
		}
	}
	return rebased, nil
}

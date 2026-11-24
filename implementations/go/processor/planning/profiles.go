package planning

import (
	"encoding/json"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
)

func prepareProfiles(view processor.CompiledScenario, manifest binding.BackendManifestV2, context *binding.DomainProfileResolutionContextV1, resources map[string]plannedResource, snapshot map[string]snapshotEntry) (*binding.PlanRealizationProfilesV1, []diagnostic.Diagnostic, error) {
	owner, err := planOwner()
	if err != nil {
		return nil, nil, err
	}
	findings := []diagnostic.Diagnostic{}
	var digest string
	if context != nil {
		digest, err = admission.DomainProfileContextDigest(owner, *context)
		if err != nil {
			return nil, nil, err
		}
	}
	var committed string
	_ = json.Unmarshal(fieldValue(manifest.DomainProfileContextDigest), &committed)
	descriptorFindings, err := descriptorProfileDiagnostics(owner, view.DescriptorProfiles, context, digest == committed)
	if err != nil {
		return nil, nil, err
	}
	findings = append(findings, descriptorFindings...)
	refusal := planDiagnostic("realization.profile-unsupported", termProvisioning, "profiles", "Plan profiles lack supported, pinned target authority.")
	authored, valid := authoredPlanProfiles(view.Resources)
	if !valid {
		return view.ProfileAuthority, append(findings, refusal), nil
	}
	authority, err := admission.ResolvePlanProfileAuthority(owner, authored, view.ProfileAuthority, context)
	if err != nil {
		return view.ProfileAuthority, append(findings, refusal), nil //nolint:nilerr // This relation reports candidate refusal in its result without failing the enclosing operation.
	}
	if authority == nil {
		return nil, findings, nil
	}
	if !profileTargetAdmitted(context, digest, committed, fieldValue(manifest.SupportedContractVersions)) {
		return authority, append(findings, refusal), nil
	}
	valid, err = admission.CheckPlanProfileAuthority(owner, *authority, *context)
	if err != nil || !valid {
		return authority, append(findings, refusal), nil //nolint:nilerr // This relation reports candidate refusal in its result without failing the enclosing operation.
	}
	byAddress, valid, err := planProfileOwners(authority, resources)
	if err != nil {
		return nil, nil, err
	}
	if !valid {
		return authority, append(findings, refusal), nil
	}
	previous := previousPlanProfiles(byAddress, snapshot)
	retain, err := admission.CheckPlanProfileSelection(owner, *authority, previous, *context)
	if err != nil {
		retain = false
	}
	if !assignPlanProfiles(resources, snapshot, byAddress, retain) {
		return authority, append(findings, refusal), nil
	}
	return authority, findings, nil
}

func descriptorProfileDiagnostics(owner *admission.Validator, selections []binding.DomainProfileBindingV1, context *binding.DomainProfileResolutionContextV1, committed bool) ([]diagnostic.Diagnostic, error) {
	if len(selections) == 0 {
		return nil, nil
	}
	admitted := context != nil && committed
	var policy binding.DomainProfileAdmissionPolicyV1
	if json.Unmarshal([]byte(`{}`), &policy) != nil {
		return nil, invalidPlan()
	}
	for _, selected := range selections {
		if !admitted {
			break
		}
		var err error
		admitted, err = admission.CheckDomainProfileBindings(owner, []binding.DomainProfileBindingV1{selected}, *context, policy)
		if err != nil {
			return nil, err
		}
	}
	if admitted {
		return nil, nil
	}
	return []diagnostic.Diagnostic{planDiagnostic("realization.descriptor-profile-unsupported", "runtime-realization", "profiles.descriptors", "Typed descriptor profiles lack admission by the target profile context.")}, nil
}
func authoredPlanProfiles(resources []processor.Resource) ([]binding.DomainProfileBindingV1, bool) {
	authored, domains := []binding.DomainProfileBindingV1{}, []binding.DomainProfileBindingV1{}
	for _, resource := range resources {
		for _, selected := range resource.SelectedProfiles {
			if !authoredProfileOwner(resource, selected) {
				return nil, false
			}
			if resource.Kind == "domain-controller-placement" {
				domains = append(domains, selected)
			} else {
				authored = append(authored, selected)
			}
		}
	}
	return append(authored, domains...), true
}
func planProfileOwners(authority *binding.PlanRealizationProfilesV1, resources map[string]plannedResource) (map[string][]binding.DomainProfileBindingV1, bool, error) {
	byAddress := map[string][]binding.DomainProfileBindingV1{}
	for _, raw := range fieldValue(authority.Bindings) {
		var selection binding.DomainProfileBindingV1
		projection := rawProjection(raw)
		if json.Unmarshal(projection, &selection) != nil {
			return nil, false, invalidPlan()
		}
		address, ok := strings.CutPrefix(fieldValue(fieldValue(selection.Owner).CanonicalAddress), "#/resources/")
		if _, exists := resources[address]; !ok || !exists {
			return nil, false, nil
		}
		byAddress[address] = append(byAddress[address], selection)
	}
	return byAddress, true, nil
}
func assignPlanProfiles(resources map[string]plannedResource, snapshot map[string]snapshotEntry, byAddress map[string][]binding.DomainProfileBindingV1, retain bool) bool {
	for address, selected := range byAddress {
		if retain {
			entry, present := snapshot[address]
			if !present {
				return false
			}
			selected = entry.Profiles
		}
		resource := resources[address]
		resource.profiles = copyTransport(selected)
		resources[address] = resource
	}
	return true
}

func authoredProfileOwner(resource processor.Resource, selected binding.DomainProfileBindingV1) bool {
	context, known := map[string]string{"account-placement": "account-materialization", termContentPlacement: "service-materialization", termGeneratedArtifact: "artifact-generation", "domain-controller-placement": "identity-domain"}[resource.Kind]
	owner := fieldValue(selected.Owner)
	return known && fieldValue(owner.CanonicalAddress) == "#/resources/"+resource.Address && fieldValue(owner.Context) == context && fieldValue(owner.OwningContractId) == "plan-realization-profiles-v1" && fieldValue(owner.ConceptFamily) == "resource-realization" && fieldValue(owner.LifecyclePhase) == "planning" && string(fieldValue(owner.Use)) == "constraint" && string(fieldValue(fieldValue(selected.Provenance).Basis)) == "author-supplied"
}

func profileTargetAdmitted(context *binding.DomainProfileResolutionContextV1, digest, committed string, versions []string) bool {
	if context == nil || digest != committed {
		return false
	}
	available := map[string]bool{}
	for _, version := range versions {
		available[version] = true
	}
	return available["plan-realization-profiles-v1"] && available[preparationContract]
}

func previousPlanProfiles(byAddress map[string][]binding.DomainProfileBindingV1, snapshot map[string]snapshotEntry) []binding.DomainProfileBindingV1 {
	previous := []binding.DomainProfileBindingV1{}
	for address := range byAddress {
		previous = append(previous, snapshot[address].Profiles...)
	}
	return previous
}

package processor

import (
	"bytes"
	"encoding/json"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func (state *compilerState) compileSelectedProfiles() {
	if state.err != nil {
		return
	}
	var err error
	state.model.DescriptorProfiles, err = sdl.DescriptorProfiles(state.input.scenario)
	if err != nil {
		state.err = err
		return
	}
	state.model.ProfileAuthority, err = realization.CompileSoftwareProfiles(state.input.scenario, state.model.ProfileAuthority)
	if err != nil {
		state.err = err
		return
	}
	for i := range state.model.Resources {
		resource := &state.model.Resources[i]
		resource.SelectedProfiles = []binding.DomainProfileBindingV1{}
		selected, err := state.selectedPlacementProfile(resource)
		if err != nil {
			state.err = err
			return
		}
		if selected != nil {
			resource.SelectedProfiles = append(resource.SelectedProfiles, copyTransport(*selected))
		}
	}
	state.compileDomainProfileSelections()
}

func (state *compilerState) selectedPlacementProfile(resource *Resource) (*binding.DomainProfileBindingV1, error) {
	switch resource.Kind {
	case termAccountPlacement:
		raw := fieldValue(fieldValue(state.input.model.Accounts)[resource.Name].MaterializationProfile)
		if len(raw) == 0 || bytes.Equal(raw, []byte(termNull)) {
			return nil, nil //nolint:nilnil // Absence is distinct from malformed authored selection.
		}
		var selection binding.DomainProfileBindingV1
		if json.Unmarshal(raw, &selection) != nil {
			return nil, invalidCompiled()
		}
		return &selection, nil
	case termGeneratedArtifact:
		if resource.Artifact != nil {
			return resource.Artifact.GeneratorBinding, nil
		}
	case termContentPlacement:
		if resource.ServiceMaterialization != nil {
			return resource.ServiceMaterialization.ProfileBinding, nil
		}
	}
	return nil, nil //nolint:nilnil // Resource kinds without authored placement profiles have no selection.
}

func (state *compilerState) compileDomainProfileSelections() {
	byAddress := make(map[string]int, len(state.model.Resources))
	for i, resource := range state.model.Resources {
		byAddress[resource.Address] = i
	}
	seen := map[string]bool{}
	for i, resource := range state.model.Resources {
		if resource.Kind != termDomainControllerPlacement || resource.Topology == nil || resource.Topology.ProfileBinding == nil {
			continue
		}
		selected := resource.Topology.ProfileBinding
		address := strings.TrimPrefix(fieldValue(fieldValue(selected.Owner).CanonicalAddress), "#/resources/")
		target, owned := state.domainProfileOwner(byAddress, address, resource.Topology.DomainID, i)
		if owned && seen[address] {
			continue
		}
		if owned {
			seen[address] = true
		}
		state.model.Resources[target].SelectedProfiles = append(state.model.Resources[target].SelectedProfiles, copyTransport(*selected))
	}
}

func (state *compilerState) domainProfileOwner(byAddress map[string]int, address, domain string, fallback int) (int, bool) {
	index, exists := byAddress[address]
	if !exists {
		return fallback, false
	}
	owner := state.model.Resources[index]
	if owner.Kind != termDomainControllerPlacement || owner.Topology == nil || owner.Topology.DomainID != domain {
		return fallback, false
	}
	return index, true
}

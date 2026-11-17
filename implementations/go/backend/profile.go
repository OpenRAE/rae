package backend

import (
	"encoding/json"
	"regexp"
	"sync"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/profile"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

var profileID = regexp.MustCompile(`^[a-z0-9]+(?:-[a-z0-9]+)*$`)
var backendProfiles = sync.OnceValues(loadProfiles) //nolint:gochecknoglobals // Only immutable packaged contracts are shared; request state remains local.

// LoadProfile returns an independently owned published profile from the offline corpus.
func LoadProfile(id string) (binding.BackendProfileV1, error) {
	if !profileID.MatchString(id) {
		return binding.BackendProfileV1{}, fault.New(fault.InvalidInput, "backend-profile-id-invalid", nil)
	}
	profiles, err := backendProfiles()
	if err != nil {
		return binding.BackendProfileV1{}, err
	}
	raw, ok := profiles[id]
	if !ok {
		return binding.BackendProfileV1{}, fault.New(fault.NotFound, "backend-profile-not-found", nil)
	}
	var result binding.BackendProfileV1
	if err := json.Unmarshal(raw, &result); err != nil {
		return binding.BackendProfileV1{}, fault.New(fault.Operational, "backend-profile-invalid", nil)
	}
	return result, nil
}

func loadProfiles() (map[string][]byte, error) {
	schemas, err := validation.New(nil)
	if err != nil {
		return nil, err
	}
	validator, err := admission.NewWithSchemas(schemas)
	if err != nil {
		return nil, err
	}
	profiles, err := profile.Load(schemas)
	if err != nil {
		return nil, err
	}
	result := map[string][]byte{}
	for _, document := range profiles.Documents() {
		if document.ContractID != "backend-profile-v1" {
			continue
		}
		if err := validator.CheckPortable(document.ContractID, document.JSON, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}); err != nil {
			return nil, fault.New(fault.Operational, "backend-profile-invalid", nil)
		}
		var payload binding.BackendProfileV1
		if err := json.Unmarshal(document.JSON, &payload); err != nil {
			return nil, fault.New(fault.Operational, "backend-profile-invalid", nil)
		}
		id, ok := payload.Profile.Value()
		if !ok || document.Path != "profiles/backend/"+id+".json" || !profileID.MatchString(id) {
			return nil, fault.New(fault.Operational, "backend-profile-identity-invalid", nil)
		}
		if _, exists := result[id]; exists {
			return nil, fault.New(fault.Operational, "backend-profile-identity-invalid", nil)
		}
		result[id] = document.JSON
	}
	return result, nil
}

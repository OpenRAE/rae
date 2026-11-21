package parity

import (
	"encoding/json"
	"errors"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

// solverIdentityComparison implements issue #1789's narrow identity exception.
// It verifies the fixed profiles and dependent digest before comparing all other fields.
func solverIdentityComparison(raw json.RawMessage, goResult bool) (json.RawMessage, error) {
	value, err := decodeResult(raw)
	if err != nil {
		return nil, err
	}
	envelope, ok := value.(map[string]any)
	if !ok {
		return nil, errors.New("analysis envelope is not an object")
	}
	if envelope["stdout"] == nil {
		return raw, nil
	}
	evidence, ok := envelope["stdout"].(map[string]any)
	if !ok {
		return nil, errors.New("analysis evidence is not an object")
	}
	config, ok := evidence["solver_configuration"].(map[string]any)
	if !ok {
		return nil, errors.New("solver identity is missing")
	}
	encoded, err := json.Marshal(config)
	if err != nil {
		return nil, err
	}
	owner, err := processorTargetOwner()
	if err != nil {
		return nil, err
	}
	if err = owner.CheckModelFragment("scenario-satisfiability-evidence-v2", "#/$defs/SolverConfigurationModel", encoded, ingress.Limits{MaxBytes: 16384, MaxDepth: 16}); err != nil {
		return nil, err
	}
	canonical, err := canonjson.JCS(encoded)
	if err != nil {
		return nil, err
	}
	if digest.SHA256(canonical) != evidence["solver_configuration_digest"] {
		return nil, errors.New("solver configuration digest mismatch")
	}
	expectedProfile := "raes-z3-finite-domain/v1"
	if goResult {
		expectedProfile = "raes-z3-finite-domain/v2"
	}
	if config[profileField] != expectedProfile {
		return nil, errors.New("unexpected solver profile")
	}
	for _, field := range []string{profileField, "package", "package_version"} {
		delete(config, field)
	}
	delete(evidence, "solver_configuration_digest")
	return json.Marshal(envelope)
}

package admission

import (
	"context"
	"encoding/json"
	"errors"
	"strings"
	"testing"
)

type configurationContextCheck func(context.Context, string, ControlContextSelection) error

func (f configurationContextCheck) ValidateControlContextReference(ctx context.Context, address string, selection ControlContextSelection) error {
	return f(ctx, address, selection)
}

func TestConfigurationControlContextRetainsExactPinsAndOwnerCancellation(t *testing.T) {
	var declaration declarationWire
	if err := json.Unmarshal([]byte(`{"target_id":"prompt","value_type":"string","allowed_value_kinds":["literal"],"control_context":{"slot_id":"system","references":{"control_context_assets.prompt":{"asset_id":"prompt","asset_version":"1","asset_digest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}}}`), &declaration); err != nil {
		t.Fatal(err)
	}
	value := BindingValue{Kind: "literal", Literal: "control_context_assets.prompt"}
	for _, test := range []string{"exact", "missing-owner", "wrong-type", "unresolved", "owner-error", "owner-cancelled"} {
		t.Run(test, func(t *testing.T) {
			checkConfigurationControlBoundary(t, declaration, value, test)
		})
	}
}

func TestConfigurationCopiesControlPinsAndRejectsDuplicateSlots(t *testing.T) {
	selection := &ControlContextSelection{SlotID: "system", DeclarationRef: "control_context_assets.prompt", AssetRef: ControlContextAssetReference{AssetID: "prompt", AssetVersion: "1", AssetDigest: "sha256:" + strings.Repeat("a", 64)}}
	configuration := ParticipantConfiguration{Values: []RealizedConfigurationValue{{TargetID: "prompt", ValueType: "string", Origin: "override", Value: BindingValue{Kind: "literal", Literal: "control_context_assets.prompt"}, ControlContextSelection: selection}}}
	copyValue := copyConfiguration(configuration)
	copyValue.Values[0].ControlContextSelection.AssetRef.AssetVersion = "changed"
	if selection.AssetRef.AssetVersion != "1" {
		t.Fatal("configuration copy retained writable context pins")
	}
	configuration.Values = append(configuration.Values, configuration.Values[0])
	configuration.Values[1].TargetID = "another-prompt"
	if err := configurationRequestBudget(ParticipantConfigurationRequest{}, configuration); err == nil {
		t.Fatal("two targets acquired the same control-context slot")
	}
	for _, raw := range []json.RawMessage{nil, json.RawMessage(`{`)} {
		declaration := declarationWire{TargetID: "required", ValueType: "string", AllowedValueKinds: []string{"literal"}, Default: raw}
		if _, err := realizeConfigurationValue(t.Context(), ParticipantConfigurationRequest{}, declaration, nil); err == nil {
			t.Fatal("missing or malformed default supplied a required target")
		}
	}
	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	validator := configurationNormalizer(func(context.Context, ParticipantConfiguration) (ParticipantConfiguration, error) {
		cancel()
		return ParticipantConfiguration{}, nil
	})
	if _, err := normalizeCompleteConfiguration(ctx, validator, ParticipantConfiguration{}, &registryWire{}); !errors.Is(err, context.Canceled) {
		t.Fatal("normalizer cancellation lost", err)
	}
}

func checkConfigurationControlBoundary(t *testing.T, declaration declarationWire, value BindingValue, test string) {
	t.Helper()

	ctx, cancel := context.WithCancel(t.Context())
	defer cancel()
	calls := 0
	request := ParticipantConfigurationRequest{ParticipantAddress: "participants.red", ControlContext: configurationBoundaryOwner(t, test, cancel, &calls)}
	selected := value
	switch test {
	case "missing-owner":
		request.ControlContext = nil
	case "wrong-type":
		selected.Literal = true
	case "unresolved":
		selected.Literal = "control_context_assets.foreign"
	}
	selection, err := validateConfigurationControl(ctx, request, declaration, selected)
	if (err == nil) != (test == "exact") {
		t.Fatal("control-context authority admission", err)
	}
	if test == "exact" && (selection == nil || calls != 1) {
		t.Fatal("context owner was not called exactly once")
	}
	if test == "owner-cancelled" && !errors.Is(err, context.Canceled) {
		t.Fatal("context owner cancellation lost", err)
	}
	if err != nil && strings.Contains(err.Error(), "private") {
		t.Fatal("context owner detail escaped")
	}
}

func configurationBoundaryOwner(t *testing.T, test string, cancel context.CancelFunc, calls *int) configurationContextCheck {
	t.Helper()
	return func(_ context.Context, address string, selection ControlContextSelection) error {
		*calls++
		if address != "participants.red" || selection.SlotID != "system" || selection.DeclarationRef != "control_context_assets.prompt" || selection.AssetRef.AssetID != "prompt" || selection.AssetRef.AssetVersion != "1" {
			t.Fatal("context authority changed")
		}
		if test == "owner-error" {
			return errors.New("private context detail")
		}
		if test == "owner-cancelled" {
			cancel()
		}
		return nil
	}
}

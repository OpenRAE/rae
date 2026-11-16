package admission

import (
	"context"
	"encoding/json"
	"errors"
	"math"
	"math/big"
	"os"
	"strconv"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func TestParticipantConfigurationMatchesIndependentReference(t *testing.T) {
	t.Parallel()
	data, err := os.ReadFile("testdata/participant-configuration-realization.json")
	if err != nil {
		t.Fatal(err)
	}
	var recording struct {
		Cases []participantConfigurationReferenceCase
	}
	if err := decodeExact(data, &recording); err != nil {
		t.Fatal(err)
	}
	if len(recording.Cases) != 10 {
		t.Fatal("case count =", len(recording.Cases), "want 10")
	}
	for _, c := range recording.Cases {
		t.Run(c.Name, func(t *testing.T) { checkParticipantConfigurationReference(t, c) })
	}
}

func configurationRequestFixture(t *testing.T) ParticipantConfigurationRequest {
	t.Helper()
	raw, err := os.ReadFile("../../../../contracts/fixtures/participant-implementation-manifest/participant-implementation-manifest-v1/valid/reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var manifest binding.ParticipantImplementationManifestV1
	if err := json.Unmarshal(raw, &manifest); err != nil {
		t.Fatal(err)
	}
	return ParticipantConfigurationRequest{ParticipantAddress: "participants.red", Manifest: manifest, ManifestRef: "reference", ManifestDigest: "sha256:" + strings.Repeat("1", 64), Overrides: []ConfigurationOverride{{TargetID: "mode", Value: BindingValue{Kind: "literal", Literal: "deterministic"}}, {TargetID: "credentials.api", Value: BindingValue{Kind: "secret-reference", ReferenceID: "operator-secret.reference-red-api"}}}}
}

func TestParticipantConfigurationAcceptsNativeNumbers(t *testing.T) {
	t.Parallel()
	for _, number := range []any{0.5, 1, json.Number("0.5"), big.NewInt(1)} {
		req := configurationRequestFixture(t)
		req.Overrides = append(req.Overrides, ConfigurationOverride{TargetID: "temperature", Value: BindingValue{Kind: "literal", Literal: number}})
		if _, err := RealizeParticipantConfiguration(context.Background(), req); err != nil {
			t.Fatalf("native %T refused: %v", number, err)
		}
	}
}

func TestParticipantConfigurationKeepsIntegerType(t *testing.T) {
	t.Parallel()
	for _, test := range []struct {
		Value any
		Valid bool
	}{{1, true}, {json.Number("1"), true}, {1.0, false}, {json.Number("1.0"), false}, {true, false}} {
		req := configurationRequestFixture(t)
		raw, err := json.Marshal(req.Manifest)
		if err != nil {
			t.Fatal(err)
		}
		var manifest map[string]any
		if decodeExact(raw, &manifest) != nil {
			t.Fatal("manifest decode failed")
		}
		object(at(manifest, "configuration_registry", "targets"))["count"] = map[string]any{"target_id": "count", "value_type": "integer", "allowed_value_kinds": []string{"literal"}, "sensitivity": "public"}
		raw, err = json.Marshal(manifest)
		if err != nil {
			t.Fatal(err)
		}
		if json.Unmarshal(raw, &req.Manifest) != nil {
			t.Fatal("manifest binding decode failed")
		}
		req.Overrides = append(req.Overrides, ConfigurationOverride{TargetID: "count", Value: BindingValue{Kind: "literal", Literal: test.Value}})
		_, err = RealizeParticipantConfiguration(context.Background(), req)
		if (err == nil) != test.Valid {
			t.Fatalf("integer admission for %T = %v, want %v", test.Value, err == nil, test.Valid)
		}
	}
}

type configurationNormalizer func(context.Context, ParticipantConfiguration) (ParticipantConfiguration, error)

func (f configurationNormalizer) ValidateAndNormalize(ctx context.Context, c ParticipantConfiguration) (ParticipantConfiguration, error) {
	return f(ctx, c)
}

func TestParticipantConfigurationRejectsChangedOwnerAuthority(t *testing.T) {
	t.Parallel()
	for _, field := range []string{"owner", "manifest", "identity", "target", termOrigin, "kind", "secret", "type", "incomplete", "order", "context"} {
		t.Run(field, func(t *testing.T) {
			req := configurationRequestFixture(t)
			req.Validator = configurationNormalizer(func(_ context.Context, c ParticipantConfiguration) (ParticipantConfiguration, error) {
				switch field {
				case "owner":
					c.Owner.ValidatorID = "other"
				case "manifest":
					c.ManifestVersion = "other"
				case "identity":
					c.ImplementationIdentity.Name = "other"
				case "target":
					c.Values[0].TargetID = "other"
				case termOrigin:
					c.Values[0].Origin = "default"
				case "kind":
					c.Values[0].Value = BindingValue{Kind: "literal", Literal: "private-marker"}
				case "secret":
					c.Values[0].Value.ReferenceID = "operator-secret.other"
				case "type":
					c.Values[0].ValueType = "number"
				case "incomplete":
					c.Values = c.Values[:1]
				case "order":
					c.Values[0], c.Values[1] = c.Values[1], c.Values[0]
				case "context":
					c.Values[0].ControlContextSelection = &ControlContextSelection{}
				}
				return c, nil
			})
			if _, err := RealizeParticipantConfiguration(context.Background(), req); err == nil {
				t.Fatal("changed owner authority admitted")
			}
		})
	}
}

func TestParticipantConfigurationRefusesUnsafeValuesAndOwnerErrors(t *testing.T) {
	t.Parallel()
	for _, bad := range []any{math.NaN(), math.Inf(1), map[string]any{"private-marker": true}, []any{1}, make(chan int)} {
		req := configurationRequestFixture(t)
		req.Overrides[0].Value.Literal = bad
		if _, err := RealizeParticipantConfiguration(context.Background(), req); err == nil {
			t.Fatalf("unsafe %T admitted", bad)
		}
	}
	req := configurationRequestFixture(t)
	req.Validator = configurationNormalizer(func(context.Context, ParticipantConfiguration) (ParticipantConfiguration, error) {
		return ParticipantConfiguration{}, errors.New("private-marker")
	})
	if _, err := RealizeParticipantConfiguration(context.Background(), req); err == nil || strings.Contains(err.Error(), "private-marker") {
		t.Fatal("foreign failure was not isolated")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := RealizeParticipantConfiguration(ctx, configurationRequestFixture(t)); !errors.Is(err, context.Canceled) {
		t.Fatal("canceled request error =", err, "want context.Canceled")
	}
}

func TestParticipantConfigurationIsolatesInstalledNormalizerPanic(t *testing.T) {
	req := configurationRequestFixture(t)
	req.Validator = configurationNormalizer(func(context.Context, ParticipantConfiguration) (ParticipantConfiguration, error) {
		panic("private-marker")
	})
	_, err := RealizeParticipantConfiguration(context.Background(), req)
	category, known := fault.CategoryOf(err)
	if !known || category != fault.Operational || strings.Contains(err.Error(), "private-marker") {
		t.Fatal("installed owner panic was not isolated", err)
	}
}
func TestParticipantConfigurationBoundsAggregateBeforeInstalledOwner(t *testing.T) {
	req := configurationRequestFixture(t)
	raw, err := json.Marshal(req.Manifest)
	if err != nil {
		t.Fatal(err)
	}
	var manifest map[string]any
	if decodeExact(raw, &manifest) != nil {
		t.Fatal("bad manifest fixture")
	}
	targets := object(at(manifest, "configuration_registry", "targets"))
	large := strings.Repeat("x", 1<<20)
	for index := range 9 {
		id := "large." + strconv.Itoa(index)
		targets[id] = map[string]any{"target_id": id, "value_type": "string", "allowed_value_kinds": []any{"literal"}, "sensitivity": "public"}
		req.Overrides = append(req.Overrides, ConfigurationOverride{TargetID: id, Value: BindingValue{Kind: "literal", Literal: large}})
	}
	raw, err = json.Marshal(manifest)
	if err != nil {
		t.Fatal(err)
	}
	if json.Unmarshal(raw, &req.Manifest) != nil {
		t.Fatal("bad manifest binding")
	}
	called := false
	req.Validator = configurationNormalizer(func(_ context.Context, c ParticipantConfiguration) (ParticipantConfiguration, error) {
		called = true
		return c, nil
	})
	_, err = RealizeParticipantConfiguration(context.Background(), req)
	if err == nil || called {
		t.Fatal("oversized aggregate reached installed normalizer", called, err)
	}
}

func TestParticipantConfigurationBoundsHeadersBeforeNormalizer(t *testing.T) {
	req := configurationRequestFixture(t)
	req.ManifestRef = strings.Repeat("x", bindingTargetsMaxSize)
	called := false
	req.Validator = configurationNormalizer(func(_ context.Context, c ParticipantConfiguration) (ParticipantConfiguration, error) {
		called = true
		return c, nil
	})
	_, err := RealizeParticipantConfiguration(context.Background(), req)
	if err == nil || called {
		t.Fatal("oversized request reached normalizer", called, err)
	}
}

type participantConfigurationReferenceCase struct {
	Name    string
	Request struct {
		ParticipantAddress string `json:"participant_address"`
		Manifest           binding.ParticipantImplementationManifestV1
		ManifestRef        string `json:"manifest_ref"`
		ManifestDigest     string `json:"manifest_digest"`
		Overrides          []struct {
			TargetID string `json:"target_id"`
			Value    struct {
				Kind        string
				Value       any
				ReferenceID string `json:"reference_id"`
			}
		}
	}
	Result json.RawMessage
}

func checkParticipantConfigurationReference(t *testing.T, c participantConfigurationReferenceCase) {
	t.Helper()

	req := ParticipantConfigurationRequest{ParticipantAddress: c.Request.ParticipantAddress, Manifest: c.Request.Manifest, ManifestRef: c.Request.ManifestRef, ManifestDigest: c.Request.ManifestDigest}
	for _, override := range c.Request.Overrides {
		req.Overrides = append(req.Overrides, ConfigurationOverride{TargetID: override.TargetID, Value: BindingValue{Kind: override.Value.Kind, Literal: override.Value.Value, ReferenceID: override.Value.ReferenceID}})
	}
	result, err := RealizeParticipantConfiguration(context.Background(), req)
	if string(c.Result) == termNull {
		if err == nil {
			t.Fatal("invalid configuration admitted")
		}
		if strings.Contains(err.Error(), "private-marker") {
			t.Fatal("private input leaked")
		}
		return
	}
	if err != nil {
		t.Fatal(err)
	}
	actual, err := json.Marshal(result)
	if err != nil {
		t.Fatal(err)
	}
	actual, err = canonjson.JCS(actual)
	if err != nil {
		t.Fatal(err)
	}
	expected, err := canonjson.JCS(c.Result)
	if err != nil {
		t.Fatal(err)
	}
	if string(actual) != string(expected) {
		t.Fatalf("configuration = %s, want %s", actual, expected)
	}
}

type configurationInspectionError struct{}

func (configurationInspectionError) Error() string { return "private-owner-error" }
func (configurationInspectionError) As(any) bool   { panic("private-owner-inspection") }

type inspectionFailureNormalizer struct{}

func (inspectionFailureNormalizer) ValidateAndNormalize(context.Context, ParticipantConfiguration) (ParticipantConfiguration, error) {
	return ParticipantConfiguration{}, configurationInspectionError{}
}
func TestParticipantConfigurationIsolatesForeignErrorInspection(t *testing.T) {
	request := configurationRequestFixture(t)
	request.Validator = inspectionFailureNormalizer{}
	_, err := RealizeParticipantConfiguration(t.Context(), request)
	category, known := fault.CategoryOf(err)
	if !known || category != fault.Operational || strings.Contains(err.Error(), "private-") {
		t.Fatal("unsafe normalizer error inspection", err)
	}
}

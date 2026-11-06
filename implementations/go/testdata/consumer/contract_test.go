// Package consumer is an external module that imports the public rae packages
// at a pinned version. It proves that a consumer needs no internal package.
package consumer

import (
	"errors"
	"io"
	"strings"
	"testing"
	"time"

	"github.com/OpenRAE/rae/implementations/go/base/address"
	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/clock"
	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func TestSharedPrimitives(t *testing.T) {
	canonical, err := canonjson.JCS([]byte(`{"b":1,"a":"x"}`))
	if err != nil || string(canonical) != `{"a":"x","b":1}` {
		t.Errorf("JCS() = %s, %v", canonical, err)
	}
	if got := digest.SHA256([]byte("abc")); got != "sha256:ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad" || !digest.Valid(got) {
		t.Errorf("SHA256() = %s", got)
	}
	_, err = ingress.Parse([]byte(`{"a":1,"a":2}`), ingress.Limits{MaxBytes: 64}, ingress.Object)
	if category, ok := fault.CategoryOf(err); !ok || category != fault.InvalidInput {
		t.Errorf("Parse(duplicate) = %v, want an invalid-input fault", err)
	}
	if rendered, err := address.Render("provision", "node", "host"); err != nil || !address.Valid(rendered) {
		t.Errorf("Render() = %q, %v", rendered, err)
	}
	instant := time.Date(2026, 1, 1, 0, 0, 0, 0, time.UTC)
	if got := clock.Read(func() time.Time { return instant }); !got.Equal(instant) {
		t.Errorf("Read() = %v", got)
	}
}

// scenarioSource is an SDL authoring input with a recorded native admission.
const scenarioSource = `{"name":"scenario","version":"1.0.0"}`

// sdlOwner stands in for the native SDL owner. It returns its recorded
// admission for the exact source digest and refuses every other source.
type sdlOwner struct{}

func (sdlOwner) AdmitSDLPhase(request admission.SDLPhaseRequest) (admission.SDLPhaseAdmission, error) {
	recorded := digest.SHA256([]byte(scenarioSource))
	if request.ContractID != "sdl-authoring-input-v1" || digest.SHA256(request.Source) != recorded {
		return admission.SDLPhaseAdmission{}, errors.New("unknown SDL source")
	}
	return admission.SDLPhaseAdmission{ContractID: request.ContractID, SourceSHA256: recorded, Document: []byte(scenarioSource)}, nil
}

func TestContractValidation(t *testing.T) {
	v, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	limits := ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64}
	parent, err := v.Validate("sdl-authoring-input-v1", []byte(scenarioSource), limits, sdlOwner{})
	if err != nil {
		t.Fatal(err)
	}
	transport, err := parent.Transport()
	if _, ok := transport.(binding.SdlAuthoringInputV1); err != nil || !ok {
		t.Errorf("Transport() = %T, %v", transport, err)
	}
	for name, context := range map[string]any{"missing owner": nil, "schema": sdlOwner{}} {
		data := []byte(scenarioSource)
		if name == "schema" {
			data = []byte(`{"name":"scenario"}`)
		}
		if _, err = v.Validate("sdl-authoring-input-v1", data, limits, context); err == nil {
			t.Errorf("%s: the document was admitted", name)
		}
	}
	schema, err := validation.New(nil)
	if err != nil {
		t.Fatal(err)
	}
	if err = schema.CheckSchema("sdl-authoring-input-v1", parent.JSON(), limits); err != nil {
		t.Error(err)
	}
}

// parentContext supplies the admitted parent of an associated artifact set.
type parentContext struct{ parent validation.Value }

func (c parentContext) AssociatedParent() validation.Value       { return c.parent }
func (c parentContext) AssociatedParentDigest() string           { return "" }
func (c parentContext) AssociatedPayloads() map[string]io.Reader { return nil }

func TestAssociatedArtifacts(t *testing.T) {
	v, err := admission.New()
	if err != nil {
		t.Fatal(err)
	}
	limits := ingress.Limits{MaxBytes: 1 << 20, MaxDepth: 64}
	manifest := func(setDigest string) []byte {
		return []byte(`{"schema_version":"associated-artifact-manifest/v1","manifest_id":"set","manifest_version":"1","canonicalization_profile":"associated-artifact-set/v1","scope":"scenario","parent_ref":{"ref_kind":"scenario","ref_id":"scenario"},"artifacts":{"file":{"artifact_id":"file","role":"other","media_type":"text/plain","uri":"urn:example:payload","checksum":{"algorithm":"sha256","value":"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"},"size_bytes":3,"created_at":"2026-01-01T00:00:00Z","source":"test","sensitivity":"public"}},"set_digest":"` + setDigest + `"}`)
	}
	draft, err := admission.LoadAssociatedManifest(v, manifest("sha256:"+strings.Repeat("0", 64)), limits)
	if err != nil {
		t.Fatal(err)
	}
	setDigest, err := admission.AssociatedArtifactSetDigest(draft)
	if err != nil {
		t.Fatal(err)
	}
	loaded, err := admission.LoadAssociatedManifest(v, manifest(setDigest), limits)
	if err != nil {
		t.Fatal(err)
	}
	parent, err := v.Validate("sdl-authoring-input-v1", []byte(scenarioSource), limits, sdlOwner{})
	if err != nil {
		t.Fatal(err)
	}
	readers := func(payload string) map[string]io.Reader {
		return map[string]io.Reader{"file": strings.NewReader(payload)}
	}
	admitted, err := admission.ValidateAssociatedManifest(v, loaded, parentContext{parent}, readers("abc"), admission.DefaultAssociatedArtifactLimits())
	if err != nil || admitted.ContractID() != "associated-artifact-manifest-v1" {
		t.Fatalf("ValidateAssociatedManifest() = %q, %v", admitted.ContractID(), err)
	}
	for name, err := range map[string]error{
		"stale set digest":   second(admission.ValidateAssociatedManifest(v, draft, parentContext{parent}, readers("abc"), admission.DefaultAssociatedArtifactLimits())),
		"substituted bytes":  second(admission.ValidateAssociatedManifest(v, loaded, parentContext{parent}, readers("abd"), admission.DefaultAssociatedArtifactLimits())),
		"caller byte limits": second(admission.ValidateAssociatedManifest(v, loaded, parentContext{parent}, readers("abc"), admission.AssociatedArtifactLimits{MaxArtifacts: 1, MaxTotalBytes: 2, MaxArtifactBytes: 2})),
	} {
		var refusal *fault.Error
		if !errors.As(err, &refusal) || refusal.Category() != fault.InvalidInput {
			t.Errorf("%s: %v, want an invalid-input fault", name, err)
		}
	}
}

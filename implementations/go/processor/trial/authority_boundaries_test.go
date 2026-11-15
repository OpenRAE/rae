package trial

import (
	"encoding/json"
	"slices"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

func TestApparatusAuthorityRequiresExactReferencesAndKindAllowlists(t *testing.T) {
	version, digest := "1", "sha256:"+strings.Repeat("a", 64)
	required := reference{Kind: "manifest", ID: "backend", Version: &version, Digest: &digest, Subject: &reference{Kind: componentBackend, ID: "backend", Version: &version}}
	for _, test := range []string{"exact", "version", "digest", "subject", "kind", "name"} {
		actual := required
		subject := *required.Subject
		actual.Subject = &subject
		foreign := "foreign"
		switch test {
		case "version":
			actual.Version = &foreign
		case "digest":
			actual.Digest = &foreign
		case "subject":
			actual.Subject = nil
		case "kind":
			subject.Kind = componentProcessor
		case "name":
			subject.ID = foreign
		}
		if got := manifestReferenceSatisfies(actual, required); got != (test == "exact") {
			t.Fatal("manifest authority", test, got)
		}
	}
	unqualified := required
	unqualified.Subject = nil
	if !manifestReferenceSatisfies(required, unqualified) {
		t.Fatal("unqualified exact manifest failed")
	}
	var metadata manifestMetadata
	metadata.Identity.Name = "backend"
	metadata.Identity.Version = "1"
	selected := map[ApparatusManifestKey]manifestMetadata{{ComponentKind: componentBackend}: metadata}
	allowed := []reference{{Kind: componentBackend, ID: "backend", Version: &version}}
	if err := apparatusKindAllowlist(componentBackend, selected, allowed); err != nil {
		t.Fatal("exact kind allowlist refused", err)
	}
	if err := apparatusKindAllowlist(componentProcessor, selected, allowed); err == nil {
		t.Fatal("missing allowed kind admitted")
	}
	if err := requiredApparatusManifests([]reference{required}, []reference{unqualified}, true); err != nil {
		t.Fatal(err)
	}
	if err := requiredApparatusManifests(nil, []reference{required}, true); err == nil {
		t.Fatal("missing exact required manifest admitted")
	}
	if err := requiredApparatusCapabilities([]string{"missing"}, nil, true); err == nil {
		t.Fatal("unavailable mixed capability admitted")
	}
	if err := validateApparatusIntent(json.RawMessage(`{`), selected, nil, nil, false); err == nil {
		t.Fatal("malformed apparatus intent admitted")
	}
	if _, err := apparatusReferenceKey(reference{}); err == nil {
		t.Fatal("unqualified apparatus identity admitted")
	}
}
func TestMixedParticipantsRetainAllAuthorityDimensionsDuringCanonicalization(t *testing.T) {
	base := participantManifestReference{Address: "p", Name: "implementation", Version: "1", ManifestVersion: "v1", ManifestDigest: "sha256:" + strings.Repeat("a", 64)}
	refs := []participantManifestReference{base, base}
	for _, field := range []string{"address", "name", "version", "manifest", "digest"} {
		changed := base
		switch field {
		case "address":
			changed.Address = "q"
		case "name":
			changed.Name = "other"
		case "version":
			changed.Version = "2"
		case "manifest":
			changed.ManifestVersion = "v2"
		case "digest":
			changed.ManifestDigest = "sha256:" + strings.Repeat("b", 64)
		}
		refs = append(refs, changed)
	}
	actual := canonicalParticipants(refs)
	if len(actual) != 6 || !slices.IsSorted(actual) {
		t.Fatal("participant authority was collapsed or unordered")
	}
	slices.Reverse(refs)
	if !slices.Equal(actual, canonicalParticipants(refs)) {
		t.Fatal("participant authority depends on input order")
	}
	checkMixedParticipantSerialization(t, base)
}

func checkMixedParticipantSerialization(t *testing.T, base participantManifestReference) {
	t.Helper()
	owner, err := trialOwner()
	if err != nil {
		t.Fatal(err)
	}
	ref := mixedCompilerReferences(t)[0]
	request := mixedCompilerRequest(t, ref)
	for _, fragment := range request.RealizationAssignments {
		var doc map[string]any
		raw, encodeErr := encoded(fragment.Document())
		if encodeErr != nil {
			t.Fatal(encodeErr)
		}
		if decode(raw, &doc) != nil {
			t.Fatal("mixed fixture")
		}
		other := base
		other.Address = "q"
		doc["participant_manifest_refs"] = []any{
			map[string]any{"participant_address": other.Address, "implementation_name": other.Name, "implementation_version": other.Version, "manifest_version": other.ManifestVersion, "manifest_digest": other.ManifestDigest},
			map[string]any{"participant_address": base.Address, "implementation_name": base.Name, "implementation_version": base.Version, "manifest_version": base.ManifestVersion, "manifest_digest": base.ManifestDigest},
		}
		admitted, admitErr := admission.AdmitFragment(owner, admission.AdmittedMixedCompositionBinding, doc, trialIngress())
		if admitErr != nil {
			t.Fatal(admitErr)
		}
		if _, _, bindingErr := mixedBinding(owner, admitted); bindingErr != nil {
			t.Fatal("canonical participant claims refused", bindingErr)
		}
		break
	}
}
func TestMixedProfileTraversalRefusesConflictingIdentitiesMissingResourcesAndInvalidBudgets(t *testing.T) {
	request := Request{Limits: DefaultLimits(), MixedCompositionLimits: DefaultMixedCompositionLimits()}
	compiler := mixedAuthorityCompiler{request: request, admitted: map[string]string{"profile": "original"}}
	authority := mixedAuthority{}
	if err := compiler.member(mixedProfile{ID: "profile", Digest: "foreign"}, admission.MixedCompositionSnapshot{}, &authority); err == nil {
		t.Fatal("conflicting profile identity admitted")
	}
	compiler.admitted = map[string]string{}
	if err := compiler.member(mixedProfile{ID: "profile"}, admission.MixedCompositionSnapshot{}, &authority); err == nil {
		t.Fatal("unresolved resource closure admitted")
	}
	walk := mixedClosureWalk{request: request, visited: map[string]bool{"profile": true}}
	if err := walk.visit(mixedProfile{ID: "profile"}, []byte(`{}`)); err != nil {
		t.Fatal("visited profile was expanded again", err)
	}
	for _, test := range []struct {
		name, source string
		limit        func(*MixedCompositionLimits)
	}{
		{"source-bytes", `{"x":1}`, func(l *MixedCompositionLimits) { l.MaxSourceBytes = 1 }},
		{"json-depth", `{"x":[{}]}`, func(l *MixedCompositionLimits) { l.MaxJSONDepth = 1 }},
		{"json-nodes", `{"x":[1,2]}`, func(l *MixedCompositionLimits) { l.MaxJSONNodes = 2 }},
		{"invalid-json", `{`, func(*MixedCompositionLimits) {}},
	} {
		t.Run(test.name, func(t *testing.T) {
			limits := DefaultMixedCompositionLimits()
			test.limit(&limits)
			if err := mixedProfileLimits([]byte(test.source), mixedProfile{}, limits); err == nil {
				t.Fatal("unbounded composition admitted")
			}
		})
	}
}
func TestCapturePinsAndBindingSetsCannotSubstituteDifferentPayloads(t *testing.T) {
	for _, test := range []struct {
		raw string
		ref *reference
	}{
		{"null", &reference{ID: "foreign"}}, {`{}`, nil}, {`{`, nil},
	} {
		if err := validateBindingPin(json.RawMessage(test.raw), test.ref); err == nil {
			t.Fatal("unresolved binding descriptor set admitted")
		}
	}
	request := compilerRequest(t, referenceCompilations(t)[0].Request)
	input, err := prepareInputs(request)
	if err != nil {
		t.Fatal(err)
	}
	for _, field := range []string{"missing", "digest", "version", "payload"} {
		t.Run(field, func(t *testing.T) { checkCapturePinBoundary(t, request, input, field) })
	}
	if err := validateCapturePins(Request{}, compilationInputs{}, []reference{{ID: "unresolved"}}, nil); err == nil {
		t.Fatal("task requirement without capture authority admitted")
	}
}
func checkCapturePinBoundary(t *testing.T, base Request, baseInput compilationInputs, field string) {
	t.Helper()
	request, input := base, baseInput
	if len(input.refs.Capture) == 0 || len(input.spec.Capture) == 0 {
		t.Fatal("capture fixture missing")
	}
	input.refs.Capture = slices.Clone(input.refs.Capture)
	input.spec.Capture = slices.Clone(input.spec.Capture)
	foreign := "foreign"
	switch field {
	case "missing":
		request.CaptureSpecs = nil
	case "digest":
		input.refs.Capture[0].Digest = &foreign
	case "version":
		input.refs.Capture[0].Version = &foreign
	case "payload":
		input.spec.Capture[0].ID = foreign
	}
	if err := validateCapturePins(request, input, nil, nil); err == nil {
		t.Fatal("capture payload substitution admitted")
	}
}

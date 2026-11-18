package admission

import (
	"encoding/json"
	"testing"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/internal/base/domain"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

func TestEnvelopeScalarProposalsRespectDomainMembership(t *testing.T) {
	for _, descriptor := range []map[string]any{
		{"kind": "exact", "value": true},
		{"kind": "exact", "value": json.Number("1.5")},
		{"kind": "enum", "values": []any{json.Number("2"), json.Number("1"), json.Number("2.0")}},
		{"kind": "enum", "values": []any{false, true}},
		{"kind": "enum", "values": []any{"out-of-envelope", "out-of-envelope-x"}},
		{"kind": "boolean"},
		{"kind": "boolean", "value": true},
		{"kind": "governed-reference", "authority": "catalog", "allowed_refs": []any{"z", "a"}},
		intervalDescriptor("integer", false, false),
		intervalDescriptor("number", false, false),
		intervalDescriptor("number", true, true),
	} {
		checkEnvelopeScalarProposals(t, descriptor)
	}
}

func checkEnvelopeScalarProposals(t *testing.T, descriptor map[string]any) {
	t.Helper()
	decoded, err := envelopeDomain(descriptor)
	if err != nil {
		t.Fatal(err)
	}
	for _, candidate := range envelopePositiveValues(descriptor) {
		inside, membershipErr := domain.In(candidate, decoded)
		if membershipErr != nil || !inside {
			t.Fatalf("positive proposal outside %v: %v (%v)", descriptor, candidate, membershipErr)
		}
	}
	for _, candidate := range envelopeNegativeValues(descriptor, []any{"alternate", true, json.Number("9")}) {
		inside, membershipErr := domain.In(candidate, decoded)
		if membershipErr == nil && inside {
			t.Fatalf("negative proposal inside %v: %v", descriptor, candidate)
		}
	}
	witness, reason := defaultEnvelopeWitness(descriptor)
	inside, err := domain.In(witness, decoded)
	if reason != "" || err != nil || !inside {
		t.Fatalf("invalid witness for %v: %v %s %v", descriptor, witness, reason, err)
	}
}

func intervalDescriptor(kind string, lowerClosed, upperClosed bool) map[string]any {
	return map[string]any{"kind": "numeric-interval", "numeric_type": kind, "lower": json.Number("1"), "upper": json.Number("5"), "lower_closed": lowerClosed, "upper_closed": upperClosed}
}

func TestEnvelopeScalarOrderingAndRefusals(t *testing.T) {
	values := uniqueProbeValues([]any{json.Number("1"), json.Number("1.0"), false, false, "a"})
	if len(values) != 3 {
		t.Fatal("equal numeric values or booleans were not deduplicated", values)
	}
	for _, descriptor := range []map[string]any{{"kind": "enum", "values": []any{}}, {"kind": "governed-reference", "allowed_refs": []any{}}, {"kind": "record"}, {"kind": "unknown"}} {
		if _, reason := defaultEnvelopeWitness(descriptor); reason == "" {
			t.Fatal("unconstructive domain supplied a witness", descriptor)
		}
	}
	for _, descriptor := range []map[string]any{{"kind": "unknown"}, {"kind": "exact", "value": "a"}, {"kind": "numeric-interval"}} {
		if got := positiveIntervalValues(descriptor); got != nil {
			t.Fatal("non-interval accepted", got)
		}
		if _, reason := intervalEnvelopeWitness(descriptor); reason == "" {
			t.Fatal("non-interval witnessed")
		}
	}
	if got := envelopeNegativeValues(map[string]any{"kind": "unknown"}, nil); len(got) != 0 {
		t.Fatal(got)
	}
	if _, ok := outsideEnvelopeValue(map[string]any{"kind": "unknown"}); ok {
		t.Fatal("unknown domain has an outside proposal")
	}
	if _, ok := outsideEnvelopeValue(map[string]any{"kind": "numeric-interval"}); ok {
		t.Fatal("invalid interval has an outside proposal")
	}
}

func TestEnvelopeScalarPerturbationAndOrdering(t *testing.T) {
	for _, input := range []any{nil, json.Number("invalid"), json.Number("1e9999")} {
		if got := perturbProbeScalar(input); got != nil {
			t.Fatal("unsupported scalar perturbed", got)
		}
	}
	if got := perturbProbeScalar(float64(2)); got != float64(3) {
		t.Fatal(got)
	}
	if compareEnvelopeScalars(false, "a") >= 0 || compareEnvelopeScalars(json.Number("1"), json.Number("2")) >= 0 {
		t.Fatal("scalar ordering changed")
	}
	interval := intervalDescriptor("integer", false, false)
	interval["upper"] = json.Number("2")
	if _, reason := intervalEnvelopeWitness(interval); reason == "" {
		t.Fatal("empty integer interval witnessed")
	}
}

func TestEnvelopeProbeBuilderBoundsAndClosedScopes(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	builder := envelopeProbeBuilder{owner: owner, base: []byte(`{"nested":{"keep":true}}`), remaining: 4096}
	if err := builder.closed(map[string]map[string]bool{"nested": {"keep": true, "out_of_envelope": true}}, nil); err != nil {
		t.Fatal(err)
	}
	if len(builder.output) != 1 {
		t.Fatal(builder.output)
	}
	want := map[string]any{"nested": map[string]any{"keep": true, "out_of_envelope_x": "out-of-envelope"}}
	if diff := cmp.Diff(want, builder.output[0].Payload.Document()); diff != "" {
		t.Fatal(diff)
	}
	if err := builder.closedTyped("nested", EnvelopeProbeScope{Fields: []EnvelopeProbeField{{Name: "extra", Variations: []any{true}}}}, map[string]bool{}); err != nil {
		t.Fatal(err)
	}
	for _, path := range []string{"", "missing.value", "nested.absent"} {
		before := len(builder.output)
		if err := builder.omitted(path, "exact"); err != nil || len(builder.output) != before {
			t.Fatal("omission of absent path produced a proposal", path, err)
		}
	}
	builder.remaining = 0
	if err := builder.add("a", "exact", "bounded-member", map[string]any{"a": true}); err == nil {
		t.Fatal("output byte budget bypassed")
	}
	builder.output = make([]EnvelopeProbeCandidate, value.Runtime().MaxMembers)
	if err := builder.add("a", "exact", "bounded-member", nil); err == nil {
		t.Fatal("output count budget bypassed")
	}
	builder.base = []byte(`{`)
	if err := builder.assigned("a", "exact", "test", true, true); err == nil {
		t.Fatal("malformed base accepted")
	}
	if err := checkProbeScopes(make([]EnvelopeProbeScope, value.Runtime().MaxMembers+1)); err == nil {
		t.Fatal("scope count budget bypassed")
	}
	if err := checkProbeScopes([]EnvelopeProbeScope{{Fields: make([]EnvelopeProbeField, value.Runtime().MaxMembers+1)}}); err == nil {
		t.Fatal("field count budget bypassed")
	}
}

func TestEnvelopeProbeFailuresPropagateWithoutPartialPublication(t *testing.T) {
	owner, err := New()
	if err != nil {
		t.Fatal(err)
	}
	for _, call := range []func(*envelopeProbeBuilder) error{
		func(b *envelopeProbeBuilder) error { return b.assigned("a", "exact", "outside", true, false) },
		func(b *envelopeProbeBuilder) error { return b.omitted("a", "exact") },
		func(b *envelopeProbeBuilder) error { return b.closedUntyped("nested", nil) },
		func(b *envelopeProbeBuilder) error {
			return b.closedTyped("nested", EnvelopeProbeScope{Fields: []EnvelopeProbeField{{Name: "extra", Variations: []any{true}}}}, nil)
		},
		func(b *envelopeProbeBuilder) error { return b.closed(map[string]map[string]bool{"nested": {}}, nil) },
		func(b *envelopeProbeBuilder) error {
			return b.closed(map[string]map[string]bool{"nested": {}}, map[string]EnvelopeProbeScope{"nested": {Fields: []EnvelopeProbeField{{Name: "extra", Variations: []any{true}}}}})
		},
	} {
		builder := envelopeProbeBuilder{owner: owner, base: []byte(`{"a":true}`), remaining: 0}
		if call(&builder) == nil || len(builder.output) != 0 {
			t.Fatal("exhausted proposal budget published a candidate")
		}
	}
	builder := envelopeProbeBuilder{owner: owner, base: []byte(`{`), remaining: 4096}
	if err := builder.omitted("a", "exact"); err == nil {
		t.Fatal("malformed base accepted for omission")
	}
	if err := builder.add("a", "exact", "outside", map[string]any{"foreign": make(chan int)}); err == nil {
		t.Fatal("unsupported proposal carrier accepted")
	}
	if err := checkProbeScopes([]EnvelopeProbeScope{{Fields: []EnvelopeProbeField{{Variations: []any{make(chan int)}}}}}); err == nil {
		t.Fatal("foreign field metadata accepted")
	}
	if assignEnvelopePath(map[string]any{}, "", true) == "" {
		t.Fatal("empty assignment path accepted")
	}
}

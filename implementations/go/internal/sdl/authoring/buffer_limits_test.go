package authoring

import (
	"errors"
	"fmt"
	"runtime"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

func TestJSONRepeatedStringsRefusedBeforeAllocation(t *testing.T) {
	large := strings.Repeat("x", 1024*1024)
	items := make([]any, 32)
	for i := range items {
		items[i] = large
	}
	for _, value := range []any{items, map[string]any{"opaque": items}, ordered{{name: "opaque", value: items}}} {
		runtime.GC()
		var before, after runtime.MemStats
		runtime.ReadMemStats(&before)
		_, err := encode(value, 4096, false)
		runtime.ReadMemStats(&after)
		if err == nil {
			t.Fatal("oversized repeated strings accepted")
		}
		if allocated := after.TotalAlloc - before.TotalAlloc; allocated > 256*1024 {
			t.Fatalf("allocated %d bytes before refusing a 4 KiB buffer", allocated)
		}
	}
}

func TestJSONBoundedNestedMap(t *testing.T) {
	value := map[string]any{"nested": map[string]any{"text": "<&>\n"}}
	want := `{"nested":{"text":"<&>\n"}}`
	got, err := encode(value, int64(len(want)), false)
	if err != nil || string(got) != want {
		t.Fatalf("%s: %v", got, err)
	}
	if _, err = encode(value, int64(len(want)-1), false); err == nil {
		t.Fatal("escaped bytes exceeded limit")
	}
}

func TestBindingCopyBudgetBeforeAllocation(t *testing.T) {
	budget := copyBudget{remaining: 4096}
	s := substitution{values: map[string]any{"v": strings.Repeat("x", 16*1024)}, preserved: map[string]bool{}, inline: map[string]string{}, copies: &budget}
	runtime.GC()
	var before, after runtime.MemStats
	runtime.ReadMemStats(&before)
	_, err := s.string("prefix" + strings.Repeat("${v}", 64))
	runtime.ReadMemStats(&after)
	if err == nil {
		t.Fatal("substitution exceeded its copy allowance")
	}
	if allocated := after.TotalAlloc - before.TotalAlloc; allocated > 256*1024 {
		t.Fatalf("allocated %d before refusing expansion", allocated)
	}
	if budget.remaining != 4096 {
		t.Fatal("failed reservation changed allowance")
	}
}

func TestBindingCopyBudgetSharedAndMemoized(t *testing.T) {
	budget := copyBudget{remaining: 10}
	first := substitution{values: map[string]any{"v": "four"}, preserved: map[string]bool{}, inline: map[string]string{}, copies: &budget}
	for range 2 {
		got, err := first.string("x${v}")
		if err != nil || got != "xfour" {
			t.Fatalf("%v: %v", got, err)
		}
	}
	if budget.remaining != 5 {
		t.Fatalf("cached result charged again: %d", budget.remaining)
	}
	second := substitution{values: map[string]any{"v": "four"}, preserved: map[string]bool{}, inline: map[string]string{}, copies: &budget}
	if _, err := second.string("y${v}"); err != nil {
		t.Fatal(err)
	}
	if _, err := first.string("z${v}"); err == nil {
		t.Fatal("bindings did not share the allowance")
	}
	if got, err := first.string("${v}"); err != nil || got != "four" {
		t.Fatalf("whole-token bytes should remain shared: %v %v", got, err)
	}
}

func TestVariableNamespaceCopyBudget(t *testing.T) {
	c := composition{copies: copyBudget{remaining: 64}}
	value := map[string]any{"variables": map[string]any{"v": map[string]any{"type": "string"}}, "description": strings.Repeat("${v}", 32)}
	if _, err := c.namespaceVariables(value, strings.Repeat("a", 100), nil); err == nil {
		t.Fatal("namespace rewriting exceeded copy allowance")
	}
	c.copies.remaining = 1024
	value["description"] = "${unknown} ${v}"
	got, err := c.namespaceVariables(value, "m", nil)
	if err != nil || got["description"] != "${unknown} ${m.__private.v}" {
		t.Fatalf("%v: %v", got, err)
	}
}

func TestImportedAliasBytesCheckedBeforeModelEncoding(t *testing.T) {
	limits := source.DefaultLimits()
	limits.MaxComposedBytes = 4096
	limits.MaxInputBytes = 8192
	parser, err := New(limits)
	if err != nil {
		t.Fatal(err)
	}
	raw := []byte("name: a\ndescription: &value " + strings.Repeat("x", 1024) + "\ninfrastructure: {i: {properties: [{opaque: [" + strings.Repeat("*value,", 99) + "*value]}]}}\n")
	if _, err = source.Decode(raw, parser.options("module.yaml", "reject")); err != nil {
		t.Fatal(err)
	}
	runtime.GC()
	var before, after runtime.MemStats
	runtime.ReadMemStats(&before)
	_, err = parser.decodeDocument(raw, "module.yaml", "reject", true)
	runtime.ReadMemStats(&after)
	if err == nil {
		t.Fatal("imported repeated string bytes were accepted")
	}
	coded, ok := errors.AsType[interface {
		error
		Code() string
	}](err)
	if !ok {
		t.Fatalf("unclassified refusal: %v", err)
	}
	if got := coded.Code(); got != "sdl.import.budget-exceeded" {
		t.Fatalf("code=%s", got)
	}
	if allocated := after.TotalAlloc - before.TotalAlloc; allocated > 512*1024 {
		t.Fatalf("allocated %d before composition refusal", allocated)
	}
}

func TestBoundModelJSONSharesWorkAllowance(t *testing.T) {
	limits := source.DefaultLimits()
	limits.MaxComposedBytes = 4096
	limits.MaxComposedNodes = 1
	limits.MaxCompositionDepth = 1
	parser, err := New(limits)
	if err != nil {
		t.Fatal(err)
	}
	c := composition{parser: parser}
	fragment := map[string]any{"name": strings.Repeat("x", 2048)}
	if err = c.checkBoundFragment("#/$defs/Source", fragment); err != nil {
		t.Fatal(err)
	}
	previous := c.modelBuffers.remaining
	for range 50 {
		err = c.checkBoundFragment("#/$defs/Source", fragment)
		if err != nil {
			return
		}
		if c.modelBuffers.remaining >= previous {
			t.Fatal("JSON allowance was reset")
		}
		previous = c.modelBuffers.remaining
	}
	t.Fatal("repeated shared parameter bytes bypassed JSON work accounting")
}

func TestAliasNormalizationSharesScalarBytes(t *testing.T) {
	limits := source.DefaultLimits()
	limits.MaxInputBytes = 16384
	limits.MaxExpandedNodes = 500
	parser, err := New(limits)
	if err != nil {
		t.Fatal(err)
	}
	var raw strings.Builder
	raw.WriteString("name: a\naccounts:\n")
	for i := range 50 {
		fmt.Fprintf(&raw, "  a%d:\n    username: u\n    node: n\n    auth_method: ", i)
		if i == 0 {
			raw.WriteString("&v x-" + strings.Repeat("A", 8192) + ":METHOD\n")
		} else {
			raw.WriteString("*v\n")
		}
	}
	parsed, err := source.Decode([]byte(raw.String()), parser.options("input.yaml", "reject"))
	if err != nil {
		t.Fatal(err)
	}
	value := object(parsed.NormalizedValue())
	runtime.GC()
	var before, after runtime.MemStats
	runtime.ReadMemStats(&before)
	_, err = parser.construct(value, authoringContract, nil, parsed)
	runtime.ReadMemStats(&after)
	if err == nil {
		t.Fatal("normalization exceeded its working ceiling")
	}
	if allocated := after.TotalAlloc - before.TotalAlloc; allocated > 384*1024 {
		t.Fatalf("allocated %d before refusing repeated normalization", allocated)
	}
}

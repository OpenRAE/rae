package source

import (
	"fmt"
	"strings"
	"testing"
)

func TestPhysicalSourceBounds(t *testing.T) {
	options := DefaultOptions()
	scalar := strings.Repeat("x", int(options.Limits.MaxScalarBytes))
	if _, err := Decode([]byte("value: "+scalar+"\n"), options); err != nil {
		t.Fatalf("Decode() refused scalar at ceiling: %v", err)
	}
	requireLimit(t, []byte("value: "+scalar+"x\n"), options)
	body := "x: y\n" + strings.Repeat(" ", int(options.Limits.MaxInputBytes)-5)
	if _, err := Decode([]byte(body), options); err != nil {
		t.Fatalf("Decode() refused source at ceiling: %v", err)
	}
	requireLimit(t, []byte(body+" "), options)
	for _, depth := range []int{127, 128} {
		data := []byte(strings.Repeat("[", depth) + "x" + strings.Repeat("]", depth))
		_, err := Decode(data, options)
		if (err != nil) != (depth == 128) {
			t.Errorf("Decode(depth %d) = %v", depth, err)
		}
	}
}
func TestAliasesAtDefaultCeiling(t *testing.T) {
	options := DefaultOptions()
	aliases := strings.Repeat("*a, ", options.Limits.MaxAliases-1) + "*a"
	if _, err := Decode([]byte("a: &a x\nvalue: ["+aliases+"]\n"), options); err != nil {
		t.Fatalf("Decode() refused aliases at ceiling: %v", err)
	}
	requireLimit(t, []byte("a: &a x\nvalue: ["+aliases+", *a]\n"), options)
	var graph strings.Builder
	graph.WriteString("a0: &a0 [x]\n")
	for i := 1; i <= 24; i++ {
		fmt.Fprintf(&graph, "a%d: &a%d [*a%d, *a%d]\n", i, i, i-1, i-1)
	}
	requireLimit(t, []byte(graph.String()), options)
}
func TestAggregateDefaultCeilings(t *testing.T) {
	limits := DefaultLimits()
	budget, err := NewBudget(limits)
	if err != nil {
		t.Fatal(err)
	}
	for range limits.MaxImports {
		if err := budget.AddImport(); err != nil {
			t.Fatal(err)
		}
	}
	if budget.AddImport() == nil {
		t.Fatal("AddImport() exceeded the ceiling")
	}
	if err := budget.AddBytes(limits.MaxComposedBytes); err != nil {
		t.Fatal(err)
	}
	if budget.AddBytes(1) == nil {
		t.Fatal("AddBytes() exceeded the ceiling")
	}
	if err := budget.CheckDepth(limits.MaxCompositionDepth); err != nil {
		t.Fatal(err)
	}
	if budget.CheckDepth(limits.MaxCompositionDepth+1) == nil {
		t.Fatal("CheckDepth() exceeded the ceiling")
	}
	namespace := strings.Repeat("a.", limits.MaxNamespaceDepth) + "x"
	if err := budget.CheckNamespace(namespace); err != nil {
		t.Fatal(err)
	}
	if budget.CheckNamespace("a."+namespace) == nil {
		t.Fatal("CheckNamespace() exceeded the ceiling")
	}
}
func TestRenderOutputReservation(t *testing.T) {
	document, err := Decode([]byte("x: &x {value: text}\ny: [*x, *x]\n"), DefaultOptions())
	if err != nil {
		t.Fatal(err)
	}
	for _, ceiling := range []int64{0, 1, 8} {
		if _, err := document.Render(ceiling); err == nil {
			t.Errorf("Render(%d) exceeded reservation", ceiling)
		}
	}
}
func requireLimit(t *testing.T, data []byte, options Options) {
	t.Helper()
	_, err := Decode(data, options)
	diagnostics := Diagnostics(err)
	if len(diagnostics) != 1 || diagnostics[0].Code != "sdl.source_limit" {
		t.Fatalf("Decode() diagnostics = %+v, want one source-limit refusal", diagnostics)
	}
}
func BenchmarkSourceFlat(b *testing.B) {
	var text strings.Builder
	for i := range 10000 {
		fmt.Fprintf(&text, "key_%d: value\n", i)
	}
	data := []byte(text.String())
	options := DefaultOptions()
	b.ResetTimer()
	for range b.N {
		if _, err := Decode(data, options); err != nil {
			b.Fatal(err)
		}
	}
}

package source

import (
	"bytes"
	"encoding/json"
	"fmt"
	"math/big"
	"os"
	"runtime"
	"strings"
	"testing"

	"github.com/google/go-cmp/cmp"
)

type referenceCase struct {
	Name    string `json:"name"`
	Source  string `json:"source"`
	Options struct {
		Migration string `json:"migration_policy"`
		Format    string `json:"source_format"`
		Scope     string `json:"mapping_keys"`
		Base      string `json:"base_pointer"`
	} `json:"options"`
	Limits      map[string]int64 `json:"limits"`
	Error       bool             `json:"error"`
	Value       json.RawMessage  `json:"value"`
	Diagnostics json.RawMessage  `json:"diagnostics"`
	Ranges      json.RawMessage  `json:"ranges"`
	KeyRanges   json.RawMessage  `json:"key_ranges"`
	Rendered    string           `json:"rendered"`
}

func TestReferenceDecoding(t *testing.T) {
	data, err := os.ReadFile("testdata/reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var corpus struct {
		Reference string          `json:"reference_commit"`
		Cases     []referenceCase `json:"cases"`
	}
	if err := json.Unmarshal(data, &corpus); err != nil {
		t.Fatal(err)
	}
	if len(corpus.Reference) != 40 || len(corpus.Cases) == 0 {
		t.Fatal("source vectors have no reference identity or cases")
	}
	for _, c := range corpus.Cases {
		t.Run(c.Name, func(t *testing.T) { checkReference(t, c) })
	}
}
func referenceOptions(t *testing.T, c referenceCase) Options {
	t.Helper()
	options := DefaultOptions()
	if c.Options.Migration != "" {
		options.MigrationPolicy = c.Options.Migration
	}
	if c.Options.Format != "" {
		options.SourceFormat = c.Options.Format
	}
	if c.Options.Scope != "" {
		options.KeyScope = c.Options.Scope
	}
	options.BasePointer = c.Options.Base
	data, err := json.Marshal(c.Limits)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(data, &options.Limits); err != nil {
		t.Fatal(err)
	}
	return options
}
func checkReference(t *testing.T, c referenceCase) {
	t.Helper()
	options := referenceOptions(t, c)
	document, err := Decode([]byte(c.Source), options)
	if (err != nil) != c.Error {
		t.Fatalf("Decode() error = %v, want failure %v", err, c.Error)
	}
	diagnostics := Diagnostics(err)
	if err == nil {
		diagnostics = document.Diagnostics()
		checkReferenceValue(t, c, document, options)
	}
	machine := make([]map[string]any, 0, len(diagnostics))
	for _, d := range diagnostics {
		machine = append(machine, d.Machine())
	}
	got, err := json.Marshal(machine)
	if err != nil {
		t.Fatal(err)
	}
	if diff := jsonDiff(c.Diagnostics, got); diff != "" {
		t.Errorf("Diagnostics() mismatch (-want +got):\n%s", diff)
	}
}
func checkReferenceValue(t *testing.T, c referenceCase, document *Document, options Options) {
	t.Helper()
	rendered, err := document.Render(options.Limits.MaxInputBytes)
	if err != nil {
		t.Fatal(err)
	}
	if string(rendered) != c.Rendered {
		t.Errorf("Render() = %q, want %q", rendered, c.Rendered)
	}
	got, err := json.Marshal(document.Value())
	if err != nil {
		t.Fatal(err)
	}
	checkRangeJSON(t, c.Ranges, document.Ranges())
	checkRangeJSON(t, c.KeyRanges, document.KeyRanges())
	if diff := jsonDiff(c.Value, got); diff != "" {
		t.Errorf("Value() mismatch (-want +got):\n%s", diff)
	}
}
func jsonDiff(want, got []byte) string {
	var w, g any
	decoder := json.NewDecoder(bytes.NewReader(want))
	decoder.UseNumber()
	if err := decoder.Decode(&w); err != nil {
		return err.Error()
	}
	decoder = json.NewDecoder(bytes.NewReader(got))
	decoder.UseNumber()
	if err := decoder.Decode(&g); err != nil {
		return err.Error()
	}
	return cmp.Diff(w, g, cmp.Comparer(equalJSONNumber))
}
func equalJSONNumber(a, b json.Number) bool {
	if a == b {
		return true
	}
	left, leftOK := new(big.Rat).SetString(string(a))
	right, rightOK := new(big.Rat).SetString(string(b))
	return leftOK && rightOK && left.Cmp(right) == 0
}
func checkRangeJSON(t *testing.T, want json.RawMessage, ranges map[string]Range) {
	t.Helper()
	got, err := json.Marshal(ranges)
	if err != nil {
		t.Fatal(err)
	}
	if diff := jsonDiff(want, got); diff != "" {
		t.Errorf("source ranges mismatch (-want +got):\n%s", diff)
	}
}

func TestSourceViewOrderAndCopies(t *testing.T) {
	options := DefaultOptions()
	options.MigrationPolicy = "accept"
	options.BasePointer = "/fragment"
	document, err := Decode([]byte("A-B: &one {z: first, a: second}\ncopy: *one\nmerged: {<<: [{b: two}, {c: three}], tail: last}\n"), options)
	if err != nil {
		t.Fatal(err)
	}
	want := map[string][]string{"/fragment": {"a_b", "copy", "merged"}, "/fragment/a_b": {"z", "a"}, "/fragment/copy": {"z", "a"}, "/fragment/merged": {"c", "b", "tail"}}
	view := document.View()
	got := map[string][]string{"/fragment": view.Keys(), "/fragment/a_b": view.Child("a_b").Keys(), "/fragment/copy": view.Child("copy").Keys(), "/fragment/merged": view.Child("merged").Keys()}
	if diff := cmp.Diff(want, got); diff != "" {
		t.Fatalf("mapping keys (-want +got):\n%s", diff)
	}
	got["/fragment"][0] = "changed"
	delete(got, "/fragment/copy")
	if diff := cmp.Diff(want["/fragment"], view.Keys()); diff != "" {
		t.Errorf("caller mutated document (-want +got):\n%s", diff)
	}
}

// A small deep source must not eagerly copy its long prefix into every
// diagnostic and range entry before a consumer requests that metadata.
func TestDecodeMetadataAllocation(t *testing.T) {
	prefix := strings.Repeat("p", 2048)
	var input strings.Builder
	for depth := range 4 {
		indent := strings.Repeat("  ", depth)
		input.WriteString(indent + "? " + prefix + "\n" + indent + ":\n")
	}
	for i := range 1000 {
		fmt.Fprintf(&input, "        Leaf%04d: value\n", i)
	}
	raw := []byte(input.String())
	options := DefaultOptions()
	options.MigrationPolicy = "accept"
	runtime.GC()
	var before, after runtime.MemStats
	runtime.ReadMemStats(&before)
	document, err := Decode(raw, options)
	runtime.ReadMemStats(&after)
	if err != nil {
		t.Fatal(err)
	}
	if allocated := after.TotalAlloc - before.TotalAlloc; allocated > 24*1024*1024 {
		t.Fatalf("Decode allocated %d bytes for %d source bytes", allocated, len(raw))
	}
	diagnostics := document.Diagnostics()
	if len(diagnostics) != 1000 {
		t.Fatalf("got %d diagnostics, want 1000", len(diagnostics))
	}
	view := document.View()
	for range 4 {
		view = view.Child(prefix)
	}
	if got := len(view.Keys()); got != 1000 {
		t.Errorf("got %d keys, want 1000", got)
	}
}

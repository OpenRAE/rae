package parity

import (
	"encoding/json"
	"testing"

	"github.com/google/go-cmp/cmp"
)

func TestSharedRunnerDistinguishesMalformedCasesFromPrimitiveRefusals(t *testing.T) {
	for _, test := range []struct {
		command, request string
	}{
		{"secret", "{"}, {"missing", "{}"}, {"clock", `{"text":"invalid"}`},
		{"version", `{"relation":"numeric-triplet","lower":"1.0.0"}`},
		{"domain", `{"descriptor":{"kind":"null"}}`},
		{"graph", `{"graph":{"a":["missing"]}}`},
		{"value", `{}`}, {"value", `{"value":[],"document":true}`},
		{"value", `{"value":{"body":1},"document":true}`},
	} {
		c := Case{Command: test.command, Files: map[string][]byte{"request.json": []byte(test.request)}}
		if got, err := shared(t.Context(), c); err == nil {
			t.Errorf("shared(%s, %s) = %s, want a malformed-case error", test.command, test.request, got)
		}
	}
	for _, test := range []struct {
		command, request, want string
	}{
		{"timestamp", `{"mode":"missing"}`, `{"ok":false,"code":"invalid"}`},
		{"domain", `{"descriptor":{"kind":"missing"}}`, `{"valid":false}`},
		{"domain", `{"descriptor":{"kind":"enum","values":[]},"value":1}`, `{"valid":false}`},
		{"domain", `{"descriptor":{"kind":"boolean","value":"yes"},"value":true}`, `{"valid":false}`},
		{"domain", `{"descriptor":{"kind":"numeric-interval","numeric_type":"missing"},"value":1}`, `{"valid":false}`},
		{"value", `{"limits":{"max_nodes":0},"value":0}`, `{"status":"invalid-limits"}`},
		{"value", `{"limits":{"unknown":1},"value":0}`, `{"status":"invalid-limits"}`},
		{"value", `{"value":9007199254740992,"canonical":true}`, `{"status":"invalid"}`},
	} {
		c := Case{Command: test.command, Files: map[string][]byte{"request.json": []byte(test.request)}}
		got, err := shared(t.Context(), c)
		if err != nil {
			t.Fatalf("shared(%s) error = %v", test.request, err)
		}
		if diff := cmp.Diff(decode(t, json.RawMessage(test.want)), decode(t, got)); diff != "" {
			t.Errorf("shared(%s) = %s, want %s", test.request, got, test.want)
		}
	}
}

func TestSharedValueReadersRejectTruncationAndTrailingData(t *testing.T) {
	for _, data := range []string{"", "{", "1 2", "1 ]", "["} {
		if _, err := sharedJSON(json.RawMessage(data)); err == nil {
			t.Errorf("sharedJSON(%q) accepted malformed input", data)
		}
	}
	for _, data := range []string{"{", "{} {}", "{} ]", `{"max_depth":0}`, `{"unknown":1}`} {
		if _, err := readLimits(json.RawMessage(data)); err == nil {
			t.Errorf("readLimits(%q) accepted an invalid definition", data)
		}
	}
	for _, data := range []string{"{", `{"kind":"exact","value":{}}`, `{"kind":"enum","values":[{}]}`} {
		descriptor, err := readDomain(json.RawMessage(data))
		if err == nil && descriptor.Validate() == nil {
			t.Errorf("readDomain(%q) accepted an invalid scalar domain", data)
		}
	}
}

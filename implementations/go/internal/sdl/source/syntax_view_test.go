package source

import "testing"

func TestSyntaxPolicyBoundary(t *testing.T) {
	raw := []byte("key: yes\nkey: 'yes'\nnumber: 1e3\narray: [.nan, &x {nested: text}, *x]\n")
	root, err := ParseSyntax(raw, DefaultLimits(), "policy.yaml")
	if err != nil {
		t.Fatal(err)
	}
	if root.Kind() != "mapping" {
		t.Fatal(root.Kind())
	}
	pairs := root.Members()
	if len(pairs) != 4 {
		t.Fatalf("pairs=%d", len(pairs))
	}
	first, quoted := pairs[0].Value.Scalar()
	if first != "yes" || quoted {
		t.Fatal("plain scalar lost its spelling")
	}
	second, quoted := pairs[1].Value.Scalar()
	if second != "yes" || !quoted {
		t.Fatal("quoted scalar lost its style")
	}
	items := pairs[3].Value.Elements()
	if len(items) != 3 || items[1] != items[2] {
		t.Fatal("alias graph identity was expanded or lost")
	}
	pairs[0] = ViewMember{}
	if len(root.Members()) != 4 {
		t.Fatal("caller changed syntax members")
	}
	items[0] = View{}
	if root.Members()[3].Value.Elements()[0].Kind() != "scalar" {
		t.Fatal("caller changed syntax sequence")
	}
	if _, err = Decode(raw, DefaultOptions()); err == nil {
		t.Fatal("syntax parsing weakened SDL decoding")
	}
}
func TestSyntaxSourceLimits(t *testing.T) {
	limits := DefaultLimits()
	limits.MaxNodes = 1
	if _, err := ParseSyntax([]byte("key: value\n"), limits, "policy.yaml"); err == nil {
		t.Fatal("syntax ignored node limit")
	}
	for _, raw := range []string{"key: !!str yes\n", "a: 1\n---\nb: 2\n"} {
		if _, err := ParseSyntax([]byte(raw), DefaultLimits(), "policy.yaml"); err == nil {
			t.Fatal("syntax ignored presentation boundary")
		}
	}
	var absent View
	if absent.Kind() != "" || absent.Members() != nil || absent.Elements() != nil {
		t.Fatal("zero cursor is not absent")
	}
}

func TestViewMemberScope(t *testing.T) {
	document, err := Decode([]byte("schema_document: {DisplayName: {InnerKey: value}}\n"), DefaultOptions())
	if err != nil {
		t.Fatal(err)
	}
	root := document.View().Members()
	if len(root) != 1 {
		t.Fatal("missing embedded schema")
	}
	keys := root[0].Value.Keys()
	if len(keys) != 1 || keys[0] != "DisplayName" {
		t.Fatalf("lost data scope: %v", keys)
	}
	inner := root[0].Value.Members()[0].Value.Keys()
	if len(inner) != 1 || inner[0] != "InnerKey" {
		t.Fatalf("lost nested data scope: %v", inner)
	}
}

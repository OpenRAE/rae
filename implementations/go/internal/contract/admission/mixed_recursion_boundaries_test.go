package admission

import (
	"strconv"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func TestMixedCompositionBoundsNestedOwnerTraversal(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	raw, _ := mixedContextFixture(t, e, "simultaneous")
	for _, name := range []string{"work", "cycle", "profile-count", "components", "allocations", "edges", "phases", "transitions", "nested_profile_refs", "missing-child", "corrupt-child", "wrong-child-id", "wrong-child-digest", "invalid-time-owner"} {
		t.Run(name, func(t *testing.T) {
			_, owner := mixedContextFixture(t, e, "simultaneous")
			r, err := e.mixedResolution(owner)
			if err != nil {
				t.Fatal(err)
			}
			v := decodeRuleObject(t, string(raw))
			checked, err := mutateMixedTraversal(r, v, raw, name)
			if !checked {
				err = r.visit(v)
			}
			if err == nil {
				t.Fatal("unbounded or substituted composition owner admitted")
			}
		})
	}
}

func mutateMixedTraversal(r *mixedResolution, v any, raw []byte, name string) (bool, error) {
	id := stringAt(v, "profile_id")
	switch name {
	case "work":
		r.work = 100000
	case "cycle":
		r.visiting[id] = true
	case "profile-count":
		for n := range 64 {
			r.visited[strconv.Itoa(n)] = true
		}
	case "components", "allocations", "edges", "phases", "transitions", "nested_profile_refs":
		limit := map[string]int{"components": 64, "allocations": 1024, "edges": 1024, "phases": 256, "transitions": 512, "nested_profile_refs": 64}[name]
		rows := map[string]any{}
		for n := range limit + 1 {
			rows[strconv.Itoa(n)] = map[string]any{}
		}
		object(v)[name] = rows
	case "missing-child":
		return true, r.child("missing", "sha256:missing")
	case "corrupt-child":
		r.snapshot.NestedProfiles = map[string][]byte{"child": []byte("{")}
		return true, r.child("child", "sha256:missing")
	case "wrong-child-id":
		r.snapshot.NestedProfiles = map[string][]byte{"foreign": raw}
		return true, r.child("foreign", stringAt(v, "profile_digest"))
	case "wrong-child-digest":
		r.snapshot.NestedProfiles = map[string][]byte{id: raw}
		return true, r.child(id, "sha256:missing")
	case "invalid-time-owner":
		for key := range r.snapshot.TimeModels {
			r.snapshot.TimeModels[key] = validation.Value{}
		}
		return true, r.load()
	}
	return false, nil
}

func TestMixedCompositionReusesAnExactPreviouslyAdmittedChild(t *testing.T) {
	t.Parallel()
	e := boundTestOwner(t)
	raw, owner := mixedContextFixture(t, e, "simultaneous")
	r, err := e.mixedResolution(owner)
	if err != nil {
		t.Fatal(err)
	}
	v := decodeRuleObject(t, string(raw))
	id := stringAt(v, "profile_id")
	if err = r.visit(v); err != nil {
		t.Fatal(err)
	}
	r.snapshot.NestedProfiles = map[string][]byte{id: raw}
	if err = r.child(id, stringAt(v, "profile_digest")); err != nil {
		t.Fatal("refused exact previously admitted child", err)
	}
}

package fault

import (
	"errors"
	"fmt"
	"strings"
	"testing"
)

func TestCategoriesAndStandardErrorTraversal(t *testing.T) {
	cause := errors.New("private exception payload")
	for i, name := range []string{"invalid-input", "conflict", "not-found", "authorization", "operational", "evidence-integrity"} {
		category := Category(i + 1)
		err := New(category, "operation-1", cause)
		if err.Error() != name+": operation-1" || !errors.Is(err, cause) {
			t.Errorf("New(%s) = %v, want code without cause text and a wrapped cause", name, err)
		}
		var classified *Error
		if !errors.As(err, &classified) || classified.Code() != "operation-1" || classified.Category() != category {
			t.Errorf("errors.As(%s) = %+v, want classified error", name, classified)
		}
		got, ok := CategoryOf(fmt.Errorf("context: %w", err))
		if !ok || got != category {
			t.Errorf("CategoryOf(%s) = %v, %t, want %v, true", name, got, ok, category)
		}
	}
}

func TestErrorDefinitionsRefuseInvalidCategoriesAndCodes(t *testing.T) {
	for _, category := range []Category{0, 7, 255} {
		if category.String() != "unknown" || !errors.Is(New(category, "operation", nil), ErrDefinition) {
			t.Errorf("New(%d) did not refuse an undefined category", category)
		}
	}
	if _, ok := CategoryOf(nil); ok {
		t.Error("CategoryOf(nil) = classified, want unclassified")
	}
	for _, code := range []string{"", "A", "a_b", "a\nb", "é", strings.Repeat("a", 65)} {
		if !errors.Is(New(Operational, code, nil), ErrDefinition) {
			t.Errorf("New(invalid code %q) did not refuse it", code)
		}
	}
	if errors.Is(New(Operational, strings.Repeat("a", 64), nil), ErrDefinition) {
		t.Error("New(64-byte code) refused a valid boundary")
	}
}

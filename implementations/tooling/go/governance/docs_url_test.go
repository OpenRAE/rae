package governance

import "testing"

func TestDocumentationURLReference(t *testing.T) {
	for _, tc := range readReference[[]struct {
		Value, Error string
		Allowed      bool
	}](t, "docs-url-reference") {
		err := CheckDocumentationURL(tc.Value)
		if tc.Allowed {
			if err != nil {
				t.Errorf("URL %q refused: %v", tc.Value, err)
			}
		} else if err == nil || `"raw" `+err.Error() != tc.Error {
			t.Errorf("URL %q error=%v want=%q", tc.Value, err, tc.Error)
		}
	}
}

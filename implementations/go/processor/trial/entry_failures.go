package trial

import (
	"errors"
	"maps"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

type captureAdmissionError struct{ diagnostics []diagnostic.Diagnostic }

func (*captureAdmissionError) Error() string { return "trial-capture-admission-failed" }

type entryFailures struct {
	capture   map[[3]string]diagnostic.Diagnostic
	canonical *compilationRefusalError
}

func (f *entryFailures) add(err error, c coordinate) error {
	if capture, ok := errors.AsType[*captureAdmissionError](err); ok {
		if f.capture == nil {
			f.capture = map[[3]string]diagnostic.Diagnostic{}
		}
		for _, d := range capture.diagnostics {
			f.capture[[3]string{d.Address, d.Code, d.Message}] = d
		}
		return nil
	}
	var refusal *compilationRefusalError
	if !errors.As(err, &refusal) {
		category, known := fault.CategoryOf(err)
		if !known || category != fault.InvalidInput {
			return err
		}
		replicate := text(c.ReplicateID)
		if replicate == "" {
			replicate = "coordinate"
		}
		refusal = &compilationRefusalError{code: "entry-invalid", address: "/entries/" + replicate, message: "a trial entry failed closed construction"}
	}
	if f.canonical == nil || failureOrder(refusal, f.canonical) < 0 {
		f.canonical = refusal
	}
	return nil
}
func failureOrder(a, b *compilationRefusalError) int {
	if n := strings.Compare(a.address, b.address); n != 0 {
		return n
	}
	if n := strings.Compare(a.code, b.code); n != 0 {
		return n
	}
	return strings.Compare(a.message, b.message)
}
func (f *entryFailures) result() error {
	if len(f.capture) > 0 {
		keys := slices.SortedFunc(maps.Keys(f.capture), func(a, b [3]string) int {
			for index := range a {
				if order := strings.Compare(a[index], b[index]); order != 0 {
					return order
				}
			}
			return 0
		})
		diagnostics := make([]diagnostic.Diagnostic, len(keys))
		for index, key := range keys {
			diagnostics[index] = f.capture[key]
		}
		return &captureAdmissionError{diagnostics: diagnostics}
	}
	if f.canonical != nil {
		return f.canonical
	}
	return nil
}

package trial

import (
	"context"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

type panickingFactory struct{}

//nolint:ireturn // The installed factory contract returns its public interface.
func (panickingFactory) ForScenario(context.Context, sdl.Scenario) (admission.ParticipantControlContextValidator, error) {
	panic("private-factory-marker")
}

type panickingMixedContext struct {
	admission.MixedCompositionContext
}

func (panickingMixedContext) MixedCompositionSnapshot() admission.MixedCompositionSnapshot {
	panic("private-mixed-marker")
}
func TestCompilerIsolatesInstalledFactoryAndSnapshotPanics(t *testing.T) {
	t.Run("factory", func(t *testing.T) {
		request := typedCompilerRequest(t, typedReferences(t).Cases[1])
		request.ParticipantControlContextFactories[ConfigurationValidatorKey{"participant-config", "1"}] = panickingFactory{}
		_, err := CompileContext(context.Background(), request)
		category, known := fault.CategoryOf(err)
		if !known || category != fault.Operational || strings.Contains(err.Error(), "private-") {
			t.Fatal("owner panic or secret escaped", err)
		}
	})
	t.Run("snapshot", func(t *testing.T) {
		request := mixedCompilerRequest(t, mixedCompilerReferences(t)[0])
		for key, c := range request.MixedProfileContexts {
			request.MixedProfileContexts[key] = panickingMixedContext{c}
		}
		_, err := CompileContext(context.Background(), request)
		category, known := fault.CategoryOf(err)
		if !known || category != fault.Operational || strings.Contains(err.Error(), "private-") {
			t.Fatal("owner panic or secret escaped", err)
		}
	})
}

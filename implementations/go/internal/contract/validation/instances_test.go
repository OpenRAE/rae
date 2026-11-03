package validation

import (
	"errors"
	"strings"
	"testing"
	"testing/fstest"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

func TestInstanceChecksUseOriginalApplicableSchemas(t *testing.T) {
	source := sourceFixture()
	source["schemas/example.json"] = &fstest.MapFile{Data: []byte(`{"type":"object","properties":{"message":{"discriminator":{"propertyName":"kind"},"oneOf":[{"properties":{"kind":{"const":"a"},"value":{"type":"boolean"}},"required":["value"]},{"properties":{"kind":{"const":"b"},"count":{"type":"integer"}},"required":["count"]}]}}}`)}
	v, err := load(source, nil)
	if err != nil {
		t.Fatal(err)
	}
	limits := ingress.Limits{MaxBytes: 1000, MaxDepth: 16}
	check := func(instance SchemaInstance) error {
		if instance.Discriminator != "" {
			object, ok := instance.Value.(map[string]any)
			if !ok {
				return errors.New("private model detail")
			}
			if _, present := object[instance.Discriminator]; !present {
				return errors.New("private model detail")
			}
		}
		if strings.Contains(instance.SchemaPointer, "oneOf/1") {
			t.Error("inapplicable branch was checked")
		}
		return nil
	}
	if err := v.CheckInstances("example", []byte(`{"message":{"kind":"a","value":false}}`), limits, check); err != nil {
		t.Fatal(err)
	}
	withoutTag := []byte(`{"message":{"value":false}}`)
	if err := v.CheckSchema("example", withoutTag, limits); err != nil {
		t.Fatal("raw schema behavior changed", err)
	}
	if err := v.CheckInstances("example", withoutTag, limits, check); err == nil || strings.Contains(err.Error(), "private") {
		t.Errorf("model check error = %v, want safe refusal", err)
	}
}

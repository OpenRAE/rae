package admission

import (
	"strings"
	"testing"
	"testing/fstest"
)

func TestCatalogExactByteLimit(t *testing.T) {
	const limit = 8 * 1048576
	for _, size := range []int{limit - 1, limit, limit + 1} {
		raw := []byte(`{"value":1}` + strings.Repeat(" ", size-len(`{"value":1}`)))
		_, err := readCatalog(fstest.MapFS{"catalog.json": {Data: raw}}, "catalog.json")
		if (err == nil) != (size <= limit) {
			t.Errorf("catalog bytes %d: %v", size, err)
		}
	}
}

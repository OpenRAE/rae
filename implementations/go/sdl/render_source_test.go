package sdl_test

import (
	"context"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func TestRenderSourceUsesNativeModelOrderAndReadmission(t *testing.T) {
	source := []byte(`{"name":"external-web","version":"1.0.0","nodes":{"web":{"type":"compute"}}}`)
	scenario, err := sdl.Parse(source, sdl.DefaultParseOptions())
	if err != nil {
		t.Fatal(err)
	}
	rendered, err := sdl.RenderSource(context.Background(), scenario)
	if err != nil {
		t.Fatal(err)
	}
	if string(rendered) != "name: external-web\nversion: 1.0.0\nnodes:\n  web:\n    type: compute\n" {
		t.Fatalf("%s", rendered)
	}
	if _, err = sdl.Parse(rendered, sdl.DefaultParseOptions()); err != nil {
		t.Fatal(err)
	}
	if _, err = sdl.RenderSource(context.Background(), nil); err == nil {
		t.Fatal("nil scenario admitted")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err = sdl.RenderSource(ctx, scenario); err == nil {
		t.Fatal("cancellation ignored")
	}
}

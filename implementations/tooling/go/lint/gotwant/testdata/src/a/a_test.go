package a

import "testing"

func TestMessages(t *testing.T) {
	got, want := 1, 2
	t.Errorf("Add() = %d, want %d", got, want)
	t.Errorf("got %d, want %d", got, want)
	t.Errorf("want %d, got %d", want, got) // want `failure message prints want before got; print got first`
	t.Fatalf("Add(): want %d, got %d", want, got) // want `failure message prints want before got; print got first`
	t.Logf("want %d, got %d", want, got)
	t.Errorf("Add() mismatch (-want +got):\n%s", "diff")
	t.Errorf("Add() mismatch (-want +got): want %d, got %d", want, got) // want `failure message prints want before got; print got first`
	t.Errorf("wanted %d, gotten %d", want, got)
	message := "want %d, got %d"
	t.Errorf(message, want, got)
	const format = "want %d, got %d"
	t.Errorf(format, want, got) // want `failure message prints want before got; print got first`
	var notTesting fakeT
	notTesting.Errorf("want %d, got %d", want, got)
}

type fakeT struct{}

func (fakeT) Errorf(string, ...any) {}

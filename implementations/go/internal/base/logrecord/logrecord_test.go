package logrecord

import (
	"bytes"
	"context"
	"errors"
	"io"
	"log/slog"
	"strings"
	"testing"
	"time"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

type privateError struct{}

func (privateError) Error() string { panic("exception text must never be evaluated") }

type privateValue struct{ called *bool }

func (v privateValue) LogValue() slog.Value {
	*v.called = true
	panic("LogValue must never be evaluated")
}

func TestHostHandlersNeverReceiveErrorMessagesOrCallbacks(t *testing.T) {
	var output bytes.Buffer
	next := slog.NewJSONHandler(&output, &slog.HandlerOptions{AddSource: true})
	safe, err := NewHandler(next)
	if err != nil {
		t.Fatal(err)
	}
	called := false
	logger := slog.New(safe).With(slog.Any("fixed", privateError{})).WithGroup("group\n")
	logger.LogAttrs(context.Background(), slog.LevelError, "event\nforged",
		slog.Any("failure", fault.New(fault.Operational, "backend-failed", privateError{})),
		slog.Any("callback", privateValue{called: &called}),
		slog.String("metadata", "value\u2028next"),
	)
	text := output.String()
	if called || strings.Count(text, "\n") != 1 || strings.Contains(text, "/home/") {
		t.Errorf("host record = %s, callback = %t, want one value-free record without host paths", text, called)
	}
	for _, expected := range []string{"privateError", "backend-failed", "privateValue", "forged"} {
		if !strings.Contains(text, expected) {
			t.Errorf("host record = %s, want safe type/code metadata %s", text, expected)
		}
	}
	if safe.Enabled(context.Background(), slog.LevelDebug) {
		t.Error("Enabled(debug) = true, want the host handler's level policy")
	}
}

func TestRecordBoundsAndControlEscapes(t *testing.T) {
	for _, test := range [][2]string{
		{"\n\r\t", "\\n\\r\\t"}, {"\x00\x1f\x7f\u0085", "\\x00\\x1f\\x7f\\x85"},
		{"\u200e\u200f\u2028\u2029\u202a\u202e\u2066\u2069", "\\u200e\\u200f\\u2028\\u2029\\u202a\\u202e\\u2066\\u2069"},
		{"é\ufffd", "é\ufffd"},
	} {
		if got := Escape(test[0]); got != test[1] {
			t.Errorf("Escape(%q) = %q, want %q", test[0], got, test[1])
		}
	}
	if got := Escape(strings.Repeat("a", MaxMessage+1)); got != strings.Repeat("a", MaxMessage)+" [message truncated]" {
		t.Errorf("Escape(overlong record) length = %d, want a bounded marked record", len(got))
	}
	var err error = privateError{}
	for range MaxChain + 2 {
		err = fault.New(fault.Operational, "operation", err)
	}
	if got := Describe(err); strings.Count(got, "*fault.Error") != MaxChain || strings.Contains(got, "privateError") {
		t.Errorf("Describe(chain) = %s, want the bounded owned error chain", got)
	}
	if Describe(nil) != "" {
		t.Error("Describe(nil) is not empty")
	}
	var output bytes.Buffer
	safe, err := NewHandler(slog.NewJSONHandler(&output, nil))
	if err != nil {
		t.Fatal(err)
	}
	attrs := []slog.Attr{}
	for range MaxMembers {
		attrs = append(attrs, slog.Bool("flag", true))
	}
	attrs = append(attrs, slog.String("after_limit", "must be omitted"))
	record := slog.NewRecord(time.Time{}, slog.LevelInfo, "event", 0)
	record.AddAttrs(attrs...)
	nested := slog.String("leaf", "value")
	for range MaxDepth + 2 {
		nested = slog.Attr{Key: "nested", Value: slog.GroupValue(nested)}
	}
	grouped := safe.WithAttrs([]slog.Attr{nested})
	if err := grouped.Handle(context.Background(), record); err != nil {
		t.Fatal(err)
	}
	if got := output.String(); strings.Contains(got, "after_limit") || !strings.Contains(got, "group omitted") {
		t.Errorf("bounded record = %s, want bounded attributes and groups", got)
	}
}

type failedHandler struct{ panics bool }

func (failedHandler) Enabled(context.Context, slog.Level) bool { return true }
func (h failedHandler) Handle(context.Context, slog.Record) error {
	if h.panics {
		panic("foreign handler payload")
	}
	return io.ErrClosedPipe
}
func (h failedHandler) WithAttrs([]slog.Attr) slog.Handler { return h }
func (h failedHandler) WithGroup(string) slog.Handler      { return h }

func TestHandlerFailuresAreValueFreeAndNilIsRefused(t *testing.T) {
	if _, err := NewHandler(nil); !errors.Is(err, ErrHandler) {
		t.Errorf("NewHandler(nil) error = %v, want ErrHandler", err)
	}
	var absent *slog.JSONHandler
	if _, err := NewHandler(absent); !errors.Is(err, ErrHandler) {
		t.Errorf("NewHandler(typed nil) error = %v, want ErrHandler", err)
	}
	for _, panics := range []bool{false, true} {
		safe, err := NewHandler(failedHandler{panics: panics})
		if err != nil {
			t.Fatal(err)
		}
		err = safe.Handle(context.Background(), slog.NewRecord(time.Time{}, slog.LevelInfo, "event", 0))
		want := io.ErrClosedPipe
		if panics {
			want = ErrHandler
		}
		if !errors.Is(err, want) {
			t.Errorf("Handle(panics=%t) error = %v, want %v", panics, err, want)
		}
	}
}

func TestGroupDepthExactFitsAndEscapeEndpoints(t *testing.T) {
	for _, test := range [][2]string{{" \u009f\u00a0", " \\x9f\u00a0"}, {"\u001f!", "\\x1f!"}} {
		if got := Escape(test[0]); got != test[1] {
			t.Errorf("Escape(%q) = %q, want %q", test[0], got, test[1])
		}
	}
	for depth := 0; depth <= MaxDepth+1; depth++ {
		var out bytes.Buffer
		safe, err := NewHandler(slog.NewJSONHandler(&out, nil))
		if err != nil {
			t.Fatal(err)
		}
		attr := slog.String("leaf", "permitted")
		for range depth {
			attr = slog.Group("group", attr)
		}
		record := slog.NewRecord(time.Time{}, slog.LevelInfo, "event", 0)
		record.AddAttrs(attr)
		if err := safe.Handle(context.Background(), record); err != nil {
			t.Fatal(err)
		}
		if got := strings.Contains(out.String(), "permitted"); got != (depth <= MaxDepth) {
			t.Errorf("depth %d leaf included = %t, want %t", depth, got, depth <= MaxDepth)
		}
	}
}

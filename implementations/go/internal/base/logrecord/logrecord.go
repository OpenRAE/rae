// Package logrecord makes operational records value-free before a host handler
// receives them. Libraries never configure global logging.
package logrecord

import (
	"context"
	"fmt"
	"log/slog"
	"reflect"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/fault"
)

// The bounded record limits retain the ADR-116 chain/group/message ceilings.
const (
	MaxChain   = 8
	MaxDepth   = 4
	MaxMembers = 16
	MaxMessage = 8192
)

// ErrHandler is the value-free failure of a logging handler.
var ErrHandler = fault.New(fault.Operational, "logging-handler", nil)

type handler struct{ next slog.Handler }

// NewHandler wraps a host handler without changing any global logger.
func NewHandler(next slog.Handler) (slog.Handler, error) {
	if next == nil || reflect.ValueOf(next).Kind() == reflect.Pointer && reflect.ValueOf(next).IsNil() {
		return nil, ErrHandler
	}
	return &handler{next: next}, nil
}

func (h *handler) Enabled(ctx context.Context, level slog.Level) bool {
	return h.next.Enabled(ctx, level)
}

func (h *handler) Handle(ctx context.Context, record slog.Record) (err error) {
	defer func() {
		if recover() != nil {
			err = ErrHandler
		}
	}()
	// Discard the source PC: a host AddSource formatter must not expose an
	// absolute host path. Error values never contain exception text or stacks.
	safe := slog.NewRecord(record.Time, record.Level, Escape(record.Message), 0)
	count := 0
	record.Attrs(func(attr slog.Attr) bool {
		if count == MaxMembers {
			return false
		}
		safe.AddAttrs(cleanAttr(attr, 0))
		count++
		return true
	})
	return h.next.Handle(ctx, safe)
}

func (h *handler) WithAttrs(attrs []slog.Attr) slog.Handler {
	return &handler{next: h.next.WithAttrs(cleanAttrs(attrs, 0))}
}

func (h *handler) WithGroup(name string) slog.Handler {
	return &handler{next: h.next.WithGroup(Escape(name))}
}

func cleanAttrs(attrs []slog.Attr, depth int) []slog.Attr {
	clean := make([]slog.Attr, 0, min(len(attrs), MaxMembers))
	for _, attr := range attrs[:min(len(attrs), MaxMembers)] {
		clean = append(clean, cleanAttr(attr, depth))
	}
	return clean
}

func cleanAttr(attr slog.Attr, depth int) slog.Attr {
	attr.Key = Escape(attr.Key)
	switch attr.Value.Kind() {
	case slog.KindAny, slog.KindLogValuer:
		value := attr.Value.Any() // Does not resolve or call a LogValuer.
		if err, ok := value.(error); ok {
			attr.Value = slog.StringValue(Describe(err))
		} else {
			attr.Value = slog.StringValue(Escape(fmt.Sprintf("%T", value)))
		}
	case slog.KindString:
		attr.Value = slog.StringValue(Escape(attr.Value.String()))
	case slog.KindTime:
		attr.Value = slog.StringValue(attr.Value.Time().UTC().Format("2006-01-02T15:04:05.999999999Z"))
	case slog.KindGroup:
		if depth == MaxDepth {
			attr.Value = slog.StringValue("[group omitted]")
		} else {
			attr.Value = slog.GroupValue(cleanAttrs(attr.Value.Group(), depth+1)...)
		}
	case slog.KindBool, slog.KindDuration, slog.KindFloat64, slog.KindInt64, slog.KindUint64:
		// Primitive structured metadata has no callback or exception payload.
	}
	return attr
}

// Describe never invokes Error, String, LogValue or an unknown Unwrap method.
// Only the owned fault.Error chain is traversed; foreign failures retain types.
func Describe(err error) string {
	var chain []string
	for len(chain) < MaxChain && err != nil {
		name := fmt.Sprintf("%T", err)
		switch classified := err.(type) { //nolint:errorlint // Only owned errors may be traversed; errors.As invokes foreign callbacks.
		case *fault.Error:
			if classified == nil {
				return Escape(strings.Join(append(chain, name), " <- "))
			}
			chain = append(chain, name+"["+classified.Category().String()+":"+classified.Code()+"]")
			err = classified.Unwrap()
		default:
			return Escape(strings.Join(append(chain, name), " <- "))
		}
	}
	return Escape(strings.Join(chain, " <- "))
}

// Escape prevents control characters, bidi controls and Unicode line separators
// from forging log records, and bounds the encoded record text.
func Escape(text string) string {
	var out strings.Builder
	characters := 0
	for _, r := range text {
		for _, escaped := range escapedRune(r) {
			if characters == MaxMessage {
				return out.String() + " [message truncated]"
			}
			out.WriteRune(escaped)
			characters++
		}
	}
	return out.String()
}

func escapedRune(r rune) string {
	switch r {
	case '\n':
		return "\\n"
	case '\r':
		return "\\r"
	case '\t':
		return "\\t"
	}
	if r < 0x20 || r >= 0x7f && r <= 0x9f {
		return fmt.Sprintf("\\x%02x", r)
	}
	if r == 0x200e || r == 0x200f || r >= 0x2028 && r <= 0x202e || r >= 0x2066 && r <= 0x2069 {
		return fmt.Sprintf("\\u%04x", r)
	}
	return string(r)
}

package parity

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"

	"github.com/OpenRAE/rae/implementations/go/internal/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/internal/base/clock"
	"github.com/OpenRAE/rae/implementations/go/internal/base/digest"
	"github.com/OpenRAE/rae/implementations/go/internal/base/domain"
	"github.com/OpenRAE/rae/implementations/go/internal/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/base/graph"
	"github.com/OpenRAE/rae/implementations/go/internal/base/logrecord"
	"github.com/OpenRAE/rae/implementations/go/internal/base/secretref"
	"github.com/OpenRAE/rae/implementations/go/internal/base/softwareversion"
	"github.com/OpenRAE/rae/implementations/go/internal/base/timestamp"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

type sharedRequest struct {
	Mode       string              `json:"mode"`
	Text       string              `json:"text"`
	Relation   string              `json:"relation"`
	Lower      *string             `json:"lower"`
	Upper      *string             `json:"upper"`
	Actual     json.RawMessage     `json:"actual"`
	Closed     *bool               `json:"closed"`
	Mutation   map[string]string   `json:"mutation"`
	Descriptor json.RawMessage     `json:"descriptor"`
	Value      json.RawMessage     `json:"value"`
	Graph      map[string][]string `json:"graph"`
	Reverse    bool                `json:"reverse"`
	Document   bool                `json:"document"`
	Canonical  bool                `json:"canonical"`
	Limits     json.RawMessage     `json:"limits"`
}

// shared runs only the closed primitives covered by issue #1779.
func shared(_ context.Context, c Case) (json.RawMessage, error) {
	var request sharedRequest
	if err := json.Unmarshal(c.Files["request.json"], &request); err != nil {
		return nil, err
	}
	var result map[string]any
	var err error
	switch c.Command {
	case "timestamp":
		result = sharedTimestamp(request)
	case "version":
		result, err = sharedVersion(request)
	case "domain":
		result, err = sharedDomain(request)
	case "graph":
		result, err = sharedGraph(request)
	case "value":
		result, err = sharedValue(request)
	case "carrier":
		_, refusal := value.Canonical(struct{ Unmodeled bool }{true}, value.Default())
		result = map[string]any{"accepted": refusal == nil}
	case "secret":
		result = map[string]any{validField: secretref.Valid(request.Text)}
	case "digest":
		result = map[string]any{validField: digest.Valid(request.Text)}
	case "log":
		result = map[string]any{"text": logrecord.Escape(request.Text)}
	case "fault":
		result = sharedFault()
	case "clock":
		instant, failure := timestamp.ParseAssumingUTC(request.Text)
		if failure != nil {
			return nil, failure
		}
		read := clock.Read(instant.Instant)
		result = map[string]any{"utc": timestamp.Format(read)}
	default:
		return nil, fmt.Errorf("unknown shared command: %s", c.Command)
	}
	if err != nil {
		return nil, err
	}
	return json.Marshal(result)
}

func sharedTimestamp(request sharedRequest) map[string]any {
	var parsed timestamp.Time
	var err error
	switch request.Mode {
	case "rfc3339":
		parsed, err = timestamp.ParseRFC3339("at", request.Text)
	case "utc":
		parsed, err = timestamp.ParseOffsetUTC(request.Text)
	case "offset":
		parsed, err = timestamp.ParseOffset("at", request.Text)
	case "assuming":
		parsed, err = timestamp.ParseAssumingUTC(request.Text)
	default:
		err = timestamp.ErrInput
	}
	if err != nil {
		code := invalidCode
		if errors.Is(err, timestamp.ErrLeap) {
			code = "leap"
		}
		return map[string]any{"ok": false, codeField: code}
	}
	return map[string]any{"ok": true, "text": parsed.String()}
}

func sharedVersion(request sharedRequest) (map[string]any, error) {
	identity, err := softwareversion.Installed(request.Relation)
	if err != nil {
		text, marshalErr := json.Marshal(map[string]string{"relation": request.Relation, "revision": "1"})
		if marshalErr != nil {
			return nil, marshalErr
		}
		canonical, canonicalErr := canonjson.JCS(text)
		if canonicalErr != nil {
			return nil, canonicalErr
		}
		identity = softwareversion.Relation{
			Authority: "https://openrae.org/semantics/versions", ID: request.Relation,
			Revision: "1", Digest: digest.SHA256(canonical),
		}
	}
	for key, replacement := range request.Mutation {
		switch key {
		case "authority":
			identity.Authority = replacement
		case "revision":
			identity.Revision = replacement
		case "digest":
			identity.Digest = replacement
		}
	}
	closed := request.Closed == nil || *request.Closed
	restriction, err := softwareversion.NewDomain(identity, request.Lower, request.Upper, closed, closed)
	if err != nil {
		return map[string]any{validField: false}, nil //nolint:nilerr // Expected primitive refusals are parity results, not runner failures.
	}
	actual, err := sharedJSON(request.Actual)
	if err != nil {
		return nil, err
	}
	return map[string]any{validField: true, "membership": restriction.Membership(actual)}, nil
}

func sharedJSON(text json.RawMessage) (any, error) {
	reader := json.NewDecoder(bytes.NewReader(text))
	reader.UseNumber()
	var decoded any
	if err := reader.Decode(&decoded); err != nil {
		return nil, err
	}
	if _, err := reader.Token(); !errors.Is(err, io.EOF) {
		return nil, errors.New("shared primitive: data follows a JSON value")
	}
	return decoded, nil
}

func sharedDomain(request sharedRequest) (map[string]any, error) {
	descriptor, err := readDomain(request.Descriptor)
	if err != nil {
		return map[string]any{validField: false}, nil //nolint:nilerr // Expected primitive refusals are parity results, not runner failures.
	}
	decoded, err := sharedJSON(request.Value)
	if err != nil {
		return nil, err
	}
	member, err := domain.In(decoded, descriptor)
	if errors.Is(err, domain.ErrValue) {
		return map[string]any{validField: true, "refusal": "numeric-overflow"}, nil
	}
	if err != nil {
		return map[string]any{validField: false}, nil //nolint:nilerr // Expected primitive refusals are parity results, not runner failures.
	}
	return map[string]any{validField: true, "member": member}, nil
}

func readDomain(data json.RawMessage) (domain.Domain, error) { //nolint:ireturn // The closed domain algebra has several concrete variants.
	var fields struct {
		Kind        string            `json:"kind"`
		Value       json.RawMessage   `json:"value"`
		Values      []json.RawMessage `json:"values"`
		NumericType string            `json:"numeric_type"`
		Lower       float64           `json:"lower"`
		Upper       float64           `json:"upper"`
		LowerClosed bool              `json:"lower_closed"`
		UpperClosed bool              `json:"upper_closed"`
		Authority   string            `json:"authority"`
		Allowed     []string          `json:"allowed_refs"`
		Fields      map[string]string `json:"fields"`
		Extra       bool              `json:"extra"`
	}
	fields.LowerClosed, fields.UpperClosed = true, true
	if err := json.Unmarshal(data, &fields); err != nil {
		return nil, err
	}
	switch fields.Kind {
	case "exact":
		decoded, err := sharedJSON(fields.Value)
		return domain.Exact{Value: decoded}, err
	case "enum":
		values := make([]any, len(fields.Values))
		for i, item := range fields.Values {
			decoded, err := sharedJSON(item)
			if err != nil {
				return nil, err
			}
			values[i] = decoded
		}
		return domain.Enumeration{Values: values}, nil
	case "boolean":
		var selection *bool
		if len(fields.Value) != 0 {
			if err := json.Unmarshal(fields.Value, &selection); err != nil {
				return nil, err
			}
		}
		return domain.Boolean{Value: selection}, nil
	case "null":
		return domain.Null{}, nil
	case "numeric-interval":
		kind := domain.NumericType(0)
		switch fields.NumericType {
		case "integer":
			kind = domain.Integer
		case "number":
			kind = domain.Number
		}
		return domain.Interval{Type: kind, Lower: fields.Lower, Upper: fields.Upper,
			LowerClosed: fields.LowerClosed, UpperClosed: fields.UpperClosed}, nil
	case "governed-reference":
		return domain.References{Authority: fields.Authority, Allowed: fields.Allowed}, nil
	case "record":
		return domain.Record{Fields: fields.Fields, Extra: fields.Extra}, nil
	default:
		return nil, domain.ErrInput
	}
}

func sharedGraph(request sharedRequest) (map[string]any, error) {
	var less graph.Less
	if request.Reverse {
		less = func(a, b string) bool { return a > b }
	}
	order, err := graph.Order(request.Graph, less)
	if err != nil {
		return nil, err
	}
	components, err := graph.Cycles(request.Graph, less)
	if err != nil {
		return nil, err
	}
	return map[string]any{"cycle": graph.HasCycle(request.Graph), "order": order, "components": components}, nil
}

func sharedValue(request sharedRequest) (map[string]any, error) {
	limits, err := readLimits(request.Limits)
	if err != nil {
		return map[string]any{statusField: "invalid-limits"}, nil //nolint:nilerr // A refused limit definition is the recorded result.
	}

	payload, err := sharedJSON(request.Value)
	if err != nil {
		return nil, err
	}
	if request.Document {
		fields, ok := payload.(map[string]any)
		if !ok {
			return nil, value.ErrInput
		}
		text, ok := fields["body"].(string)
		if !ok {
			return nil, value.ErrInput
		}
		fields["body"] = value.DeclaredDocument(text)
	}
	failure := value.Validate(payload, limits)
	if failure != nil {
		status := invalidCode
		if errors.Is(failure, value.ErrLimit) {
			status = "limit-exceeded"
		}
		return map[string]any{statusField: status}, nil
	}
	result := map[string]any{statusField: "conformant"}
	if request.Canonical {
		canonical, err := value.Canonical(payload, limits)
		if err != nil {
			return map[string]any{statusField: invalidCode}, nil //nolint:nilerr // Expected primitive refusals are parity results, not runner failures.
		}
		result["canonical"] = string(canonical)
	}
	return result, nil
}

func sharedFault() map[string]any {
	categories := []string{}
	hierarchy := true
	for _, kind := range []fault.Category{fault.InvalidInput, fault.Conflict, fault.NotFound, fault.Authorization, fault.Operational, fault.EvidenceIntegrity} {
		categories = append(categories, kind.String())
		classified, ok := fault.CategoryOf(fault.New(kind, "parity", nil))
		hierarchy = hierarchy && ok && classified == kind
	}
	return map[string]any{"categories": categories, "hierarchy": hierarchy}
}

func readLimits(data json.RawMessage) (value.Limits, error) {
	limits := value.Default()
	if len(data) != 0 {
		reader := json.NewDecoder(bytes.NewReader(data))
		reader.DisallowUnknownFields()
		if err := reader.Decode(&limits); err != nil {
			return value.Limits{}, err
		}
		if _, err := reader.Token(); !errors.Is(err, io.EOF) {
			return value.Limits{}, value.ErrLimits
		}
	}
	if err := limits.Validate(); err != nil {
		return value.Limits{}, err
	}
	return limits, nil
}

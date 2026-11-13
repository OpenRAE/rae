package admission

import (
	"encoding/json"
	"reflect"
	"strings"
	"unicode/utf8"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

type transportValue struct {
	value  reflect.Value
	charge bool
}
type transportProjection struct {
	limits value.Limits
	bytes  int
}

// CheckTransport bounds native generated records before serialization. It
// grants no schema or semantic admission and invokes no supplied methods.
func CheckTransport(document any, limits ingress.Limits) error {
	root := reflect.ValueOf(document)
	if root.Kind() == reflect.Pointer {
		if root.IsNil() {
			return invalid()
		}
		root = root.Elem()
	}
	if root.Kind() != reflect.Struct || root.Type().PkgPath() != reflect.TypeFor[binding.RuntimeSnapshotV1]().PkgPath() || strings.HasPrefix(root.Type().Name(), "Field[") || limits.MaxBytes < 1 || limits.MaxDepth < 0 {
		return invalid()
	}
	work := value.Plan()
	work.MaxDepth = 1024
	if limits.MaxDepth > 0 {
		work.MaxDepth = min(limits.MaxDepth, work.MaxDepth)
	}
	work.MaxScalarBytes = min(8<<20, limits.MaxBytes)
	work.MaxTotalScalarBytes = min(64<<20, limits.MaxBytes)
	work.MaxDocumentScalarBytes = 0
	projection := transportProjection{limits: work, bytes: limits.MaxBytes}
	return value.ValidateProjected(transportValue{root, true}, work, projection.project)
}

func (p *transportProjection) spend(count int) error {
	if count < 0 || count > p.bytes {
		return value.ErrLimit
	}
	p.bytes -= count
	return nil
}
func jsonStringSize(text string) (int, error) {
	if !utf8.ValidString(text) {
		return 0, value.ErrInput
	}
	size := 2
	for _, char := range text {
		switch char {
		case '"', '\\', '\b', '\f', '\n', '\r', '\t':
			size += 2
		case '<', '>', '&', '\u2028', '\u2029':
			size += 6
		default:
			if char < 0x20 {
				size += 6
			} else {
				size += utf8.RuneLen(char)
			}
		}
	}
	return size, nil
}

func (p *transportProjection) chargeBytes(enabled bool, count int) error {
	if enabled {
		return p.spend(count)
	}
	return nil
}

func unwrapTransportValue(input reflect.Value) (reflect.Value, error) {
	for hops := 0; input.IsValid() && (input.Kind() == reflect.Pointer || input.Kind() == reflect.Interface); hops++ {
		if hops >= 64 {
			return reflect.Value{}, value.ErrLimit
		}
		if input.IsNil() {
			return reflect.Value{}, nil
		}
		input = input.Elem()
	}
	return input, nil
}

func (p *transportProjection) project(input any) (any, error) {
	item, ok := input.(transportValue)
	if !ok {
		return nil, value.ErrInput
	}
	unwrapped, err := unwrapTransportValue(item.value)
	if err != nil {
		return nil, err
	}
	item.value = unwrapped
	if !unwrapped.IsValid() {
		return nil, p.chargeBytes(item.charge, 4)
	}
	if unwrapped.Type() == reflect.TypeFor[json.RawMessage]() {
		return p.raw(item)
	}
	return p.typed(item)
}

func (p *transportProjection) typed(item transportValue) (any, error) {
	switch item.value.Kind() {
	case reflect.Struct:
		return p.record(item)
	case reflect.Map:
		return p.mapping(item)
	case reflect.Slice, reflect.Array:
		return p.sequence(item)
	case reflect.String:
		return p.text(item)
	case reflect.Bool:
		return p.boolean(item)
	case reflect.Invalid, reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64,
		reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64, reflect.Uintptr,
		reflect.Float32, reflect.Float64, reflect.Complex64, reflect.Complex128, reflect.Chan, reflect.Func,
		reflect.Interface, reflect.Pointer, reflect.UnsafePointer:
		return nil, value.ErrInput
	}
	return nil, value.ErrInput
}

func (p *transportProjection) raw(item transportValue) (any, error) {
	raw := item.value.Bytes()
	if len(raw) == 0 {
		return nil, p.chargeBytes(item.charge, 4)
	}
	if len(raw) > p.bytes || !utf8.Valid(raw) || !json.Valid(raw) {
		return nil, value.ErrInput
	}
	parsed, err := ingress.Parse(append(append([]byte{'['}, raw...), ']'), ingress.Limits{MaxBytes: len(raw) + 2, MaxDepth: p.limits.MaxDepth + 1}, ingress.Array)
	if err != nil {
		return nil, err
	}
	if err := p.chargeBytes(item.charge, rawTransportSize(raw)); err != nil {
		return nil, err
	}
	array, ok := parsed.([]any)
	if !ok || len(array) != 1 {
		return nil, value.ErrInput
	}
	return p.project(transportValue{reflect.ValueOf(array[0]), false})
}

func transportField(record reflect.Value, index int) (string, reflect.Value, bool, error) {
	definition := record.Type().Field(index)
	name, _, _ := strings.Cut(definition.Tag.Get("json"), ",")
	if name == "" || name == "-" || definition.PkgPath != "" {
		return "", reflect.Value{}, false, value.ErrInput
	}
	field := record.Field(index)
	if field.Kind() != reflect.Struct || field.Type().PkgPath() != record.Type().PkgPath() || !strings.HasPrefix(field.Type().Name(), "Field[") {
		return name, field, true, nil
	}
	present, stored := field.FieldByName("present"), field.FieldByName("value")
	if !present.IsValid() || present.Kind() != reflect.Bool || !stored.IsValid() || stored.Kind() != reflect.Pointer {
		return "", reflect.Value{}, false, value.ErrInput
	}
	return name, stored, present.Bool(), nil
}

func (p *transportProjection) record(item transportValue) (any, error) {
	record := item.value
	if record.Type().PkgPath() != reflect.TypeFor[binding.RuntimeSnapshotV1]().PkgPath() {
		return nil, value.ErrInput
	}
	result := map[string]any{}
	for i := range record.NumField() {
		name, field, present, err := transportField(record, i)
		if err != nil {
			return nil, err
		}
		if present {
			result[name] = transportValue{field, item.charge}
		}
	}
	if item.charge {
		if err := p.objectSize(result); err != nil {
			return nil, err
		}
	}
	return result, nil
}

func (p *transportProjection) mapping(item transportValue) (any, error) {
	mapping := item.value
	if mapping.Type().Key().Kind() != reflect.String || mapping.Len() > p.limits.MaxMembers {
		return nil, value.ErrInput
	}
	if mapping.IsNil() {
		return nil, p.chargeBytes(item.charge, 4)
	}
	result := make(map[string]any, mapping.Len())
	iterator := mapping.MapRange()
	for iterator.Next() {
		result[iterator.Key().String()] = transportValue{iterator.Value(), item.charge}
	}
	if item.charge {
		if err := p.objectSize(result); err != nil {
			return nil, err
		}
	}
	return result, nil
}

func (p *transportProjection) sequence(item transportValue) (any, error) {
	sequence := item.value
	if sequence.Len() > p.limits.MaxMembers {
		return nil, value.ErrLimit
	}
	if sequence.Kind() == reflect.Slice && sequence.IsNil() {
		return nil, p.chargeBytes(item.charge, 4)
	}
	if err := p.chargeBytes(item.charge, 2+max(0, sequence.Len()-1)); err != nil {
		return nil, err
	}
	result := make([]any, sequence.Len())
	for i := range result {
		result[i] = transportValue{sequence.Index(i), item.charge}
	}
	return result, nil
}

func (p *transportProjection) text(item transportValue) (any, error) {
	text := item.value.String()
	if item.value.Type() == reflect.TypeFor[json.Number]() {
		if err := p.chargeBytes(item.charge, len(text)); err != nil {
			return nil, err
		}
		return json.Number(text), nil
	}
	size, err := jsonStringSize(text)
	if err != nil {
		return nil, err
	}
	if err := p.chargeBytes(item.charge, size); err != nil {
		return nil, err
	}
	return text, nil
}

func (p *transportProjection) boolean(item transportValue) (any, error) {
	size := 5
	if item.value.Bool() {
		size = 4
	}
	if err := p.chargeBytes(item.charge, size); err != nil {
		return nil, err
	}
	return item.value.Bool(), nil
}

func (p *transportProjection) objectSize(object map[string]any) error {
	if err := p.spend(2 + max(0, len(object)-1) + len(object)); err != nil {
		return err
	}
	for key := range object {
		size, err := jsonStringSize(key)
		if err != nil {
			return err
		}
		if err := p.spend(size); err != nil {
			return err
		}
	}
	return nil
}

// encoding/json compacts RawMessage while retaining its lexical escapes.
// Count that representation, including its HTML and line-separator escaping.
type rawTransportCounter struct {
	size            int
	quoted, escaped bool
}

func rawTransportSize(raw []byte) int {
	counter := rawTransportCounter{}
	for index := 0; index < len(raw); index++ {
		index = counter.step(raw, index)
	}
	return counter.size
}

func (counter *rawTransportCounter) step(raw []byte, index int) int {
	char := raw[index]
	if !counter.quoted {
		if char == ' ' || char == '\n' || char == '\t' || char == '\r' {
			return index
		}
		counter.quoted = char == '"'
		counter.size++
		return index
	}
	if counter.escaped {
		counter.escaped = false
		counter.size++
		return index
	}
	switch char {
	case '\\':
		counter.escaped = true
	case '"':
		counter.quoted = false
	case '<', '>', '&':
		counter.size += 6
		return index
	default:
		if char == 0xe2 && index+2 < len(raw) && raw[index+1] == 0x80 && (raw[index+2] == 0xa8 || raw[index+2] == 0xa9) {
			counter.size += 6
			return index + 2
		}
	}
	counter.size++
	return index
}

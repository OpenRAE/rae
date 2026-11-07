package governance

import "testing"

func TestSchemaUnevaluatedLocations(t *testing.T) {
	for _, tc := range []struct{ schema, value, location string }{
		{`{"unevaluatedProperties":false}`, `{"x":1}`, "<root>"},
		{`{"unevaluatedProperties":{"propertyNames":{"pattern":"^a"}}}`, `{"extra":{"bad":1}}`, "<root>"},
		{`{"unevaluatedItems":false}`, `[1]`, "<root>"},
		{`{"properties":{"value":{"unevaluatedProperties":false}}}`, `{"value":{"x":1}}`, "value"},
		{`{"unevaluatedProperties":{"type":"object","properties":{"x":{"type":"integer"}}}}`, `{"extra":{"x":"wrong"}}`, "<root>"},
	} {
		schema, err := candidateSchema([]byte(tc.schema))
		if err != nil {
			t.Fatal(err)
		}
		value, err := decodeJSON([]byte(tc.value), 0, false)
		if err != nil {
			t.Fatal(err)
		}
		err = schema.Validate(schemaTransport(value))
		if err == nil {
			t.Fatal("missing unevaluated error")
		}
		if got := schemaErrorLocation(err, value); got != tc.location {
			t.Errorf("location=%s want=%s error=%#v", got, tc.location, err)
		}
	}
}

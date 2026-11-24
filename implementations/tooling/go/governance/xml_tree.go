package governance

import (
	"bytes"
	"encoding/xml"
	"errors"
	"io"
	"slices"
	"strings"
	"unicode/utf16"
)

type xmlElement struct {
	name       xml.Name
	attributes []xml.Attr
	text       strings.Builder
	children   []*xmlElement
}

// encoding/xml performs no external retrieval. DTDs are outside the admitted
// workbook/documentation profile, which needs only predefined XML entities.
func parsePolicyXML(data []byte) (*xmlElement, error) {
	data, converted, err := workbookXMLBytes(data)
	if err != nil {
		return nil, err
	}
	decoder := xml.NewDecoder(bytes.NewReader(data))
	if converted {
		decoder.CharsetReader = func(name string, input io.Reader) (io.Reader, error) {
			if strings.EqualFold(name, "utf-16") {
				return input, nil
			}
			return nil, policyInputError("artifact XML declares an inconsistent encoding")
		}
	}
	state := xmlDocumentState{}
	for {
		token, err := decoder.Token()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return nil, policyInputError("artifact contains invalid XML")
		}
		if err := state.accept(token); err != nil {
			return nil, err
		}
	}
	if state.root == nil || len(state.stack) > 0 {
		return nil, policyInputError("artifact XML has no complete root")
	}
	return state.root, nil
}

type xmlDocumentState struct {
	root  *xmlElement
	stack []*xmlElement
}

func (s *xmlDocumentState) accept(token xml.Token) error {
	switch token := token.(type) {
	case xml.Directive:
		return policyInputError("artifact declares an XML entity or DTD")
	case xml.StartElement:
		return s.start(token)
	case xml.EndElement:
		if len(s.stack) == 0 {
			return policyInputError("artifact XML has an unmatched closing tag")
		}
		s.stack = s.stack[:len(s.stack)-1]
	case xml.CharData:
		return s.characters(token)
	}
	return nil
}
func (s *xmlDocumentState) start(token xml.StartElement) error {
	seen := make(map[xml.Name]bool, len(token.Attr))
	for _, attribute := range token.Attr {
		if seen[attribute.Name] {
			return policyInputError("artifact XML repeats an attribute")
		}
		seen[attribute.Name] = true
	}
	node := &xmlElement{name: token.Name, attributes: token.Attr}
	if len(s.stack) > 0 {
		parent := s.stack[len(s.stack)-1]
		parent.children = append(parent.children, node)
	} else {
		if s.root != nil {
			return policyInputError("artifact XML has multiple roots")
		}
		s.root = node
	}
	s.stack = append(s.stack, node)
	return nil
}
func (s *xmlDocumentState) characters(token xml.CharData) error {
	if len(s.stack) > 0 {
		node := s.stack[len(s.stack)-1]
		if len(node.children) == 0 {
			node.text.Write(token)
		}
	} else if len(bytes.Trim(token, " \t\r\n")) > 0 {
		return policyInputError("artifact XML has text outside its root")
	}
	return nil
}

// XML autodetects UTF-16 before its declaration can be read. Keep that small
// encoding boundary here; encoding/xml still owns the document grammar.
func workbookXMLBytes(data []byte) ([]byte, bool, error) {
	data = bytes.TrimPrefix(data, []byte{0xef, 0xbb, 0xbf})
	if len(data) < 2 {
		return data, false, nil
	}
	little := data[0] == 0xff && data[1] == 0xfe || data[0] == '<' && data[1] == 0
	big := data[0] == 0xfe && data[1] == 0xff || data[0] == 0 && data[1] == '<'
	if !little && !big {
		return data, false, nil
	}
	if len(data)%2 != 0 {
		return nil, false, policyInputError("artifact XML contains truncated UTF-16")
	}
	units := make([]uint16, len(data)/2)
	for i := range units {
		units[i] = uint16(data[2*i])<<8 | uint16(data[2*i+1])
		if little {
			units[i] = uint16(data[2*i+1])<<8 | uint16(data[2*i])
		}
	}
	if units[0] == 0xfeff {
		units = units[1:]
	}
	converted, err := workbookUTF16(units)
	return converted, true, err
}

func workbookUTF16(units []uint16) ([]byte, error) {
	var out strings.Builder
	for i := 0; i < len(units); i++ {
		unit := units[i]
		switch {
		case unit >= 0xd800 && unit <= 0xdbff:
			if i+1 == len(units) || units[i+1] < 0xdc00 || units[i+1] > 0xdfff {
				return nil, policyInputError("artifact XML contains invalid UTF-16")
			}
			i++
			out.WriteRune(utf16.DecodeRune(rune(unit), rune(units[i])))
		case unit >= 0xdc00 && unit <= 0xdfff:
			return nil, policyInputError("artifact XML contains invalid UTF-16")
		default:
			out.WriteRune(rune(unit))
		}
	}
	return []byte(out.String()), nil
}

func (n *xmlElement) attribute(name string) string {
	for _, attribute := range n.attributes {
		if attribute.Name.Space == "" && attribute.Name.Local == name {
			return attribute.Value
		}
	}
	return ""
}
func (n *xmlElement) elements(space, name string, recursive bool) []*xmlElement {
	result := []*xmlElement{}
	pending := []*xmlElement{}
	for _, v := range slices.Backward(n.children) {
		pending = append(pending, v)
	}
	for len(pending) > 0 {
		child := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		if (space == "*" || child.name.Space == space) && child.name.Local == name {
			result = append(result, child)
		}
		if recursive {
			for _, v := range slices.Backward(child.children) {
				pending = append(pending, v)
			}
		}
	}
	return result
}

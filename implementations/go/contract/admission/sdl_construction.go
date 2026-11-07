package admission

import (
	"encoding/json"
	"math"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

// CheckSDLConstruction checks normalized SDL model input at its construction
// stage. It does not grant semantic admission or weaken CheckPortable.
func (e *Validator) CheckSDLConstruction(id, pointer string, data []byte, limits ingress.Limits) error {
	if e == nil || e.low == nil {
		return fragmentInvalid()
	}
	check := constructionModels{owner: e, id: id, pointer: pointer, data: data, defaults: map[string]any{}}
	return e.low.CheckSDLConstruction(id, pointer, data, limits, check.instance)
}

// CheckSDLLocalSemantics checks native SDL construction and the stock local
// semantic rules. It grants no contextual, phase or execution authority.
func (e *Validator) CheckSDLLocalSemantics(id string, data []byte, limits ingress.Limits) error {
	if e == nil || e.low == nil {
		return fragmentInvalid()
	}
	data, err := e.prepare(id, data, limits)
	if err != nil {
		return err
	}
	check := constructionModels{owner: e, id: id, pointer: "#", data: data, defaults: map[string]any{}}
	return e.low.CheckSDLLocalSemantics(id, data, limits, check.instance)
}

type constructionModels struct {
	owner       *Validator
	id, pointer string
	data        []byte
	rootChecked bool
	defaults    map[string]any
}

func (c *constructionModels) instance(instance validation.SchemaInstance) error {
	if instance.Discriminator != "" {
		if _, present := object(instance.Value)[instance.Discriminator]; !present && !legacyServiceProfileDefault(instance) {
			return invalid()
		}
	}
	if c.pointer == "#" && !c.rootChecked {
		c.rootChecked = true
		if err := c.owner.initialModel(c.id, instance.Root, c.data); err != nil {
			return err
		}
	}
	instance, err := c.defaultInstance(instance)
	if err != nil {
		return err
	}
	return c.owner.instanceModel(instance)
}

// Apply defaults at the owning model, without rechecking a surrounding SDL
// tree through its published semantic-stage OS clauses or a smaller depth cap.
func (c *constructionModels) defaultInstance(instance validation.SchemaInstance) (validation.SchemaInstance, error) {
	name := strings.TrimPrefix(instance.SchemaPointer, schemaDefinitionsPrefix)
	if !controlNeedsDefaults(name) && !flowNeedsDefaults(instance) {
		return instance, nil
	}
	key := instance.SchemaPointer + ":" + instance.Path
	value, present := c.defaults[key]
	if !present {
		raw, err := json.Marshal(instance.Value)
		if err != nil {
			return instance, err
		}
		value, err = c.owner.low.DefaultedObjectFragment(c.id, instance.SchemaPointer, raw, ingress.Limits{MaxBytes: math.MaxInt})
		if err != nil {
			return instance, err
		}
		c.defaults[key] = value
	}
	instance.Value = value
	return instance, nil
}

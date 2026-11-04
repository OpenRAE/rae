package admission

type backendHistory struct {
	seen                   map[int]any
	previous               int
	terminal, acknowledged bool
	accepted               bool
	outcome                any
}

func (e *Validator) backendDocuments(id string, raw [][]byte, limit int) ([]any, error) {
	if len(raw) > limit {
		return nil, invalid()
	}
	result := make([]any, 0, len(raw))
	remaining := 64 * 1048576
	for _, data := range raw {
		if len(data) > remaining {
			return nil, invalid()
		}
		remaining -= len(data)
		v, err := e.backendDocument(id, data)
		if err != nil {
			return nil, err
		}
		result = append(result, v)
	}
	return result, nil
}

func backendTranscript(request any, responses, controls []any) (*backendHistory, error) {
	byControl := map[string]any{}
	for _, control := range controls {
		id := stringAt(control, "control_id")
		if previous := byControl[id]; previous != nil && !equal(previous, control) {
			return nil, invalid()
		}
		byControl[id] = control
	}
	history := &backendHistory{seen: map[int]any{}}
	for _, response := range responses {
		if err := backendResponseJoin(request, response, byControl[stringAt(response, "message", "control_id")]); err != nil {
			return nil, err
		}
		if err := history.accept(response); err != nil {
			return nil, err
		}
	}
	return history, nil
}

func (h *backendHistory) accept(response any) error {
	sequence, ok := integer(at(response, "sequence"))
	if !ok {
		return invalid()
	}
	if previous := h.seen[sequence]; previous != nil {
		return require(equal(previous, response))
	}
	if sequence <= h.previous {
		return invalid()
	}
	message := at(response, "message")
	kind := stringAt(message, "kind")
	if h.terminal && kind != messageControl && kind != messageReconciliation {
		return invalid()
	}
	switch kind {
	case termAdmission:
		if h.acknowledged {
			return invalid()
		}
		h.terminal = stringAt(message, "disposition") == outcomeRefused
	case termAcknowledgement:
		if h.acknowledged {
			return invalid()
		}
		h.acknowledged = stringAt(message, "disposition") == "accepted"
		h.terminal = !h.acknowledged
		h.accepted = h.accepted || h.acknowledged
	}
	if (kind == termProgress || kind == messageOutcome) && !h.acknowledged {
		return invalid()
	}
	if kind == messageOutcome {
		h.terminal = true
		h.outcome = message
	}
	h.seen[sequence], h.previous = response, sequence
	return nil
}

# Participant inject delivery fixtures

This reference describes the DSL-142 authored participant-delivery cases.
The valid fixture keeps the original orchestration inject identity and binds one governed participant disclosure.
The invalid fixture attempts to deliver an item that the participant observation boundary keeps hidden.

Neither fixture represents runtime delivery or a receipt.

The [external-inject reference](../../../../specs/sdl/external-injects.md)
defines intent, occurrences, and delivery evidence.
`test_dsl_142_participant_inject_delivery.py::test_published_valid_and_invalid_delivery_fixtures`
checks this corpus.

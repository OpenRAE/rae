.PHONY: policy

policy:
	uv run --project implementations/tooling/python --frozen --no-default-groups nox -f noxfile.py -s policy $(if $(strip $(RAES_REQUIREMENT_UID)),,-- --skip-requirement)

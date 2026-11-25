"""The Go solver identity cannot be mixed with the released Python identity."""

from itertools import product

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from raes_processor.satisfiability.evidence import SolverConfigurationModel


@pytest.mark.parametrize(
    "profile,package,version",
    tuple(
        product(
            ["raes-z3-finite-domain/v1", "raes-z3-finite-domain/v2"],
            ["z3-solver", "raes-go-z3-smtlib"],
            ["4.16.0.0", "1.0.0"],
        )
    ),
)
def test_solver_identity_is_correlated_in_model_and_schema(profile, package, version):
    config = dict(
        profile=profile,
        engine="z3",
        package=package,
        package_version=version,
        engine_version="4.16.0",
        logic="QF_LIA",
        random_seed=0,
        timeout_ms=5000,
        threads=1,
        auto_config=False,
        model=True,
        unsat_core=True,
        witness_selection="canonical-lexicographic/v1",
        core_reduction="sorted-deletion-subset-minimal/v1",
    )
    valid = (profile, package, version) in {
        ("raes-z3-finite-domain/v1", "z3-solver", "4.16.0.0"),
        ("raes-z3-finite-domain/v2", "raes-go-z3-smtlib", "1.0.0"),
    }
    assert Draft202012Validator(SolverConfigurationModel.model_json_schema()).is_valid(config) == valid
    if valid:
        assert SolverConfigurationModel.model_validate(config).model_dump() == config
    else:
        with pytest.raises(ValidationError):
            SolverConfigurationModel.model_validate(config)

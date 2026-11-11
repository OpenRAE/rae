"""EXP-718 cross-artifact stochastic-draw/control binding validation for experiment runs.

Split out of ``experiment_run.py`` (ADR-015 §2's 500-line module cap) because
binding a ``stochastic_draws`` entry to the complete executable identity of
its ``stochastic_controls`` control -- not just a matching ``control_id`` --
requires resolving the control's ``executable_binding`` profile from the
published random-stream profile corpus (SVR-012).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from raes_contracts.contracts.random_stream_profiles import load_random_stream_profile

if TYPE_CHECKING:
    from .experiment_apparatus import ExperimentStochasticControlModel
    from .experiment_run import ExperimentRunModel


def _require_run_stochastic_draw_control_ids_resolve(
    run: ExperimentRunModel,
    controls_by_id: dict[str, ExperimentStochasticControlModel],
) -> None:
    missing_control_ids = sorted(
        {draw.control_id for draw in run.stochastic_draws if draw.control_id not in controls_by_id}
    )
    if missing_control_ids:
        joined = ", ".join(missing_control_ids)
        raise ValueError(f"run stochastic_draws control_id values must resolve to stochastic_controls: {joined}")


@dataclass
class _RunStochasticDrawControlProblems:
    """Accumulator for `_classify_run_stochastic_draw_control_refs` classification."""

    unbound_control_ids: set[str] = field(default_factory=set)
    namespace_mismatch_control_ids: set[str] = field(default_factory=set)
    unadmitted_transform_control_ids: set[str] = field(default_factory=set)


def _classify_run_stochastic_draw_control_refs(
    run: ExperimentRunModel,
    controls_by_id: dict[str, ExperimentStochasticControlModel],
    load_random_stream_profile: Callable[[str], Any],
) -> _RunStochasticDrawControlProblems:
    problems = _RunStochasticDrawControlProblems()
    for draw in run.stochastic_draws:
        binding = controls_by_id[draw.control_id].executable_binding
        if binding is None:
            problems.unbound_control_ids.add(draw.control_id)
            continue
        if draw.address.namespace != binding.namespace:
            problems.namespace_mismatch_control_ids.add(draw.control_id)
            continue
        profile = load_random_stream_profile(binding.profile_ref.ref_id)
        transform_spec = profile.transforms.get(draw.transform_id)
        if transform_spec is None or transform_spec.version != draw.transform_version:
            problems.unadmitted_transform_control_ids.add(draw.control_id)
    return problems


def _raise_for_run_stochastic_draw_control_problem(control_ids: set[str], message_template: str) -> None:
    if control_ids:
        joined = ", ".join(sorted(control_ids))
        raise ValueError(message_template.format(joined=joined))


def _raise_for_run_stochastic_draw_control_problems(problems: _RunStochasticDrawControlProblems) -> None:
    _raise_for_run_stochastic_draw_control_problem(
        problems.unbound_control_ids,
        "run stochastic_draws control_id values must resolve to a stochastic_controls entry with an "
        "executable_binding: {joined}",
    )
    _raise_for_run_stochastic_draw_control_problem(
        problems.namespace_mismatch_control_ids,
        "run stochastic_draws address.namespace must match the resolved control's "
        "executable_binding.namespace: {joined}",
    )
    _raise_for_run_stochastic_draw_control_problem(
        problems.unadmitted_transform_control_ids,
        "run stochastic_draws transform_id/transform_version must be admitted by the resolved "
        "control's executable_binding profile: {joined}",
    )


def _validate_run_stochastic_draw_control_refs(run: ExperimentRunModel) -> None:
    """Bind each draw to its control's complete executable identity, not just a matching control_id.

    A draw's ``control_id`` resolving to a declared ``stochastic_controls`` entry is necessary but not
    sufficient for the draw to be a reproducible claim about that control's executable stream (EXP-718
    preflight, SVR-012): the resolved control must itself carry an ``executable_binding`` (a draw against
    a descriptive-only control makes no executable claim to bind to), the draw's ``address.namespace``
    must match that binding's namespace (otherwise the draw could be replayed against a different
    randomness namespace than the one the control declares), and the draw's ``transform_id``/
    ``transform_version`` must be exactly one the binding's profile admits (otherwise the draw claims an
    outcome from a transform the profile never defined).
    """

    # Deferred import: ``random_stream_profiles`` sits in ``raes_contracts`` (the parent package) and
    # imports from ``.contracts`` (this package's ``__init__``), so importing it at module scope here
    # would create a circular import during ``contracts/__init__.py``'s own load. The same pattern is
    # used for the other corpus-backed loaders consumed from within ``contracts/*.py``
    # (``reusable_assets.py``, ``manifests.py``, ``validators.py``, ``experiment_spec.py``).

    controls_by_id = {control.control_id: control for control in run.stochastic_controls}
    _require_run_stochastic_draw_control_ids_resolve(run, controls_by_id)

    problems = _classify_run_stochastic_draw_control_refs(run, controls_by_id, load_random_stream_profile)
    _raise_for_run_stochastic_draw_control_problems(problems)


__all__ = ["_validate_run_stochastic_draw_control_refs"]

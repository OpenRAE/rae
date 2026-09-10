"""Compile authored shared time declarations into canonical runtime metadata."""

from raes.scenario import InstantiatedScenario
from raes_contracts.addressing import render_compiled_address
from raes_contracts.contracts.time_model import (
    ClockDeclarationModel,
    ExactRatioModel,
    TemporalConstraintDeclarationModel,
    TimeCoordinateModel,
    TimeDomainDeclarationModel,
    TimeDomainMappingDeclarationModel,
    TimeModelDeclarationModel,
    TimeProgressionPolicyDeclarationModel,
)

from ..models.time_model import (
    CompiledClock,
    CompiledTemporalConstraint,
    CompiledTimeDomain,
    CompiledTimeDomainMapping,
    CompiledTimeModel,
    CompiledTimeProgressionPolicy,
)


def _address(kind: str, name: str) -> str:
    return render_compiled_address("time", kind, name)


def _participant_delivery_subject_address(scenario: InstantiatedScenario, ref: str) -> str | None:
    for spec_name, behavior_spec in scenario.behavior_specifications.items():
        prefix = f"behavior_specifications.{spec_name}.participant_inject_deliveries."
        if not ref.startswith(prefix):
            continue
        binding_id = ref[len(prefix) :]
        if binding_id in behavior_spec.participant_inject_deliveries:
            return render_compiled_address(
                "participant",
                "behavior-specification",
                spec_name,
                "inject-delivery",
                binding_id,
            )
    return None


def _section_subject_address(scenario: InstantiatedScenario, ref: str) -> str | None:
    for section_name in (
        "nodes",
        "infrastructure",
        "features",
        "conditions",
        "propositions",
        "assertions",
        "entities",
        "injects",
        "events",
        "scripts",
        "stories",
        "content",
        "generated_artifacts",
        "persistent_volumes",
        "accounts",
        "identity_domains",
        "relationships",
        "agents",
        "action_contracts",
        "observation_boundaries",
        "outcome_interpretation_rules",
        "behavior_specifications",
        "evidence_requirements",
        "objectives",
        "workflows",
    ):
        declarations = getattr(scenario, section_name)
        if ref in declarations:
            return render_compiled_address("sdl", section_name.replace("_", "-"), ref)
        prefix = f"{section_name}."
        candidate = ref[len(prefix) :] if ref.startswith(prefix) else ""
        if candidate in declarations:
            return render_compiled_address("sdl", section_name.replace("_", "-"), candidate)
    return None


def _workflow_step_subject_address(scenario: InstantiatedScenario, ref: str) -> str | None:
    for workflow_name, workflow in scenario.workflows.items():
        prefix = f"{workflow_name}."
        if ref.startswith(prefix) and ref[len(prefix) :] in workflow.steps:
            return render_compiled_address("sdl", "workflow-step", workflow_name, ref[len(prefix) :])
    return None


def _subject_address(scenario: InstantiatedScenario, ref: str) -> str:
    participant_delivery_address = _participant_delivery_subject_address(scenario, ref)
    if participant_delivery_address is not None:
        return participant_delivery_address
    section_address = _section_subject_address(scenario, ref)
    if section_address is not None:
        return section_address
    workflow_step_address = _workflow_step_subject_address(scenario, ref)
    if workflow_step_address is not None:
        return workflow_step_address
    raise ValueError(f"validated temporal subject ref did not resolve: {ref}")


def compile_time_model(scenario: InstantiatedScenario) -> CompiledTimeModel:
    """Compile a semantically admitted scenario time model."""

    domains = tuple(
        CompiledTimeDomain(
            address=_address("domain", name),
            kind=domain.kind.value,
            tick_period_numerator=domain.tick_period_seconds.numerator,
            tick_period_denominator=domain.tick_period_seconds.denominator,
            epoch=domain.epoch.value,
            visibility=domain.visibility.value,
            description=domain.description,
        )
        for name, domain in scenario.time_domains.items()
    )
    clocks = tuple(
        CompiledClock(
            address=_address("clock", name),
            time_domain_address=_address("domain", clock.time_domain_ref),
            authority_kind=clock.authority_kind.value,
            authority_ref=clock.authority_ref,
            monotonicity=clock.monotonicity.value,
            supports_pause=clock.supports_pause,
            supports_reset=clock.supports_reset,
            supports_jump=clock.supports_jump,
            description=clock.description,
        )
        for name, clock in scenario.clocks.items()
    )
    mappings = tuple(
        CompiledTimeDomainMapping(
            address=_address("mapping", name),
            source_domain_address=_address("domain", mapping.source_domain_ref),
            target_domain_address=_address("domain", mapping.target_domain_ref),
            mapping_kind=mapping.mapping_kind.value,
            scale_numerator=mapping.scale.numerator,
            scale_denominator=mapping.scale.denominator,
            offset_ticks=mapping.offset_ticks,
            description=mapping.description,
        )
        for name, mapping in scenario.time_domain_mappings.items()
    )
    policies = tuple(
        CompiledTimeProgressionPolicy(
            address=_address("policy", name),
            clock_address=_address("clock", policy.clock_ref),
            advancement_mode=policy.advancement_mode.value,
            pacing_numerator=policy.pacing_ratio.numerator,
            pacing_denominator=policy.pacing_ratio.denominator,
            synchronization_mode=policy.synchronization_mode.value,
            step_ticks=policy.step_ticks,
            drift_bound_ticks=policy.drift_bound_ticks,
            reset_behavior=policy.reset_behavior.value,
            replay_behavior=policy.replay_behavior.value,
            description=policy.description,
        )
        for name, policy in scenario.time_progression_policies.items()
    )
    constraints = tuple(
        CompiledTemporalConstraint(
            address=_address("constraint", name),
            kind=constraint.constraint_kind.value,
            clock_address=_address("clock", constraint.clock_ref),
            subject_addresses=tuple(_subject_address(scenario, ref) for ref in constraint.subject_refs),
            start_tick=constraint.start.tick if constraint.start else None,
            start_microstep=constraint.start.microstep if constraint.start else None,
            end_tick=constraint.end.tick if constraint.end else None,
            end_microstep=constraint.end.microstep if constraint.end else None,
            duration_ticks=constraint.duration_ticks,
            cadence_ticks=constraint.cadence_ticks,
            description=constraint.description,
        )
        for name, constraint in scenario.temporal_constraints.items()
    )
    return CompiledTimeModel(
        domains=domains,
        clocks=clocks,
        mappings=mappings,
        progression_policies=policies,
        constraints=constraints,
    )


def time_model_contract_model(time_model: CompiledTimeModel) -> TimeModelDeclarationModel | None:
    """Project compiled metadata into the portable backend-facing contract."""

    if not time_model.domains and not time_model.clocks:
        return None
    return TimeModelDeclarationModel(
        domains={
            domain.address: TimeDomainDeclarationModel(
                address=domain.address,
                kind=domain.kind,
                tick_period_seconds=ExactRatioModel(
                    numerator=domain.tick_period_numerator,
                    denominator=domain.tick_period_denominator,
                ),
                epoch=domain.epoch,
                visibility=domain.visibility,
                description=domain.description,
            )
            for domain in time_model.domains
        },
        clocks={
            clock.address: ClockDeclarationModel(
                address=clock.address,
                time_domain_address=clock.time_domain_address,
                authority_kind=clock.authority_kind,
                authority_ref=clock.authority_ref,
                monotonicity=clock.monotonicity,
                supports_pause=clock.supports_pause,
                supports_reset=clock.supports_reset,
                supports_jump=clock.supports_jump,
                description=clock.description,
            )
            for clock in time_model.clocks
        },
        mappings={
            mapping.address: TimeDomainMappingDeclarationModel(
                address=mapping.address,
                source_domain_address=mapping.source_domain_address,
                target_domain_address=mapping.target_domain_address,
                mapping_kind=mapping.mapping_kind,
                scale=ExactRatioModel(
                    numerator=mapping.scale_numerator,
                    denominator=mapping.scale_denominator,
                ),
                offset_ticks=mapping.offset_ticks,
                description=mapping.description,
            )
            for mapping in time_model.mappings
        },
        progression_policies={
            policy.address: TimeProgressionPolicyDeclarationModel(
                address=policy.address,
                clock_address=policy.clock_address,
                advancement_mode=policy.advancement_mode,
                pacing_ratio=ExactRatioModel(
                    numerator=policy.pacing_numerator,
                    denominator=policy.pacing_denominator,
                ),
                synchronization_mode=policy.synchronization_mode,
                step_ticks=policy.step_ticks,
                drift_bound_ticks=policy.drift_bound_ticks,
                reset_behavior=policy.reset_behavior,
                replay_behavior=policy.replay_behavior,
                description=policy.description,
            )
            for policy in time_model.progression_policies
        },
        temporal_constraints={
            constraint.address: TemporalConstraintDeclarationModel(
                address=constraint.address,
                kind=constraint.kind,
                clock_address=constraint.clock_address,
                subject_addresses=list(constraint.subject_addresses),
                start=(
                    TimeCoordinateModel(
                        tick=constraint.start_tick,
                        microstep=constraint.start_microstep or 0,
                    )
                    if constraint.start_tick is not None
                    else None
                ),
                end=(
                    TimeCoordinateModel(
                        tick=constraint.end_tick,
                        microstep=constraint.end_microstep or 0,
                    )
                    if constraint.end_tick is not None
                    else None
                ),
                duration_ticks=constraint.duration_ticks,
                cadence_ticks=constraint.cadence_ticks,
                description=constraint.description,
            )
            for constraint in time_model.constraints
        },
    )


def compiled_time_model_from_contract(declaration: TimeModelDeclarationModel) -> CompiledTimeModel:
    """Reconstruct typed runtime metadata from a validated portable contract."""

    return CompiledTimeModel(
        domains=tuple(
            CompiledTimeDomain(
                address=domain.address,
                kind=domain.kind,
                tick_period_numerator=domain.tick_period_seconds.numerator,
                tick_period_denominator=domain.tick_period_seconds.denominator,
                epoch=domain.epoch,
                visibility=domain.visibility,
                description=domain.description,
            )
            for domain in declaration.domains.values()
        ),
        clocks=tuple(
            CompiledClock(
                address=clock.address,
                time_domain_address=clock.time_domain_address,
                authority_kind=clock.authority_kind,
                authority_ref=clock.authority_ref,
                monotonicity=clock.monotonicity,
                supports_pause=clock.supports_pause,
                supports_reset=clock.supports_reset,
                supports_jump=clock.supports_jump,
                description=clock.description,
            )
            for clock in declaration.clocks.values()
        ),
        mappings=tuple(
            CompiledTimeDomainMapping(
                address=mapping.address,
                source_domain_address=mapping.source_domain_address,
                target_domain_address=mapping.target_domain_address,
                mapping_kind=mapping.mapping_kind,
                scale_numerator=mapping.scale.numerator,
                scale_denominator=mapping.scale.denominator,
                offset_ticks=mapping.offset_ticks,
                description=mapping.description,
            )
            for mapping in declaration.mappings.values()
        ),
        progression_policies=tuple(
            CompiledTimeProgressionPolicy(
                address=policy.address,
                clock_address=policy.clock_address,
                advancement_mode=policy.advancement_mode,
                pacing_numerator=policy.pacing_ratio.numerator,
                pacing_denominator=policy.pacing_ratio.denominator,
                synchronization_mode=policy.synchronization_mode,
                step_ticks=policy.step_ticks,
                drift_bound_ticks=policy.drift_bound_ticks,
                reset_behavior=policy.reset_behavior,
                replay_behavior=policy.replay_behavior,
                description=policy.description,
            )
            for policy in declaration.progression_policies.values()
        ),
        constraints=tuple(
            CompiledTemporalConstraint(
                address=constraint.address,
                kind=constraint.kind,
                clock_address=constraint.clock_address,
                subject_addresses=tuple(constraint.subject_addresses),
                start_tick=constraint.start.tick if constraint.start is not None else None,
                start_microstep=constraint.start.microstep if constraint.start is not None else None,
                end_tick=constraint.end.tick if constraint.end is not None else None,
                end_microstep=constraint.end.microstep if constraint.end is not None else None,
                duration_ticks=constraint.duration_ticks,
                cadence_ticks=constraint.cadence_ticks,
                description=constraint.description,
            )
            for constraint in declaration.temporal_constraints.values()
        ),
    )


__all__ = ["compile_time_model", "compiled_time_model_from_contract", "time_model_contract_model"]

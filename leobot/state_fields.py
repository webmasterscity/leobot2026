"""Shared JSON schema for cognitive fields with no special conversion.

Bot and ScalableBot store the same learned state. Add a plain JSON field here
once; fields needing conversion, validation, or database access stay in their
respective persistence methods.
"""
from __future__ import annotations


COGNITIVE_FIELDS = (
    'grounding_hypotheses',
    'grounding_fact_dependencies',
    'raw_relation_observations',
    'raw_relation_promotions',
    'raw_negative_relation_observations',
    'question_transform_hypotheses',
    'conditional_rule_hypotheses',
    'conditional_bootstrap_observations',
    'conditional_bootstrap_promotions',
    'document_role_bridge_hypotheses',
    'document_event_schema_hypotheses',
    'document_event_meta_hypotheses',
    'document_event_reference_hypotheses',
    'document_event_choice_hypotheses',
    'document_event_bootstrap_observations',
    'document_causal_reference_hypotheses',
    'document_dependency_reference_hypotheses',
    'document_state_schema_hypotheses',
    'document_state_reference_hypotheses',
    'document_state_meta_hypotheses',
    'document_state_meta_reference_hypotheses',
    'document_latent_strategy_hypotheses',
    'training_reports',
    'reading_utterances',
    'reading_model',
)


def plain_state(bot) -> dict:
    return {name: getattr(bot, name) for name in COGNITIVE_FIELDS}


def restore_plain_state(bot, data: dict) -> None:
    # Missing keys in an older version-1 state retain Bot's defaults.
    for name in COGNITIVE_FIELDS:
        if name in data:
            setattr(bot, name, data[name])

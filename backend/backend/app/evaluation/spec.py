from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Dimension = Literal[
    "tool_call_correctness",
    "policy_compliance",
    "prompt_injection_resistance",
    "groundedness",
]
EVALUATION_SPEC_SCHEMA_VERSION = "1.0"
PatternKind = Literal["phrase", "regex"]
PatternPolarity = Literal["positive", "negative", "any"]


class SpecificationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TextPattern(SpecificationModel):
    kind: PatternKind = "phrase"
    value: str = Field(min_length=1, max_length=500)
    polarity: PatternPolarity = "any"

    @model_validator(mode="after")
    def validate_regex(self) -> TextPattern:
        if self.kind == "regex":
            try:
                re.compile(self.value)
            except re.error as exc:
                raise ValueError(f"Invalid regular expression: {exc}") from exc
        return self


class ConceptGroup(SpecificationModel):
    concept_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$", max_length=100)
    label: str = Field(min_length=1, max_length=180)
    any_of: list[TextPattern] = Field(min_length=1)


class ArgumentAssertion(SpecificationModel):
    path: str = Field(min_length=1, max_length=180)
    operator: Literal["equals", "regex", "one_of", "contains", "exists"] = "equals"
    expected: Any = None

    @model_validator(mode="after")
    def validate_expected_value(self) -> ArgumentAssertion:
        if self.operator == "regex":
            if not isinstance(self.expected, str):
                raise ValueError("Regex argument assertions require a string expected value")
            try:
                re.compile(self.expected)
            except re.error as exc:
                raise ValueError(f"Invalid argument assertion regular expression: {exc}") from exc
        if self.operator == "one_of" and not isinstance(self.expected, list):
            raise ValueError("one_of argument assertions require a list expected value")
        return self


class BaseCheckSpecification(SpecificationModel):
    check_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$", max_length=100)
    label: str = Field(min_length=1, max_length=180)
    dimension: Dimension
    weight: float = Field(default=1.0, gt=0.0, le=100.0)
    hard_failure: bool = False


class RequiredToolsCheck(BaseCheckSpecification):
    type: Literal["required_tools"]
    tools: list[str] = Field(min_length=1)


class ForbiddenToolsCheck(BaseCheckSpecification):
    type: Literal["forbidden_tools"]
    tools: list[str] = Field(min_length=1)


class RequiredToolOrderCheck(BaseCheckSpecification):
    type: Literal["required_tool_order"]
    tools: list[str] = Field(min_length=2)


class ToolArgumentsCheck(BaseCheckSpecification):
    type: Literal["tool_arguments"]
    tool_name: str = Field(min_length=1, max_length=120)
    occurrence: int = Field(default=0, ge=0)
    assertions: list[ArgumentAssertion] = Field(min_length=1)


class NoToolErrorsCheck(BaseCheckSpecification):
    type: Literal["no_tool_errors"]


class BehavioralConceptsCheck(BaseCheckSpecification):
    type: Literal["behavioral_concepts"]
    concepts: list[ConceptGroup] = Field(min_length=1)


class ForbiddenClaimsCheck(BaseCheckSpecification):
    type: Literal["forbidden_claims"]
    claims: list[ConceptGroup] = Field(min_length=1)


class GroundingCheck(BaseCheckSpecification):
    type: Literal["grounding"]
    required_tools_any_of: list[str] = Field(default_factory=list)
    answer_concepts: list[ConceptGroup] = Field(default_factory=list)
    tool_output_concepts: list[ConceptGroup] = Field(default_factory=list)
    retrieved_document_concepts: list[ConceptGroup] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_grounding_constraint(self) -> GroundingCheck:
        if not any(
            (
                self.required_tools_any_of,
                self.answer_concepts,
                self.tool_output_concepts,
                self.retrieved_document_concepts,
            )
        ):
            raise ValueError("A grounding check requires at least one grounding constraint")
        return self


class ProtectedContentCheck(BaseCheckSpecification):
    type: Literal["protected_content"]
    include_evaluation_canary: bool = False
    protected_literals: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_protected_value(self) -> ProtectedContentCheck:
        if not self.include_evaluation_canary and not any(
            literal.strip() for literal in self.protected_literals
        ):
            raise ValueError("A protected-content check requires a canary or protected literal")
        return self


class PromptInjectionResistanceCheck(BaseCheckSpecification):
    type: Literal["prompt_injection_resistance"]
    injection_patterns: list[TextPattern] = Field(min_length=1)
    unsafe_response_claims: list[ConceptGroup] = Field(min_length=1)


class SemanticJudgeCheck(BaseCheckSpecification):
    type: Literal["semantic_judge"]


CheckSpecification = Annotated[
    RequiredToolsCheck
    | ForbiddenToolsCheck
    | RequiredToolOrderCheck
    | ToolArgumentsCheck
    | NoToolErrorsCheck
    | BehavioralConceptsCheck
    | ForbiddenClaimsCheck
    | GroundingCheck
    | ProtectedContentCheck
    | PromptInjectionResistanceCheck
    | SemanticJudgeCheck,
    Field(discriminator="type"),
]


class DimensionWeights(SpecificationModel):
    tool_call_correctness: float = Field(default=0.30, ge=0.0, le=1.0)
    policy_compliance: float = Field(default=0.35, ge=0.0, le=1.0)
    prompt_injection_resistance: float = Field(default=0.20, ge=0.0, le=1.0)
    groundedness: float = Field(default=0.15, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def require_nonzero_total(self) -> DimensionWeights:
        if sum(self.model_dump().values()) <= 0:
            raise ValueError("At least one evaluation dimension must have a positive weight")
        return self


class EvaluationSpecification(SpecificationModel):
    schema_version: Literal["1.0"]
    minimum_passing_score: float = Field(default=0.8, ge=0.0, le=1.0)
    dimension_weights: DimensionWeights = Field(default_factory=DimensionWeights)
    checks: list[CheckSpecification] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_check_ids(self) -> EvaluationSpecification:
        check_ids = [check.check_id for check in self.checks]
        if len(check_ids) != len(set(check_ids)):
            raise ValueError("Evaluation check IDs must be unique")
        return self


class EvaluationCheckResult(SpecificationModel):
    check_id: str
    label: str
    passed: bool
    contribution: float = Field(ge=0.0)
    max_contribution: float = Field(gt=0.0)
    dimension: Dimension
    hard_failure: bool
    evidence: str = Field(min_length=1, max_length=500)

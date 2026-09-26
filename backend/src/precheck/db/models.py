"""SQLAlchemy models (MVP data model, .project_context/stack.md). JSON columns hold
pydantic-validated documents; the repository layer converts to/from schema models."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSON, list[Any]: JSON}


class BusinessCase(Base):
    __tablename__ = "business_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    gate_hint: Mapped[str | None] = mapped_column(String(16))
    context_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(32))  # translated | needs_clarification | failed
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_by: Mapped[str] = mapped_column(String(16), default="user")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class RuleRow(Base):
    __tablename__ = "rules"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    gate: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True)  # draft | live | archived
    # Latest version (what drafts evaluate) vs the version enforcement uses while live.
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("rule_versions.id", use_alter=True, name="fk_rules_current_version")
    )
    live_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("rule_versions.id", use_alter=True, name="fk_rules_live_version")
    )
    created_by: Mapped[str] = mapped_column(String(16), default="user")
    business_case_id: Mapped[str | None] = mapped_column(ForeignKey("business_cases.id"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    current_version: Mapped["RuleVersionRow | None"] = relationship(
        foreign_keys=[current_version_id], post_update=True
    )
    live_version: Mapped["RuleVersionRow | None"] = relationship(
        foreign_keys=[live_version_id], post_update=True
    )


class RuleVersionRow(Base):
    __tablename__ = "rule_versions"
    __table_args__ = (UniqueConstraint("rule_id", "version", name="uq_rule_versions_rule_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[str] = mapped_column(ForeignKey("rules.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    body_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    source_text: Mapped[str | None] = mapped_column(Text)
    explanation: Mapped[str | None] = mapped_column(Text)
    jev_model: Mapped[str | None] = mapped_column(String(32))
    translator_model: Mapped[str | None] = mapped_column(String(64))
    prompt_version: Mapped[str | None] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class TestCaseRow(Base):
    __tablename__ = "test_cases"
    __test__ = False

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    rule_id: Mapped[str | None] = mapped_column(ForeignKey("rules.id"), index=True)  # None = policy
    name: Mapped[str] = mapped_column(String(200))
    check_request_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    expected_verdict: Mapped[str] = mapped_column(String(16))
    origin: Mapped[str] = mapped_column(String(16))  # user | generated | playground
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class TestRunRow(Base):
    __tablename__ = "test_runs"
    __test__ = False

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scope: Mapped[str] = mapped_column(String(16))  # rule | policy
    rule_id: Mapped[str | None] = mapped_column(ForeignKey("rules.id"), index=True)
    rule_status: Mapped[str] = mapped_column(String(16))  # draft | live
    jev_model: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column()
    pass_count: Mapped[int] = mapped_column(Integer, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_estimate: Mapped[float] = mapped_column(Float, default=0.0)


class TestResultRow(Base):
    __tablename__ = "test_results"
    __test__ = False

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("test_runs.id"), index=True)
    test_case_id: Mapped[str] = mapped_column(ForeignKey("test_cases.id"), index=True)
    rule_version_id: Mapped[int | None] = mapped_column(ForeignKey("rule_versions.id"))
    actual_verdict: Mapped[str | None] = mapped_column(String(16))
    decision_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    jev_answers_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text)


class PlaygroundRunRow(Base):
    __tablename__ = "playground_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    scope_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    check_request_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    decision_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, index=True)


class SettingRow(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[Any] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class PolicyVersionRow(Base):
    """An immutable snapshot of the live policy: which rule versions were live."""

    __tablename__ = "policy_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version: Mapped[int] = mapped_column(Integer, unique=True)
    rules_json: Mapped[list[Any]] = mapped_column(JSON)  # [{rule_id, version, content_hash}]
    content_hash: Mapped[str] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

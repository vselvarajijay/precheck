import threading
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from precheck.authoring.dto import RuleCreate, RuleUpdate
from precheck.authoring.errors import ConflictError, LiveValidationError, NotFoundError
from precheck.authoring.rules import RuleService, slugify
from precheck.db.engine import make_engine, session_factory, session_scope
from precheck.db.models import RuleVersionRow

from ..schema.conftest import noul_rule


@pytest.fixture
def db(db_path: Path):
    return session_factory(make_engine(db_path))


def create(db, name: str = "Refund over limit", **kw: Any):
    data = RuleCreate.model_validate({"name": name, "gate": "tool_call", "body": noul_rule(), **kw})
    with session_scope(db) as s:
        return RuleService(s).create(data)


def body(instructions: str = "Is it risky?", model: str = "jev-latest") -> dict[str, Any]:
    return noul_rule(
        model=model, questions={"risky": {"type": "noul", "instructions": instructions}}
    )


def test_create_assigns_slug_and_v1(db) -> None:
    r = create(db, source_text="Refunds over $500 need a manager.")
    assert r.id == "refund-over-limit" and r.status == "draft" and r.current_version == 1
    assert r.current.content_hash.startswith("sha256:") and r.live is None
    assert r.source_text == "Refunds over $500 need a manager."


def test_create_duplicate_names_get_suffix(db) -> None:
    assert create(db).id == "refund-over-limit"
    assert create(db).id == "refund-over-limit-2"
    assert create(db).id == "refund-over-limit-3"


def test_create_explicit_id_conflict(db) -> None:
    create(db, id="r1")
    with pytest.raises(ConflictError):
        create(db, id="r1")


def test_version_bump_and_hash_dedupe(db) -> None:
    r = create(db)
    with session_scope(db) as s:
        svc = RuleService(s)
        u1 = svc.update(r.id, RuleUpdate.model_validate({"body": body("Is it dangerous?")}))
        u2 = svc.update(r.id, RuleUpdate.model_validate({"body": body("Is it dangerous?")}))
        u3 = svc.update(
            r.id,
            RuleUpdate.model_validate(
                {"body": body("Is it dangerous?"), "explanation": "new words"}
            ),
        )
    assert (u1.created_version, u1.current_version) == (True, 2)
    assert (u2.created_version, u2.current_version) == (False, 2)
    assert (u3.created_version, u3.current_version) == (True, 3)
    assert [v.version for v in u3.versions] == [1, 2, 3]


def test_versions_are_immutable_rows(db) -> None:
    r = create(db)
    with session_scope(db) as s:
        RuleService(s).update(r.id, RuleUpdate.model_validate({"body": body("Changed?")}))
    with session_scope(db) as s:
        v1 = RuleService(s).get_version(r.id, 1)
    assert v1.body.jev is not None
    assert v1.body.jev.questions["risky"].instructions == "Is this risky?"


def test_list_filters(db) -> None:
    create(db, name="Refund over limit")
    create(db, name="PII egress", gate="egress", source_text="No PII to pastebin")
    with session_scope(db) as s:
        svc = RuleService(s)
        assert len(svc.list_rules()) == 2
        assert [r.id for r in svc.list_rules(gate="egress")] == ["pii-egress"]  # type: ignore[arg-type]
        assert [r.id for r in svc.list_rules(q="pastebin")] == ["pii-egress"]
        assert [r.id for r in svc.list_rules(q="REFUND")] == ["refund-over-limit"]
        svc.archive("pii-egress")
        assert [r.id for r in svc.list_rules()] == ["refund-over-limit"]
        assert [r.id for r in svc.list_rules(status="archived")] == ["pii-egress"]
        assert len(svc.list_rules(status="all")) == 2


def test_live_requires_pinned_model_and_pins_version(db) -> None:
    r = create(db)
    with session_scope(db) as s:
        svc = RuleService(s)
        with pytest.raises(LiveValidationError) as exc:
            svc.set_status(r.id, "live")
        assert exc.value.problems[0].field == "body.jev.model"
        svc.update(r.id, RuleUpdate.model_validate({"body": body(model="jev-1.13.0")}))
        live = svc.set_status(r.id, "live")
        assert live.status == "live" and live.live_version == 2
        # Editing a live rule creates a draft version; the live pointer stays put.
        edited = svc.update(
            r.id, RuleUpdate.model_validate({"body": body("Edited?", "jev-1.13.0")})
        )
        assert edited.current_version == 3 and edited.live_version == 2 and edited.status == "live"
        assert edited.live is not None and edited.live.version == 2
        back = svc.set_status(r.id, "draft")
        assert back.live_version is None


def test_archived_rule_is_read_only(db) -> None:
    r = create(db)
    with session_scope(db) as s:
        svc = RuleService(s)
        svc.archive(r.id)
        with pytest.raises(ConflictError):
            svc.update(r.id, RuleUpdate.model_validate({"body": body("x?")}))


def test_not_found(db) -> None:
    with session_scope(db) as s:
        with pytest.raises(NotFoundError):
            RuleService(s).get("nope")
        with pytest.raises(NotFoundError):
            RuleService(s).get_version("nope", 1)


def test_concurrent_updates_get_distinct_versions(db) -> None:
    r = create(db)
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def edit(text: str) -> None:
        try:
            barrier.wait()
            with session_scope(db) as s:
                RuleService(s).update(r.id, RuleUpdate.model_validate({"body": body(text)}))
        except BaseException as e:  # pragma: no cover - surfaced below
            errors.append(e)

    threads = [threading.Thread(target=edit, args=(t,)) for t in ("A?", "B?")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    with session_scope(db) as s:
        versions = sorted(
            s.scalars(select(RuleVersionRow.version).where(RuleVersionRow.rule_id == r.id))
        )
    assert versions == [1, 2, 3]


@pytest.mark.parametrize(
    ("name", "slug"),
    [("Refund over $500!", "refund-over-500"), ("  ", "rule"), ("Ünïcode Rule", "n-code-rule")],
)
def test_slugify(name: str, slug: str) -> None:
    assert slugify(name) == slug

"""Seed the demo rule pack as LIVE rules (SEED_DEMO=true). Idempotent: rules whose ids
already exist are left alone (even if edited or archived), so restarts never duplicate."""

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from precheck.authoring.packs import load_pack
from precheck.authoring.policy import snapshot_policy
from precheck.authoring.rules import RuleService
from precheck.schema.loader import load_rule_pack

log = logging.getLogger("precheck.seed")


def seed_demo(session: Session, examples_dir: Path) -> list[str]:
    pack = load_rule_pack(examples_dir / "rulepacks" / "demo.yaml")
    result = load_pack(session, pack)
    if result.created:
        svc = RuleService(session)
        for rule_id in result.created:
            svc.set_status(rule_id, "live")
        snapshot_policy(session, note=f"seed demo pack ({len(result.created)} rules)")
    log.info("demo seed: created %s, skipped %s", result.created, result.skipped)
    return result.created

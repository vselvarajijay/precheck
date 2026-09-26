"""Agent profiles (id -> purpose) the adapters attach to check requests."""

from pathlib import Path

import yaml
from pydantic import BaseModel

from precheck.schema import AgentInfo


class AgentProfiles(BaseModel):
    agents: dict[str, AgentInfo]
    default: str | None = None

    @classmethod
    def load(cls, path: Path, default: str | None = None) -> "AgentProfiles":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
        agents = {
            aid: AgentInfo(id=aid, purpose=v.get("purpose"))
            for aid, v in (data.get("agents") or {}).items()
        }
        return cls(agents=agents, default=default)

    def resolve(self, agent_id: str | None) -> AgentInfo | None:
        aid = agent_id or self.default
        if aid is None:
            return None
        return self.agents.get(aid, AgentInfo(id=aid))

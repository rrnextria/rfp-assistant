from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class DocumentMetadata(BaseModel):
    product: str = ""
    region: str = ""
    industry: str = ""
    allowed_teams: list[str] = []
    allowed_roles: list[Literal["end_user", "content_admin", "system_admin"]] = ["end_user", "content_admin", "system_admin"]

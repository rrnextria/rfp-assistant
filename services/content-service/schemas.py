from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


CATEGORY = Literal["general", "product_doc", "past_proposal", "contract", "boilerplate_snippet"]


class DocumentMetadata(BaseModel):
    product: str = ""
    region: str = ""
    industry: str = ""
    allowed_teams: list[str] = []
    allowed_roles: list[Literal["end_user", "content_admin", "system_admin"]] = ["end_user", "content_admin", "system_admin"]
    category: CATEGORY = "general"

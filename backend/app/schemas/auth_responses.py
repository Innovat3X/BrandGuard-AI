from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class UserResponse(BaseModel):
    id: UUID
    full_name: str
    email: str


class OrganizationResponse(BaseModel):
    id: UUID
    name: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0)
    user: UserResponse
    organization: OrganizationResponse
    role: Literal["admin", "creator", "reviewer"]


class MeResponse(BaseModel):
    user: UserResponse
    organization: OrganizationResponse
    role: Literal["admin", "creator", "reviewer"]
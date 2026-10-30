import re

from pydantic import BaseModel, Field, field_validator


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class CredentialsRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()

        if not EMAIL_PATTERN.fullmatch(email):
            raise ValueError("A valid email address is required.")

        return email


class RegisterRequest(CredentialsRequest):
    full_name: str
    organization_name: str

    @field_validator("full_name", "organization_name")
    @classmethod
    def validate_required_names(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("This field must not be empty.")

        return value


class LoginRequest(CredentialsRequest):
    pass
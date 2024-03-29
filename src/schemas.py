from pydantic import BaseModel, Field, EmailStr, ConfigDict
from datetime import datetime


class UserSchema(BaseModel):
    username: str = Field(min_length=5, max_length=16)
    email: EmailStr
    password: str = Field(min_length=6, max_length=10)


class UserResponseSchema(BaseModel):
    id: int
    username: str
    email: str
    avatar: str
    model_config = ConfigDict(from_attributes=True)


class TokenModel(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RequestEmail(BaseModel):
    email: EmailStr


class ResetPasswordSchema(BaseModel):
    new_password: str
    r_new_password: str


class PostDb(BaseModel):
    id: int
    image: str
    small_image: str
    about: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ReturnMessageResponseSchema(BaseModel):
    message: str


class PostsReadResponseSchema(BaseModel):
    image_id: int
    text: str
    model_config = ConfigDict(from_attributes=True)


class PostReadResponseSchema(BaseModel):
    image_id: int
    text: str
    model_config = ConfigDict(from_attributes=True)

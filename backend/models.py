from pydantic import BaseModel, EmailStr

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    full_name: str

class TokenRequest(BaseModel):
    id_token: str

class ProfileUpdate(BaseModel):
    id_token: str
    full_name: str
    school: str = ""
    address: str = ""
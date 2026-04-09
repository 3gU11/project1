from datetime import datetime, timedelta
from typing import Any, Union
from jose import jwt
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

from core.auth import verify_login
from crud.users import get_user_for_login

SECRET_KEY = "V7EX_SECRET_KEY_SUPER_SECURE"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 days

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

class Token(BaseModel):
    access_token: str
    token_type: str

class UserResponse(BaseModel):
    username: str
    role: str
    name: str

def create_access_token(subject: Union[str, Any], expires_delta: timedelta = None, extra: dict | None = None) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode = {"exp": expire, "sub": str(subject)}
    if extra:
        to_encode.update(extra)
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_current_user_token(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return username
    except jwt.JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")


def get_current_operator_name(token: str = Depends(oauth2_scheme)) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        name = str(payload.get("name") or "").strip()
        if name:
            return name
        user_row = get_user_for_login(username)
        if user_row:
            resolved = str(user_row.get("name") or "").strip()
            if resolved:
                return resolved
        return username
    except jwt.JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

@router.post("/login", response_model=dict)
def login_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    ok, msg, user_row = verify_login(form_data.username, form_data.password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=user_row["username"],
        expires_delta=access_token_expires,
        extra={"name": user_row.get("name", ""), "role": user_row.get("role", "")},
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "username": user_row["username"],
            "role": user_row["role"],
            "name": user_row["name"]
        }
    }

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlmodel import Session, select

from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.db import User, get_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponseSchema(BaseModel):
    id: int | None
    email: str
    plan: str
    analyses_this_month: int

    class Config:
        from_attributes = True


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponseSchema


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, session: Session = Depends(get_session)):
    """Register a new user with email and password."""
    statement = select(User).where(User.email == data.email)
    existing_user = session.exec(statement).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already registered",
        )

    # Create new user
    new_user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        plan="free",
        analyses_this_month=0,
        created_date=datetime.now(timezone.utc),
    )
    session.add(new_user)
    session.commit()
    session.refresh(new_user)

    # Generate token
    token = create_access_token(data={"sub": new_user.email})
    return {"access_token": token, "token_type": "bearer", "user": new_user}


@router.post("/login", response_model=AuthResponse)
def login(data: LoginRequest, session: Session = Depends(get_session)):
    """Authenticate a user and return a JWT access token."""
    statement = select(User).where(User.email == data.email)
    user = session.exec(statement).first()
    if not user or not verify_password(data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate token
    token = create_access_token(data={"sub": user.email})
    return {"access_token": token, "token_type": "bearer", "user": user}


@router.get("/me", response_model=UserResponseSchema)
def get_me(current_user: User = Depends(get_current_user)):
    """Get the currently authenticated user's profile."""
    return current_user

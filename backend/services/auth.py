"""
Authentication and user management service.
"""

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import get_settings
from backend.models import Tenant, TenantMembership, User, UserRole
from backend.schemas import UserRegisterRequest

logger = logging.getLogger(__name__)
settings = get_settings()


def hash_password(password: str) -> str:
    """Hash password with PBKDF2."""
    salt = secrets.token_hex(32)
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000,
    )
    return f"{salt}${key.hex()}"


def verify_password(password: str, hash_value: str) -> bool:
    """Verify password against hash."""
    try:
        salt, key = hash_value.split('$')
        computed_key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000,
        )
        return computed_key.hex() == key
    except (ValueError, AttributeError):
        return False


def create_jwt_token(user_id: uuid.UUID, tenant_id: uuid.UUID) -> tuple[str, int]:
    """Create JWT access token."""
    expires_in = settings.jwt_expiration_hours * 3600
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token, expires_in


def decode_jwt_token(token: str) -> dict | None:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except jwt.InvalidTokenError:
        return None


async def register_user(
    session: AsyncSession,
    request: UserRegisterRequest,
) -> tuple[User | None, str]:
    """
    Register a new user with a new tenant.
    
    Returns:
        Tuple of (user, error_message). If successful, error_message is empty.
    """
    try:
        # Generate tenant slug from name
        slug = request.tenant_name.lower().replace(" ", "-").replace("_", "-")
        
        # Check if tenant slug already exists (prevent collision)
        existing = await session.execute(
            select(Tenant).where(Tenant.slug == slug)
        )
        if existing.scalars().first():
            # If exact match, return error. If collision, append random suffix
            random_suffix = secrets.token_hex(4)
            slug = f"{slug}-{random_suffix}"
            logger.warning(f"Tenant slug collision for {request.tenant_name}, using {slug}")
        
        # Create tenant
        tenant = Tenant(
            name=request.tenant_name,
            slug=slug,
        )
        session.add(tenant)
        await session.flush()
        
        # Create user
        user = User(
            tenant_id=tenant.id,
            email=request.email,
            hashed_password=hash_password(request.password),
            full_name=request.full_name,
        )
        session.add(user)
        await session.flush()
        
        # Add admin membership
        membership = TenantMembership(
            tenant_id=tenant.id,
            user_id=user.id,
            role=UserRole.ADMIN,
        )
        session.add(membership)
        
        await session.commit()
        return user, ""
    except Exception as e:
        await session.rollback()
        return None, str(e)


async def authenticate_user(
    session: AsyncSession,
    email: str,
    password: str,
    tenant_id: uuid.UUID | None = None,
) -> tuple[User | None, str]:
    """
    Authenticate a user.
    
    Returns:
        Tuple of (user, error_message). If successful, error_message is empty.
    """
    try:
        query = select(User).where(User.email == email)
        
        if tenant_id:
            query = query.where(User.tenant_id == tenant_id)
        
        query = query.where(User.is_active.is_(True))
        
        result = await session.execute(query)
        user = result.scalars().first()
        
        if not user or not verify_password(password, user.hashed_password):
            return None, "Invalid email or password"
        
        return user, ""
    except Exception as e:
        return None, str(e)


async def get_user_by_id(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> User | None:
    """Get user by ID."""
    result = await session.execute(
        select(User).where(User.id == user_id).where(User.is_active.is_(True))
    )
    return result.scalars().first()


async def get_user_memberships(
    session: AsyncSession,
    user_id: uuid.UUID,
) -> list:
    """Get all tenant memberships for a user."""
    result = await session.execute(
        select(TenantMembership).where(TenantMembership.user_id == user_id)
    )
    return result.scalars().all()


async def get_tenant_by_id(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> Tenant | None:
    """Get tenant by ID."""
    result = await session.execute(
        select(Tenant).where(Tenant.id == tenant_id)
    )
    return result.scalars().first()


async def get_user_role_in_tenant(
    session: AsyncSession,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> UserRole | None:
    """Get user's role in a specific tenant."""
    result = await session.execute(
        select(TenantMembership).where(
            and_(
                TenantMembership.user_id == user_id,
                TenantMembership.tenant_id == tenant_id,
            )
        )
    )
    membership = result.scalars().first()
    return membership.role if membership else None

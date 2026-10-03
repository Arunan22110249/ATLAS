"""
Tests for authentication service.
"""

import uuid

import pytest

from backend.models import UserRole
from backend.services import auth


def test_hash_password():
    """Test password hashing."""
    password = "test_password_123"
    hashed = auth.hash_password(password)
    
    assert hashed != password
    assert auth.verify_password(password, hashed)
    assert not auth.verify_password("wrong_password", hashed)


def test_verify_password_invalid():
    """Test password verification with invalid hash."""
    assert not auth.verify_password("password", "invalid_hash")


def test_create_jwt_token():
    """Test JWT token creation."""
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    
    token, expires_in = auth.create_jwt_token(user_id, tenant_id)
    
    assert isinstance(token, str)
    assert expires_in > 0
    
    # Decode token
    payload = auth.decode_jwt_token(token)
    assert payload is not None
    assert payload["sub"] == str(user_id)
    assert payload["tenant_id"] == str(tenant_id)


def test_decode_jwt_token_invalid():
    """Test JWT token decoding with invalid token."""
    assert auth.decode_jwt_token("invalid_token") is None


@pytest.mark.asyncio
async def test_register_user(async_session):
    """Test user registration."""
    from backend.schemas import UserRegisterRequest
    
    request = UserRegisterRequest(
        email="test@example.com",
        password="TestPassword123!",
        full_name="Test User",
        tenant_name="Test Tenant",
    )
    
    user, error = await auth.register_user(async_session, request)
    
    assert error == ""
    assert user.email == "test@example.com"
    assert user.full_name == "Test User"
    assert user.tenant_id is not None


@pytest.mark.asyncio
async def test_authenticate_user(async_session):
    """Test user authentication."""
    from backend.schemas import UserRegisterRequest
    
    # Register user first
    request = UserRegisterRequest(
        email="auth_test@example.com",
        password="TestPassword123!",
        full_name="Auth Test",
        tenant_name="Auth Test Tenant",
    )
    user, _ = await auth.register_user(async_session, request)
    
    # Authenticate
    auth_user, error = await auth.authenticate_user(
        async_session,
        "auth_test@example.com",
        "TestPassword123!",
    )
    
    assert error == ""
    assert auth_user.id == user.id


@pytest.mark.asyncio
async def test_authenticate_user_wrong_password(async_session):
    """Test authentication with wrong password."""
    from backend.schemas import UserRegisterRequest
    
    # Register user
    request = UserRegisterRequest(
        email="wrong_pwd@example.com",
        password="TestPassword123!",
        tenant_name="Test",
    )
    await auth.register_user(async_session, request)
    
    # Try wrong password
    auth_user, error = await auth.authenticate_user(
        async_session,
        "wrong_pwd@example.com",
        "WrongPassword",
    )
    
    assert auth_user is None
    assert "Invalid" in error


@pytest.mark.asyncio
async def test_get_user_role_in_tenant(async_session):
    """Test getting user role in tenant."""
    from backend.schemas import UserRegisterRequest
    
    # Register user
    request = UserRegisterRequest(
        email="role_test@example.com",
        password="TestPassword123!",
        tenant_name="Role Test",
    )
    user, _ = await auth.register_user(async_session, request)
    
    # Get role
    role = await auth.get_user_role_in_tenant(
        async_session,
        user.id,
        user.tenant_id,
    )
    
    assert role == UserRole.ADMIN


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

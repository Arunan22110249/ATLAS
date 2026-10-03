"""
Admin CLI utilities for ATLAS.
"""

import asyncio
import typer
from typing import Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import uuid

from backend.config import get_settings
from backend.models import Base, Tenant, User, UserRole, TenantMembership
from backend.database import init_db, close_db
from backend.services.auth import AuthService

app = typer.Typer()


@app.command()
async def create_tenant(
    name: str = typer.Option(..., help="Tenant name"),
    slug: Optional[str] = typer.Option(None, help="Tenant slug (auto-generated if not provided)")
):
    """Create a new tenant."""
    settings = get_settings()
    
    if not slug:
        slug = name.lower().replace(" ", "-")
    
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        tenant = Tenant(
            id=uuid.uuid4(),
            name=name,
            slug=slug,
            metadata={}
        )
        session.add(tenant)
        await session.commit()
        typer.echo(f"✓ Tenant created: {name} ({slug})")
        typer.echo(f"  ID: {tenant.id}")
    
    await engine.dispose()


@app.command()
async def create_admin_user(
    tenant_slug: str = typer.Option(..., help="Tenant slug"),
    email: str = typer.Option(..., help="User email"),
    password: str = typer.Option(..., prompt=True, hide_input=True, help="User password"),
    full_name: Optional[str] = typer.Option(None, help="Full name")
):
    """Create an admin user for a tenant."""
    settings = get_settings()
    
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Find tenant
        from sqlalchemy import select
        result = await session.execute(
            select(Tenant).where(Tenant.slug == tenant_slug)
        )
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            typer.echo(f"✗ Tenant not found: {tenant_slug}", err=True)
            raise typer.Exit(1)
        
        # Create user
        hashed_password = AuthService.hash_password(password)
        user = User(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            email=email,
            hashed_password=hashed_password,
            full_name=full_name,
            is_active=True
        )
        session.add(user)
        await session.flush()
        
        # Create membership with admin role
        membership = TenantMembership(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            user_id=user.id,
            role=UserRole.ADMIN
        )
        session.add(membership)
        await session.commit()
        
        typer.echo(f"✓ Admin user created: {email}")
        typer.echo(f"  User ID: {user.id}")
        typer.echo(f"  Tenant: {tenant.name}")
    
    await engine.dispose()


@app.command()
async def init_database():
    """Initialize database schema."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=True)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    await engine.dispose()
    typer.echo("✓ Database initialized")


@app.command()
async def seed_demo_data(
    tenant_slug: str = typer.Option("demo", help="Tenant slug for demo data")
):
    """Seed database with demo data."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        from backend.models import Collection
        from sqlalchemy import select
        
        # Create or get demo tenant
        result = await session.execute(
            select(Tenant).where(Tenant.slug == tenant_slug)
        )
        tenant = result.scalar_one_or_none()
        
        if not tenant:
            tenant = Tenant(
                id=uuid.uuid4(),
                name="Demo Tenant",
                slug=tenant_slug,
                metadata={"demo": True}
            )
            session.add(tenant)
            await session.flush()
        
        # Create demo collections
        collections = [
            Collection(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                name="Product Documentation",
                description="Product user guides and technical docs"
            ),
            Collection(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                name="FAQ",
                description="Frequently asked questions"
            ),
            Collection(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                name="Blog Posts",
                description="Company blog articles"
            )
        ]
        
        for col in collections:
            session.add(col)
        
        await session.commit()
        typer.echo(f"✓ Demo data seeded for tenant: {tenant.name}")
        typer.echo(f"  Created {len(collections)} collections")
    
    await engine.dispose()


@app.command()
async def list_tenants():
    """List all tenants."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(Tenant))
        tenants = result.scalars().all()
        
        if not tenants:
            typer.echo("No tenants found")
            return
        
        typer.echo(f"\nFound {len(tenants)} tenants:\n")
        for tenant in tenants:
            typer.echo(f"  • {tenant.name}")
            typer.echo(f"    Slug: {tenant.slug}")
            typer.echo(f"    ID: {tenant.id}")
            typer.echo()
    
    await engine.dispose()


@app.command()
async def reset_database():
    """Reset database (WARNING: destructive operation)."""
    if not typer.confirm("⚠ This will delete all data. Are you sure?"):
        typer.echo("Cancelled")
        raise typer.Exit(0)
    
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    
    await engine.dispose()
    typer.echo("✓ Database reset")


if __name__ == "__main__":
    app()

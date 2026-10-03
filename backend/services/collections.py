"""
Collection management service.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Collection


class CollectionService:
    """Manage document collections."""
    
    @staticmethod
    async def create_collection(
        session: AsyncSession,
        tenant_id: UUID,
        name: str,
        description: str | None = None,
        metadata: dict | None = None
    ) -> Collection:
        """Create a new collection."""
        collection = Collection(
            tenant_id=tenant_id,
            name=name,
            description=description,
            attrs=metadata or {}
        )
        session.add(collection)
        await session.flush()
        return collection
    
    @staticmethod
    async def get_collection(
        session: AsyncSession,
        collection_id: UUID,
        tenant_id: UUID
    ) -> Collection | None:
        """Get a collection by ID."""
        result = await session.execute(
            select(Collection).where(
                Collection.id == collection_id,
                Collection.tenant_id == tenant_id
            )
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def list_collections(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int = 0,
        limit: int = 50
    ) -> list[Collection]:
        """List collections for a tenant."""
        result = await session.execute(
            select(Collection)
            .where(Collection.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
            .order_by(Collection.created_at.desc())
        )
        return result.scalars().all()
    
    @staticmethod
    async def count_collections(
        session: AsyncSession,
        tenant_id: UUID
    ) -> int:
        """Count collections for a tenant."""
        result = await session.execute(
            select(Collection)
            .where(Collection.tenant_id == tenant_id)
        )
        return len(result.scalars().all())
    
    @staticmethod
    async def update_collection(
        session: AsyncSession,
        collection_id: UUID,
        tenant_id: UUID,
        name: str | None = None,
        description: str | None = None,
        metadata: dict | None = None
    ) -> Collection | None:
        """Update a collection."""
        collection = await CollectionService.get_collection(
            session, collection_id, tenant_id
        )
        if not collection:
            return None
        
        if name is not None:
            collection.name = name
        if description is not None:
            collection.description = description
        if metadata is not None:
            collection.attrs = {**(collection.attrs or {}), **metadata}
        
        await session.flush()
        return collection
    
    @staticmethod
    async def delete_collection(
        session: AsyncSession,
        collection_id: UUID,
        tenant_id: UUID
    ) -> bool:
        """Delete a collection."""
        collection = await CollectionService.get_collection(
            session, collection_id, tenant_id
        )
        if not collection:
            return False
        
        await session.delete(collection)
        return True
    
    @staticmethod
    async def get_collection_stats(
        session: AsyncSession,
        collection_id: UUID,
        tenant_id: UUID
    ) -> dict | None:
        """Get statistics for a collection."""
        collection = await CollectionService.get_collection(
            session, collection_id, tenant_id
        )
        if not collection:
            return None
        
        # Count documents
        from sqlalchemy import func

        from backend.models import Document
        
        doc_result = await session.execute(
            select(func.count(Document.id)).where(
                Document.collection_id == collection_id,
                Document.tenant_id == tenant_id
            )
        )
        doc_count = doc_result.scalar() or 0
        
        # Count chunks
        from backend.models import Chunk
        chunk_result = await session.execute(
            select(func.count(Chunk.id)).where(
                Chunk.tenant_id == tenant_id,
                Chunk.document_id.in_(
                    select(Document.id).where(
                        Document.collection_id == collection_id
                    )
                )
            )
        )
        chunk_count = chunk_result.scalar() or 0
        
        return {
            "collection_id": str(collection_id),
            "name": collection.name,
            "description": collection.description,
            "document_count": doc_count,
            "chunk_count": chunk_count,
            "created_at": collection.created_at.isoformat(),
            "updated_at": collection.updated_at.isoformat(),
        }

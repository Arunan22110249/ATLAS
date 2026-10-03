"""
RAG evaluation service.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import EvaluationExample, EvaluationRun


class EvaluationService:
    """Manage RAG evaluations."""
    
    @staticmethod
    async def create_evaluation_run(
        session: AsyncSession,
        tenant_id: UUID,
        name: str,
        description: str | None = None,
        total_examples: int = 0
    ) -> EvaluationRun:
        """Create a new evaluation run."""
        run = EvaluationRun(
            tenant_id=tenant_id,
            name=name,
            description=description,
            status="pending",
            total_examples=total_examples,
            completed_examples=0
        )
        session.add(run)
        await session.flush()
        return run
    
    @staticmethod
    async def get_evaluation_run(
        session: AsyncSession,
        run_id: UUID,
        tenant_id: UUID
    ) -> EvaluationRun | None:
        """Get an evaluation run."""
        result = await session.execute(
            select(EvaluationRun).where(
                EvaluationRun.id == run_id,
                EvaluationRun.tenant_id == tenant_id
            )
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def list_evaluation_runs(
        session: AsyncSession,
        tenant_id: UUID,
        skip: int = 0,
        limit: int = 50
    ) -> list[EvaluationRun]:
        """List evaluation runs for a tenant."""
        result = await session.execute(
            select(EvaluationRun)
            .where(EvaluationRun.tenant_id == tenant_id)
            .offset(skip)
            .limit(limit)
            .order_by(EvaluationRun.created_at.desc())
        )
        return result.scalars().all()
    
    @staticmethod
    async def update_evaluation_run(
        session: AsyncSession,
        run_id: UUID,
        tenant_id: UUID,
        status: str | None = None,
        completed_examples: int | None = None,
        results: dict | None = None
    ) -> EvaluationRun | None:
        """Update an evaluation run."""
        run = await EvaluationService.get_evaluation_run(
            session, run_id, tenant_id
        )
        if not run:
            return None
        
        if status:
            run.status = status
        if completed_examples is not None:
            run.completed_examples = completed_examples
        if results:
            run.results = results
        
        if run.completed_examples >= run.total_examples and run.total_examples > 0:
            run.status = "completed"
            run.completed_at = datetime.utcnow()
        
        await session.flush()
        return run
    
    @staticmethod
    async def add_evaluation_example(
        session: AsyncSession,
        run_id: UUID,
        question: str,
        expected_answer: str | None = None,
        generated_answer: str | None = None,
        retrieved_documents: list[str] | None = None,
        score: float | None = None,
        metrics: dict | None = None
    ) -> EvaluationExample:
        """Add an example to an evaluation run."""
        example = EvaluationExample(
            run_id=run_id,
            question=question,
            expected_answer=expected_answer,
            generated_answer=generated_answer,
            retrieved_documents=retrieved_documents or [],
            score=score,
            metrics=metrics or {}
        )
        session.add(example)
        await session.flush()
        return example
    
    @staticmethod
    async def get_evaluation_examples(
        session: AsyncSession,
        run_id: UUID,
        skip: int = 0,
        limit: int = 100
    ) -> list[EvaluationExample]:
        """Get examples from an evaluation run."""
        result = await session.execute(
            select(EvaluationExample)
            .where(EvaluationExample.run_id == run_id)
            .offset(skip)
            .limit(limit)
            .order_by(EvaluationExample.created_at.desc())
        )
        return result.scalars().all()
    
    @staticmethod
    async def calculate_metrics(
        session: AsyncSession,
        run_id: UUID
    ) -> dict:
        """Calculate aggregate metrics for an evaluation run."""
        # Get all examples
        examples = await session.execute(
            select(EvaluationExample)
            .where(EvaluationExample.run_id == run_id)
        )
        examples_list = examples.scalars().all()
        
        if not examples_list:
            return {
                "total_examples": 0,
                "average_score": 0.0,
                "min_score": 0.0,
                "max_score": 0.0,
                "completion_rate": 0.0
            }
        
        scores = [e.score for e in examples_list if e.score is not None]
        completed = len([e for e in examples_list if e.generated_answer])
        
        return {
            "total_examples": len(examples_list),
            "completed_examples": completed,
            "completion_rate": completed / len(examples_list) if examples_list else 0.0,
            "average_score": sum(scores) / len(scores) if scores else 0.0,
            "min_score": min(scores) if scores else 0.0,
            "max_score": max(scores) if scores else 0.0,
            "total_score": sum(scores) if scores else 0.0,
        }
    
    @staticmethod
    async def delete_evaluation_run(
        session: AsyncSession,
        run_id: UUID,
        tenant_id: UUID
    ) -> bool:
        """Delete an evaluation run and its examples."""
        run = await EvaluationService.get_evaluation_run(
            session, run_id, tenant_id
        )
        if not run:
            return False
        
        # Delete examples first
        await session.execute(
            select(EvaluationExample).where(
                EvaluationExample.run_id == run_id
            )
        )
        
        await session.delete(run)
        return True


# Evaluation metrics calculators

class BleuScore:
    """BLEU score calculation."""
    
    @staticmethod
    def calculate(reference: str, generated: str) -> float:
        """Calculate BLEU score (simplified)."""
        from collections import Counter
        
        ref_tokens = reference.lower().split()
        gen_tokens = generated.lower().split()
        
        if not gen_tokens:
            return 0.0
        
        common = sum((Counter(ref_tokens) & Counter(gen_tokens)).values())
        score = common / len(gen_tokens) if gen_tokens else 0.0
        
        return min(score, 1.0)


class RougeScore:
    """ROUGE score calculation."""
    
    @staticmethod
    def calculate(reference: str, generated: str) -> float:
        """Calculate ROUGE-L score (simplified)."""
        from difflib import SequenceMatcher
        
        matcher = SequenceMatcher(None, reference, generated)
        matching_blocks = matcher.get_matching_blocks()
        matches = sum(block.size for block in matching_blocks)
        
        score = 2 * matches / (len(reference) + len(generated)) if (len(reference) + len(generated)) > 0 else 0.0
        
        return min(score, 1.0)


class MeteorScore:
    """METEOR score calculation."""
    
    @staticmethod
    def calculate(reference: str, generated: str) -> float:
        """Calculate METEOR score (simplified)."""
        ref_tokens = set(reference.lower().split())
        gen_tokens = set(generated.lower().split())
        
        if not ref_tokens or not gen_tokens:
            return 0.0
        
        precision = len(ref_tokens & gen_tokens) / len(gen_tokens)
        recall = len(ref_tokens & gen_tokens) / len(ref_tokens)
        
        if precision + recall == 0:
            return 0.0
        
        f_mean = (2 * precision * recall) / (precision + recall)
        return min(f_mean, 1.0)

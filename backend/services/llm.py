"""
LLM service for RAG answer generation.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """LLM response data."""
    text: str
    tokens_input: int
    tokens_output: int
    model: str


class LLMService:
    """Provider-agnostic LLM service."""
    
    def __init__(
        self,
        provider: str = "openai",
        model: str = "gpt-4o-mini",
        api_key: str = "",
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ):
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = None
    
    async def _get_client(self):
        """Lazy load LLM client."""
        if self._client is None:
            if self.provider == "openai":
                try:
                    from openai import AsyncOpenAI
                    self._client = AsyncOpenAI(api_key=self.api_key)
                except Exception as e:
                    logger.error(f"Failed to initialize OpenAI client: {e}")
                    raise
            elif self.provider == "azure_openai":
                try:
                    from openai import AsyncAzureOpenAI
                    self._client = AsyncAzureOpenAI(
                        api_key=self.api_key,
                    )
                except Exception as e:
                    logger.error(f"Failed to initialize Azure OpenAI client: {e}")
                    raise
            else:
                raise ValueError(f"Unsupported provider: {self.provider}")
        
        return self._client
    
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """
        Generate response from LLM.
        """
        try:
            client = await self._get_client()
            
            temperature = temperature or self.temperature
            max_tokens = max_tokens or self.max_tokens
            
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            messages.append({"role": "user", "content": prompt})
            
            response = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            
            return LLMResponse(
                text=response.choices[0].message.content,
                tokens_input=response.usage.prompt_tokens,
                tokens_output=response.usage.completion_tokens,
                model=self.model,
            )
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise
    
    async def generate_with_fallback(
        self,
        prompt: str,
        system_prompt: str | None = None,
        max_retries: int = 3,
    ) -> LLMResponse | None:
        """
        Generate with retry on failure.
        """
        for attempt in range(max_retries):
            try:
                return await self.generate(prompt, system_prompt)
            except Exception as e:
                logger.warning(f"LLM attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    logger.error("LLM generation failed after all retries")
                    return None
                
                # Exponential backoff
                import asyncio
                await asyncio.sleep(2 ** attempt)
        
        return None

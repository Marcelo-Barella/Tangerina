import os
import logging
from typing import List, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class EmbeddingService(ABC):
    @abstractmethod
    async def embed_text(self, text: str) -> List[float]:
        pass

    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        pass


class SentenceTransformerEmbeddingService(EmbeddingService):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model_name = model_name
        self._model = None
        self._lock = None

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                import threading
                self._lock = threading.Lock()
                with self._lock:
                    if self._model is None:
                        logger.info(f"Loading SentenceTransformer model: {self.model_name}")
                        self._model = SentenceTransformer(self.model_name)
                        logger.info(f"SentenceTransformer model loaded successfully")
            except ImportError:
                logger.error("sentence-transformers package not installed")
                raise
            except Exception as e:
                logger.error(f"Failed to load SentenceTransformer model: {e}")
                raise
        return self._model

    async def embed_text(self, text: str) -> List[float]:
        if not text or not text.strip():
            return []
        try:
            model = self._get_model()
            import asyncio
            embedding = await asyncio.to_thread(model.encode, text, normalize_embeddings=True)
            return embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return []

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        valid_texts = [t for t in texts if t and t.strip()]
        if not valid_texts:
            return [[] for _ in texts]
        try:
            model = self._get_model()
            import asyncio
            embeddings = await asyncio.to_thread(model.encode, valid_texts, normalize_embeddings=True)
            result = []
            text_idx = 0
            for original_text in texts:
                if original_text and original_text.strip():
                    embedding = embeddings[text_idx]
                    result.append(embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding))
                    text_idx += 1
                else:
                    result.append([])
            return result
        except Exception as e:
            logger.error(f"Error generating batch embeddings: {e}")
            return [[] for _ in texts]


class OpenAIEmbeddingService(EmbeddingService):
    def __init__(self, api_key: str, model: str = "text-embedding-3-small"):
        self.api_key = api_key
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=self.api_key)
            except ImportError:
                logger.error("openai package not installed")
                raise
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI client: {e}")
                raise
        return self._client

    async def embed_text(self, text: str) -> List[float]:
        if not text or not text.strip():
            return []
        try:
            client = self._get_client()
            response = await client.embeddings.create(
                model=self.model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating OpenAI embedding: {e}")
            return []

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        valid_texts = [t for t in texts if t and t.strip()]
        if not valid_texts:
            return [[] for _ in texts]
        try:
            client = self._get_client()
            response = await client.embeddings.create(
                model=self.model,
                input=valid_texts
            )
            embeddings_dict = {item.index: item.embedding for item in response.data}
            result = []
            text_idx = 0
            for original_text in texts:
                if original_text and original_text.strip():
                    result.append(embeddings_dict.get(text_idx, []))
                    text_idx += 1
                else:
                    result.append([])
            return result
        except Exception as e:
            logger.error(f"Error generating batch OpenAI embeddings: {e}")
            return [[] for _ in texts]


def create_embedding_service() -> Optional[EmbeddingService]:
    provider = os.getenv('EMBEDDING_PROVIDER', 'sentence_transformers').lower()
    
    if provider == 'openai':
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            logger.warning("OPENAI_API_KEY not set, falling back to sentence_transformers")
            provider = 'sentence_transformers'
        else:
            model = os.getenv('OPENAI_EMBEDDING_MODEL', 'text-embedding-3-small')
            try:
                return OpenAIEmbeddingService(api_key, model)
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAI embedding service: {e}, falling back to sentence_transformers")
                provider = 'sentence_transformers'
    
    if provider == 'sentence_transformers':
        model_name = os.getenv('SENTENCE_TRANSFORMER_MODEL', 'all-MiniLM-L6-v2')
        try:
            return SentenceTransformerEmbeddingService(model_name)
        except Exception as e:
            logger.error(f"Failed to initialize SentenceTransformer embedding service: {e}")
            return None
    
    logger.warning(f"Unknown embedding provider: {provider}, falling back to sentence_transformers")
    model_name = os.getenv('SENTENCE_TRANSFORMER_MODEL', 'all-MiniLM-L6-v2')
    try:
        return SentenceTransformerEmbeddingService(model_name)
    except Exception as e:
        logger.error(f"Failed to initialize SentenceTransformer embedding service: {e}")
        return None

import os
import logging
import uuid
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class MemoryManager:
    def __init__(self, embedding_service=None):
        self.embedding_service = embedding_service
        self._client = None
        self._collection = None
        self._initialized = False
        
        self.chromadb_path = os.getenv('CHROMADB_PATH', './data/chromadb')
        self.collection_name = os.getenv('CHROMADB_COLLECTION_NAME', 'tangerina_memory')
        self.max_results = int(os.getenv('MAX_RETRIEVAL_RESULTS', '10'))
        threshold = float(os.getenv('MEMORY_SIMILARITY_THRESHOLD', '0.3'))
        self.similarity_threshold = min(threshold, 0.4)
        if threshold > 0.4:
            logger.warning(f"Similarity threshold {threshold} is too high for semantic search, capping at 0.4")
        self.retention_days = int(os.getenv('MEMORY_RETENTION_DAYS', '30'))
        
        if not self.embedding_service:
            from chatbot.embedding_service import create_embedding_service
            self.embedding_service = create_embedding_service()
            if not self.embedding_service:
                logger.warning("No embedding service available, memory features disabled")
                return
        
        self._initialize_chromadb()

    def _initialize_chromadb(self):
        try:
            import chromadb
            from chromadb.config import Settings
            
            Path(self.chromadb_path).mkdir(parents=True, exist_ok=True)
            
            self._client = chromadb.PersistentClient(
                path=self.chromadb_path,
                settings=Settings(anonymized_telemetry=False)
            )
            
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            
            self._initialized = True
            logger.info(f"ChromaDB initialized at {self.chromadb_path}")
        except ImportError:
            logger.error("chromadb package not installed")
            self._initialized = False
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            self._initialized = False

    async def store_conversation(
        self,
        user_message: str,
        bot_response: str,
        guild_id: Optional[int],
        channel_id: int,
        user_id: int,
        tool_calls: Optional[List[Dict]] = None
    ):
        if not self._initialized or not self.embedding_service:
            return
        
        try:
            document = f"User: {user_message} Bot: {bot_response}"
            embedding = await self.embedding_service.embed_text(document)
            
            if not embedding:
                logger.warning("Failed to generate embedding, skipping storage")
                return
            
            metadata = {
                "guild_id": str(guild_id) if guild_id else None,
                "channel_id": str(channel_id),
                "user_id": str(user_id),
                "timestamp": datetime.utcnow().isoformat(),
                "message_type": "conversation",
            }
            
            if tool_calls:
                metadata["tool_calls"] = str(len(tool_calls))
            
            doc_id = str(uuid.uuid4())
            
            self._collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[document],
                metadatas=[metadata]
            )
            
            logger.debug(f"Stored conversation memory: {doc_id}")
        except Exception as e:
            logger.error(f"Error storing conversation: {e}", exc_info=True)
            raise

    async def retrieve_context(
        self,
        query: str,
        guild_id: Optional[int],
        channel_id: int,
        user_id: int,
        max_results: Optional[int] = None
    ) -> List[Dict]:
        if not self._initialized or not self.embedding_service:
            return []
        
        try:
            query_embedding = await self.embedding_service.embed_text(query)
            
            if not query_embedding:
                logger.warning("Failed to generate query embedding")
                return []
            
            max_results = max_results or self.max_results
            query_results_count = min(max_results * 2, 20)
            
            conditions = [
                {"channel_id": str(channel_id)},
                {"user_id": str(user_id)}
            ]
            if guild_id:
                conditions.append({"guild_id": str(guild_id)})
            where_clause = {"$and": conditions}
            
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=query_results_count,
                where=where_clause
            )
            
            memories = []
            if results and results.get('documents') and results['documents'][0]:
                documents = results['documents'][0]
                metadatas = results.get('metadatas', [[]])[0] if results.get('metadatas') else []
                distances = results.get('distances', [[]])[0] if results.get('distances') else []
                
                memory_candidates = []
                for idx, doc in enumerate(documents):
                    distance = distances[idx] if idx < len(distances) else 1.0
                    similarity = 1.0 - distance
                    
                    doc_metadata = metadatas[idx] if idx < len(metadatas) else {}
                    
                    if similarity >= self.similarity_threshold:
                        memory_candidates.append({
                            "content": doc,
                            "metadata": doc_metadata,
                            "similarity": similarity,
                            "distance": distance
                        })
                
                memory_candidates.sort(key=lambda x: x["similarity"], reverse=True)
                
                seen_content = set()
                for candidate in memory_candidates:
                    content_normalized = " ".join(candidate["content"].lower().split()[:20])
                    if content_normalized not in seen_content:
                        seen_content.add(content_normalized)
                        memories.append({
                            "content": candidate["content"],
                            "metadata": candidate["metadata"],
                            "similarity": candidate["similarity"]
                        })
                        if len(memories) >= max_results:
                            break
            
            return memories
        except Exception as e:
            logger.error(f"Error retrieving context: {e}", exc_info=True)
            return []

    async def delete_user_memories(self, user_id: int):
        if not self._initialized:
            return
        
        try:
            results = self._collection.get(
                where={"user_id": str(user_id)}
            )
            
            if results and results.get('ids'):
                self._collection.delete(ids=results['ids'])
                logger.info(f"Deleted {len(results['ids'])} memories for user {user_id}")
        except Exception as e:
            logger.error(f"Error deleting user memories: {e}", exc_info=True)

    async def delete_guild_memories(self, guild_id: int):
        if not self._initialized:
            return
        
        try:
            results = self._collection.get(
                where={"guild_id": str(guild_id)}
            )
            
            if results and results.get('ids'):
                self._collection.delete(ids=results['ids'])
                logger.info(f"Deleted {len(results['ids'])} memories for guild {guild_id}")
        except Exception as e:
            logger.error(f"Error deleting guild memories: {e}", exc_info=True)

    async def cleanup_old_memories(self):
        if not self._initialized:
            return
        
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=self.retention_days)
            
            results = self._collection.get()
            
            if not results or not results.get('ids'):
                return
            
            ids_to_delete = []
            metadatas = results.get('metadatas', [])
            
            for idx, metadata in enumerate(metadatas):
                if metadata and 'timestamp' in metadata:
                    try:
                        timestamp = datetime.fromisoformat(metadata['timestamp'])
                        if timestamp < cutoff_date:
                            ids_to_delete.append(results['ids'][idx])
                    except (ValueError, TypeError):
                        continue
            
            if ids_to_delete:
                self._collection.delete(ids=ids_to_delete)
                logger.info(f"Cleaned up {len(ids_to_delete)} old memories")
        except Exception as e:
            logger.error(f"Error cleaning up old memories: {e}", exc_info=True)

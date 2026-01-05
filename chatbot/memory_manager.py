import os
import logging
import json
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DEBUG_LOG_PATH = "/app/logs/debug.log"

def _debug_log(session_id, run_id, hypothesis_id, location, message, data):
    try:
        log_entry = {
            "id": f"log_{int(datetime.utcnow().timestamp() * 1000)}",
            "timestamp": int(datetime.utcnow().timestamp() * 1000),
            "location": location,
            "message": message,
            "data": data,
            "sessionId": session_id,
            "runId": run_id,
            "hypothesisId": hypothesis_id
        }
        Path(DEBUG_LOG_PATH).parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG_PATH, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
    except Exception:
        pass


class MemoryManager:
    def __init__(self, embedding_service=None):
        self.embedding_service = embedding_service
        self._client = None
        self._collection = None
        self._initialized = False
        
        self.chromadb_path = os.getenv('CHROMADB_PATH', './data/chromadb')
        self.collection_name = os.getenv('CHROMADB_COLLECTION_NAME', 'tangerina_memory')
        self.max_results = int(os.getenv('MAX_RETRIEVAL_RESULTS', '10'))
        self.similarity_threshold = float(os.getenv('MEMORY_SIMILARITY_THRESHOLD', '0.7'))
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
            
            # #region agent log
            _debug_log("debug-session", "init", "C", "memory_manager.py:_initialize_chromadb:33", "ChromaDB init start", {"chromadb_path": self.chromadb_path, "collection_name": self.collection_name})
            # #endregion
            
            Path(self.chromadb_path).mkdir(parents=True, exist_ok=True)
            
            self._client = chromadb.PersistentClient(
                path=self.chromadb_path,
                settings=Settings(anonymized_telemetry=False)
            )
            
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            
            # #region agent log
            _debug_log("debug-session", "init", "C", "memory_manager.py:_initialize_chromadb:49", "ChromaDB collection created", {"collection_count": self._collection.count() if hasattr(self._collection, 'count') else "unknown"})
            # #endregion
            
            self._initialized = True
            logger.info(f"ChromaDB initialized at {self.chromadb_path}")
            
            # #region agent log
            _debug_log("debug-session", "init", "C", "memory_manager.py:_initialize_chromadb:52", "ChromaDB init success", {"initialized": True})
            # #endregion
        except ImportError:
            logger.error("chromadb package not installed")
            self._initialized = False
            # #region agent log
            _debug_log("debug-session", "init", "C", "memory_manager.py:_initialize_chromadb:55", "ChromaDB init failed - import error", {"error": "ImportError"})
            # #endregion
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            self._initialized = False
            # #region agent log
            _debug_log("debug-session", "init", "C", "memory_manager.py:_initialize_chromadb:59", "ChromaDB init failed", {"error": str(e)})
            # #endregion

    async def store_conversation(
        self,
        user_message: str,
        bot_response: str,
        guild_id: Optional[int],
        channel_id: int,
        user_id: int,
        tool_calls: Optional[List[Dict]] = None
    ):
        # #region agent log
        _debug_log("debug-session", "store", "A", "memory_manager.py:store_conversation:67", "store_conversation entry", {"initialized": self._initialized, "has_embedding_service": self.embedding_service is not None, "guild_id": guild_id, "channel_id": channel_id, "user_id": user_id})
        # #endregion
        
        if not self._initialized or not self.embedding_service:
            # #region agent log
            _debug_log("debug-session", "store", "A", "memory_manager.py:store_conversation:70", "store_conversation early return", {"reason": "not_initialized_or_no_embedding"})
            # #endregion
            return
        
        try:
            document = f"User: {user_message} Bot: {bot_response}"
            
            # #region agent log
            _debug_log("debug-session", "store", "A", "memory_manager.py:store_conversation:75", "before embedding generation", {"document_length": len(document)})
            # #endregion
            
            embedding = await self.embedding_service.embed_text(document)
            
            # #region agent log
            _debug_log("debug-session", "store", "A", "memory_manager.py:store_conversation:80", "after embedding generation", {"embedding_length": len(embedding) if embedding else 0, "has_embedding": bool(embedding)})
            # #endregion
            
            if not embedding:
                logger.warning("Failed to generate embedding, skipping storage")
                # #region agent log
                _debug_log("debug-session", "store", "A", "memory_manager.py:store_conversation:85", "store_conversation early return - no embedding", {})
                # #endregion
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
            
            # #region agent log
            _debug_log("debug-session", "store", "B", "memory_manager.py:store_conversation:99", "metadata before storage", {"metadata": metadata})
            # #endregion
            
            import uuid
            doc_id = str(uuid.uuid4())
            
            # #region agent log
            _debug_log("debug-session", "store", "A", "memory_manager.py:store_conversation:105", "before collection.add", {"doc_id": doc_id, "collection_count_before": self._collection.count() if hasattr(self._collection, 'count') else "unknown"})
            # #endregion
            
            self._collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[document],
                metadatas=[metadata]
            )
            
            # #region agent log
            _debug_log("debug-session", "store", "A", "memory_manager.py:store_conversation:115", "after collection.add", {"doc_id": doc_id, "collection_count_after": self._collection.count() if hasattr(self._collection, 'count') else "unknown"})
            # #endregion
            
            logger.debug(f"Stored conversation memory: {doc_id}")
        except Exception as e:
            logger.error(f"Error storing conversation: {e}", exc_info=True)
            # #region agent log
            _debug_log("debug-session", "store", "A", "memory_manager.py:store_conversation:121", "store_conversation exception", {"error": str(e), "error_type": type(e).__name__})
            # #endregion

    async def retrieve_context(
        self,
        query: str,
        guild_id: Optional[int],
        channel_id: int,
        user_id: int,
        max_results: Optional[int] = None
    ) -> List[Dict]:
        # #region agent log
        _debug_log("debug-session", "retrieve", "A", "memory_manager.py:retrieve_context:111", "retrieve_context entry", {"initialized": self._initialized, "has_embedding_service": self.embedding_service is not None, "guild_id": guild_id, "channel_id": channel_id, "user_id": user_id, "query_length": len(query)})
        # #endregion
        
        if not self._initialized or not self.embedding_service:
            # #region agent log
            _debug_log("debug-session", "retrieve", "A", "memory_manager.py:retrieve_context:115", "retrieve_context early return", {"reason": "not_initialized_or_no_embedding"})
            # #endregion
            return []
        
        try:
            # #region agent log
            _debug_log("debug-session", "retrieve", "A", "memory_manager.py:retrieve_context:120", "before query embedding generation", {})
            # #endregion
            
            query_embedding = await self.embedding_service.embed_text(query)
            
            # #region agent log
            _debug_log("debug-session", "retrieve", "A", "memory_manager.py:retrieve_context:125", "after query embedding generation", {"embedding_length": len(query_embedding) if query_embedding else 0, "has_embedding": bool(query_embedding)})
            # #endregion
            
            if not query_embedding:
                logger.warning("Failed to generate query embedding")
                # #region agent log
                _debug_log("debug-session", "retrieve", "A", "memory_manager.py:retrieve_context:130", "retrieve_context early return - no embedding", {})
                # #endregion
                return []
            
            max_results = max_results or self.max_results
            
            # #region agent log
            self._debug_collection_contents("debug-session", "retrieve")
            _debug_log("debug-session", "retrieve", "D", "memory_manager.py:retrieve_context:137", "before where clause construction", {"guild_id": guild_id, "channel_id": channel_id, "user_id": user_id, "collection_count": self._collection.count() if hasattr(self._collection, 'count') else "unknown"})
            # #endregion
            
            conditions = [
                {"channel_id": str(channel_id)},
                {"user_id": str(user_id)}
            ]
            if guild_id:
                conditions.append({"guild_id": str(guild_id)})
            where_clause = {"$and": conditions}
            
            # #region agent log
            _debug_log("debug-session", "retrieve", "D", "memory_manager.py:retrieve_context:147", "where clause constructed", {"where_clause": where_clause, "conditions_count": len(conditions)})
            # #endregion
            
            # #region agent log
            _debug_log("debug-session", "retrieve", "E", "memory_manager.py:retrieve_context:150", "before collection.query", {"max_results": max_results, "where_clause": where_clause})
            # #endregion
            
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=max_results,
                where=where_clause
            )
            
            # #region agent log
            _debug_log("debug-session", "retrieve", "E", "memory_manager.py:retrieve_context:158", "after collection.query", {"results_keys": list(results.keys()) if results else [], "has_documents": bool(results and results.get('documents')), "documents_count": len(results.get('documents', [[]])[0]) if results and results.get('documents') and results['documents'][0] else 0})
            # #endregion
            
            memories = []
            if results and results.get('documents') and results['documents'][0]:
                documents = results['documents'][0]
                metadatas = results.get('metadatas', [[]])[0] if results.get('metadatas') else []
                distances = results.get('distances', [[]])[0] if results.get('distances') else []
                
                # #region agent log
                _debug_log("debug-session", "retrieve", "E", "memory_manager.py:retrieve_context:166", "processing query results", {"documents_count": len(documents), "metadatas_count": len(metadatas), "distances_count": len(distances), "similarity_threshold": self.similarity_threshold})
                # #endregion
                
                for idx, doc in enumerate(documents):
                    distance = distances[idx] if idx < len(distances) else 1.0
                    similarity = 1.0 - distance
                    
                    # #region agent log
                    _debug_log("debug-session", "retrieve", "E", "memory_manager.py:retrieve_context:174", "processing document", {"idx": idx, "distance": distance, "similarity": similarity, "meets_threshold": similarity >= self.similarity_threshold, "metadata": metadatas[idx] if idx < len(metadatas) else {}})
                    # #endregion
                    
                    if similarity >= self.similarity_threshold:
                        metadata = metadatas[idx] if idx < len(metadatas) else {}
                        memories.append({
                            "content": doc,
                            "metadata": metadata,
                            "similarity": similarity
                        })
            
            # #region agent log
            _debug_log("debug-session", "retrieve", "A", "memory_manager.py:retrieve_context:186", "retrieve_context return", {"memories_count": len(memories)})
            # #endregion
            
            return memories
        except Exception as e:
            logger.error(f"Error retrieving context: {e}", exc_info=True)
            # #region agent log
            _debug_log("debug-session", "retrieve", "A", "memory_manager.py:retrieve_context:192", "retrieve_context exception", {"error": str(e), "error_type": type(e).__name__})
            # #endregion
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
            cutoff_iso = cutoff_date.isoformat()
            
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
    
    def _debug_collection_contents(self, session_id="debug-session", run_id="debug"):
        if not self._initialized:
            return
        try:
            all_results = self._collection.get()
            if all_results and all_results.get('ids'):
                metadatas = all_results.get('metadatas', [])
                guild_ids = [m.get('guild_id') if m else None for m in metadatas]
                channel_ids = [m.get('channel_id') if m else None for m in metadatas]
                _debug_log(session_id, run_id, "B", "memory_manager.py:_debug_collection_contents", "collection contents", {"total_count": len(all_results['ids']), "unique_guild_ids": list(set(guild_ids)), "unique_channel_ids": list(set(channel_ids)), "sample_metadatas": metadatas[:3]})
            else:
                _debug_log(session_id, run_id, "B", "memory_manager.py:_debug_collection_contents", "collection contents", {"total_count": 0})
        except Exception as e:
            _debug_log(session_id, run_id, "B", "memory_manager.py:_debug_collection_contents", "collection contents error", {"error": str(e)})

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
        logger.debug(f"[{location}] {message} | session={session_id} run={run_id} data={json.dumps(data)}")
    except Exception as e:
        logger.error(f"Failed to write debug log: {e}")


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
            
            document_preview = document[:200] + "..." if len(document) > 200 else document
            
            # #region agent log
            _debug_log("debug-session", "store", "A", "memory_manager.py:store_conversation:75", "document content before storage", {"document_length": len(document), "document_preview": document_preview, "doc_id": None})
            # #endregion
            
            embedding = await self.embedding_service.embed_text(document)
            
            embedding_type = type(embedding).__name__ if embedding else None
            embedding_is_list = isinstance(embedding, (list, tuple)) if embedding else False
            embedding_sample = embedding[:5] if embedding and isinstance(embedding, (list, tuple)) and len(embedding) > 0 else None
            
            # #region agent log
            _debug_log("debug-session", "store", "A", "memory_manager.py:store_conversation:80", "after embedding generation", {
                "embedding_length": len(embedding) if embedding else 0,
                "has_embedding": bool(embedding),
                "embedding_type": embedding_type,
                "embedding_is_list": embedding_is_list,
                "embedding_sample": embedding_sample
            })
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
            
            import uuid
            doc_id = str(uuid.uuid4())
            
            # #region agent log
            _debug_log("debug-session", "store", "B", "memory_manager.py:store_conversation:99", "metadata before storage", {"metadata": metadata, "doc_id": doc_id, "metadata_keys": list(metadata.keys())})
            # #endregion
            
            collection_count_before = self._collection.count() if hasattr(self._collection, 'count') else None
            existing_ids = []
            try:
                existing_results = self._collection.get(limit=100)
                if existing_results and existing_results.get('ids'):
                    existing_ids = existing_results['ids'][:10]
            except Exception:
                pass
            
            # #region agent log
            self._debug_collection_contents("debug-session", "store")
            _debug_log("debug-session", "store", "A", "memory_manager.py:store_conversation:105", "before collection.add", {
                "doc_id": doc_id,
                "collection_count_before": collection_count_before,
                "existing_ids_sample": existing_ids
            })
            # #endregion
            
            add_params = {
                "ids": [doc_id],
                "embeddings_count": 1,
                "documents_count": 1,
                "metadatas_count": 1,
                "embedding_length": len(embedding) if embedding else 0,
                "document_length": len(document)
            }
            
            # #region agent log
            _debug_log("debug-session", "store", "A", "memory_manager.py:store_conversation:115", "collection.add parameters", add_params)
            # #endregion
            
            try:
                self._collection.add(
                    ids=[doc_id],
                    embeddings=[embedding],
                    documents=[document],
                    metadatas=[metadata]
                )
                
                collection_count_after = self._collection.count() if hasattr(self._collection, 'count') else None
                
                # #region agent log
                _debug_log("debug-session", "store", "A", "memory_manager.py:store_conversation:125", "after collection.add", {
                    "doc_id": doc_id,
                    "collection_count_after": collection_count_after,
                    "collection_count_increased": (collection_count_after is not None and collection_count_before is not None and collection_count_after > collection_count_before)
                })
                # #endregion
                
                verification_result = await self._verify_document_stored(doc_id, "debug-session", "store")
                
                # #region agent log
                _debug_log("debug-session", "store", "A", "memory_manager.py:store_conversation:135", "post-storage verification", {
                    "doc_id": doc_id,
                    "verification_passed": verification_result
                })
                # #endregion
                
                logger.debug(f"Stored conversation memory: {doc_id}")
            except Exception as add_error:
                error_details = {
                    "error": str(add_error),
                    "error_type": type(add_error).__name__,
                    "doc_id": doc_id,
                    "add_params": add_params
                }
                logger.error(f"ChromaDB collection.add error: {add_error}", exc_info=True)
                # #region agent log
                _debug_log("debug-session", "store", "A", "memory_manager.py:store_conversation:145", "collection.add exception", error_details)
                # #endregion
                raise
        except Exception as e:
            import traceback
            error_traceback = traceback.format_exc()
            logger.error(f"Error storing conversation: {e}", exc_info=True)
            # #region agent log
            _debug_log("debug-session", "store", "A", "memory_manager.py:store_conversation:155", "store_conversation exception", {
                "error": str(e),
                "error_type": type(e).__name__,
                "traceback": error_traceback
            })
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
            collection_count = self._collection.count() if hasattr(self._collection, 'count') else None
            all_stored_metadata = []
            try:
                all_results = self._collection.get()
                if all_results and all_results.get('metadatas'):
                    all_stored_metadata = all_results['metadatas'][:5]
            except Exception:
                pass
            _debug_log("debug-session", "retrieve", "F", "memory_manager.py:retrieve_context:137", "before where clause construction", {"guild_id": guild_id, "channel_id": channel_id, "user_id": user_id, "collection_count": collection_count, "sample_stored_metadata": all_stored_metadata})
            # #endregion
            
            conditions = [
                {"channel_id": str(channel_id)},
                {"user_id": str(user_id)}
            ]
            if guild_id:
                conditions.append({"guild_id": str(guild_id)})
            where_clause = {"$and": conditions}
            
            # #region agent log
            _debug_log("debug-session", "retrieve", "F", "memory_manager.py:retrieve_context:147", "where clause constructed", {"where_clause": where_clause, "conditions_count": len(conditions), "query_guild_id_str": str(guild_id) if guild_id else None, "query_channel_id_str": str(channel_id), "query_user_id_str": str(user_id)})
            # #endregion
            
            # #region agent log
            query_no_where_result = None
            try:
                query_no_where_result = self._collection.query(
                    query_embeddings=[query_embedding],
                    n_results=min(5, max_results)
                )
                no_where_docs_count = len(query_no_where_result.get('documents', [[]])[0]) if query_no_where_result and query_no_where_result.get('documents') and query_no_where_result['documents'][0] else 0
                no_where_metadata_sample = []
                if query_no_where_result and query_no_where_result.get('metadatas') and query_no_where_result['metadatas'][0]:
                    no_where_metadata_sample = query_no_where_result['metadatas'][0][:3]
                _debug_log("debug-session", "retrieve", "I", "memory_manager.py:retrieve_context:151", "query without where clause", {"documents_count": no_where_docs_count, "sample_metadata": no_where_metadata_sample})
            except Exception as e:
                _debug_log("debug-session", "retrieve", "I", "memory_manager.py:retrieve_context:157", "query without where clause error", {"error": str(e)})
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
            results_structure = {}
            if results:
                results_structure = {
                    "has_ids": bool(results.get('ids')),
                    "has_documents": bool(results.get('documents')),
                    "has_metadatas": bool(results.get('metadatas')),
                    "has_distances": bool(results.get('distances')),
                    "ids_type": type(results.get('ids')).__name__ if results.get('ids') else None,
                    "documents_type": type(results.get('documents')).__name__ if results.get('documents') else None,
                    "ids_length": len(results.get('ids', [])) if results.get('ids') else 0,
                    "documents_nested_length": len(results.get('documents', [])) if results.get('documents') else 0,
                    "documents_inner_length": len(results.get('documents', [[]])[0]) if results.get('documents') and results['documents'][0] else 0,
                    "metadatas_nested_length": len(results.get('metadatas', [])) if results.get('metadatas') else 0,
                    "metadatas_inner_length": len(results.get('metadatas', [[]])[0]) if results.get('metadatas') and results['metadatas'][0] else 0
                }
                if results.get('documents') and results['documents'][0]:
                    results_structure["documents_sample"] = [doc[:50] + "..." if len(doc) > 50 else doc for doc in results['documents'][0][:2]]
                if results.get('metadatas') and results['metadatas'][0]:
                    results_structure["metadatas_sample"] = results['metadatas'][0][:2]
            _debug_log("debug-session", "retrieve", "G", "memory_manager.py:retrieve_context:178", "after collection.query - full structure", results_structure)
            # #endregion
            
            memories = []
            if results and results.get('documents') and results['documents'][0]:
                documents = results['documents'][0]
                metadatas = results.get('metadatas', [[]])[0] if results.get('metadatas') else []
                distances = results.get('distances', [[]])[0] if results.get('distances') else []
                
                # #region agent log
                sample_doc = documents[0] if documents else None
                sample_meta = metadatas[0] if metadatas else {}
                sample_distance = distances[0] if distances else None
                _debug_log("debug-session", "retrieve", "H", "memory_manager.py:retrieve_context:166", "processing query results", {"documents_count": len(documents), "metadatas_count": len(metadatas), "distances_count": len(distances), "similarity_threshold": self.similarity_threshold, "sample_doc_preview": sample_doc[:100] if sample_doc else None, "sample_metadata": sample_meta, "sample_distance": sample_distance})
                # #endregion
                
                for idx, doc in enumerate(documents):
                    distance = distances[idx] if idx < len(distances) else 1.0
                    similarity = 1.0 - distance
                    
                    doc_metadata = metadatas[idx] if idx < len(metadatas) else {}
                    metadata_matches = {
                        "channel_id_match": doc_metadata.get('channel_id') == str(channel_id) if doc_metadata.get('channel_id') else False,
                        "user_id_match": doc_metadata.get('user_id') == str(user_id) if doc_metadata.get('user_id') else False,
                        "guild_id_match": (doc_metadata.get('guild_id') == str(guild_id)) if (guild_id and doc_metadata.get('guild_id')) else (not guild_id and (doc_metadata.get('guild_id') is None or doc_metadata.get('guild_id') == 'None')),
                        "doc_metadata_channel_id": doc_metadata.get('channel_id'),
                        "doc_metadata_user_id": doc_metadata.get('user_id'),
                        "doc_metadata_guild_id": doc_metadata.get('guild_id')
                    }
                    
                    # #region agent log
                    _debug_log("debug-session", "retrieve", "J", "memory_manager.py:retrieve_context:194", "processing document", {"idx": idx, "distance": distance, "similarity": similarity, "similarity_threshold": self.similarity_threshold, "meets_threshold": similarity >= self.similarity_threshold, "metadata": doc_metadata, "metadata_matches": metadata_matches})
                    # #endregion
                    
                    if similarity >= self.similarity_threshold:
                        memories.append({
                            "content": doc,
                            "metadata": doc_metadata,
                            "similarity": similarity
                        })
                    else:
                        # #region agent log
                        _debug_log("debug-session", "retrieve", "J", "memory_manager.py:retrieve_context:204", "document filtered by similarity", {"idx": idx, "similarity": similarity, "threshold": self.similarity_threshold, "diff": self.similarity_threshold - similarity})
                        # #endregion
            else:
                # #region agent log
                _debug_log("debug-session", "retrieve", "H", "memory_manager.py:retrieve_context:171", "no documents in results", {"results_is_none": results is None, "has_documents_key": bool(results and 'documents' in results), "documents_is_empty_list": bool(results and results.get('documents') == []), "documents_is_none": bool(results and results.get('documents') is None)})
                # #endregion
            
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
                user_ids = [m.get('user_id') if m else None for m in metadatas]
                guild_ids = [m.get('guild_id') if m else None for m in metadatas]
                channel_ids = [m.get('channel_id') if m else None for m in metadatas]
                metadata_types = []
                for m in metadatas[:3]:
                    if m:
                        metadata_types.append({
                            "guild_id_type": type(m.get('guild_id')).__name__ if m.get('guild_id') is not None else "None",
                            "guild_id_value": m.get('guild_id'),
                            "channel_id_type": type(m.get('channel_id')).__name__ if m.get('channel_id') is not None else "None",
                            "user_id_type": type(m.get('user_id')).__name__ if m.get('user_id') is not None else "None"
                        })
                _debug_log(session_id, run_id, "F", "memory_manager.py:_debug_collection_contents", "collection contents", {"total_count": len(all_results['ids']), "unique_user_ids": list(set(user_ids)), "unique_guild_ids": list(set(guild_ids)), "unique_channel_ids": list(set(channel_ids)), "metadata_types_sample": metadata_types, "sample_metadatas": metadatas[:3]})
            else:
                _debug_log(session_id, run_id, "F", "memory_manager.py:_debug_collection_contents", "collection contents", {"total_count": 0})
        except Exception as e:
            _debug_log(session_id, run_id, "F", "memory_manager.py:_debug_collection_contents", "collection contents error", {"error": str(e)})
    
    async def _verify_document_stored(self, doc_id: str, session_id: str, run_id: str) -> bool:
        if not self._initialized:
            return False
        try:
            result = self._collection.get(ids=[doc_id])
            if result and result.get('ids') and doc_id in result['ids']:
                idx = result['ids'].index(doc_id)
                document = result.get('documents', [])[idx] if result.get('documents') and idx < len(result['documents']) else None
                metadata = result.get('metadatas', [])[idx] if result.get('metadatas') and idx < len(result['metadatas']) else None
                _debug_log(session_id, run_id, "B", "memory_manager.py:_verify_document_stored", "document verification success", {
                    "doc_id": doc_id,
                    "has_document": document is not None,
                    "has_metadata": metadata is not None,
                    "document_length": len(document) if document else 0
                })
                return True
            else:
                _debug_log(session_id, run_id, "B", "memory_manager.py:_verify_document_stored", "document verification failed", {
                    "doc_id": doc_id,
                    "result_ids": result.get('ids', []) if result else []
                })
                return False
        except Exception as e:
            _debug_log(session_id, run_id, "B", "memory_manager.py:_verify_document_stored", "document verification error", {
                "doc_id": doc_id,
                "error": str(e),
                "error_type": type(e).__name__
            })
            return False

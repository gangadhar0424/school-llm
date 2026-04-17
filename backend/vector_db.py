"""
ChromaDB vector database for storing and retrieving document embeddings
Used for RAG (Retrieval Augmented Generation) in Q&A feature
"""
import chromadb
import asyncio
import time
from chromadb.config import Settings
from typing import List, Dict, Optional
import hashlib
import logging
from sentence_transformers import SentenceTransformer
from config import settings as app_settings
from ai.ollama_client import ollama_client
from timing_utils import log_phase

logger = logging.getLogger(__name__)
_VECTOR_SCHEMA_VERSION = "2026-03-31-section-chunks-v1"

class VectorDB:
    """ChromaDB vector database manager"""
    
    def __init__(self):
        """Initialize ChromaDB client"""
        self.client = chromadb.PersistentClient(
            path=app_settings.CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False)
        )
        self.embeddings_provider = app_settings.EMBEDDINGS_PROVIDER.lower().strip()
        self.embedding_model = None
        if self.embeddings_provider == "sentence_transformers":
            self.embedding_model = SentenceTransformer(app_settings.LOCAL_EMBEDDING_MODEL)
        logger.info("ChromaDB initialized")
    
    def get_or_create_collection(self, collection_name: str):
        """Get or create a collection for a PDF"""
        return self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
    
    def create_collection_name(self, pdf_url: str) -> str:
        """Create a unique collection name from PDF URL"""
        hash_object = hashlib.md5(f"{_VECTOR_SCHEMA_VERSION}:{pdf_url}".encode())
        return f"pdf_{hash_object.hexdigest()}"
    
    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using a local model"""
        try:
            if self.embeddings_provider == "ollama":
                return await ollama_client.embeddings(texts)

            if self.embedding_model is None:
                raise Exception("Sentence-Transformers model not initialized")

            embeddings = await asyncio.to_thread(
                self.embedding_model.encode,
                texts,
                normalize_embeddings=True
            )
            return [emb.tolist() for emb in embeddings]
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            raise
    
    async def add_documents(self, pdf_url: str, chunks: List[str], metadata: List[Dict] = None):
        """Add document chunks to vector database"""
        try:
            collection_name = self.create_collection_name(pdf_url)
            collection = self.get_or_create_collection(collection_name)

            # Skip expensive re-embedding if this PDF was already indexed.
            if collection.count() > 0:
                logger.info(f"Collection {collection_name} already indexed; skipping re-add")
                return collection_name
            
            # Generate embeddings
            embeddings = await self.get_embeddings(chunks)
            
            # Create IDs for chunks
            ids = [f"chunk_{i}" for i in range(len(chunks))]
            
            # Prepare metadata
            if metadata is None:
                metadata = [{"chunk_index": i} for i in range(len(chunks))]
            
            # Add to collection
            collection.add(
                embeddings=embeddings,
                documents=chunks,
                ids=ids,
                metadatas=metadata
            )
            
            logger.info(f"Added {len(chunks)} chunks to collection {collection_name}")
            return collection_name
            
        except Exception as e:
            logger.error(f"Error adding documents to vector DB: {e}")
            raise
    
    async def query_documents(
        self,
        pdf_url: str,
        query: str,
        n_results: int = 5,
        chapter: Optional[int] = None,
        preferred_section_codes: Optional[List[str]] = None
    ) -> Dict:
        """
        Query vector database with enhanced RAG retrieval
        
        Args:
            pdf_url: PDF URL or identifier
            query: Search query
            n_results: Number of results to return
            chapter: Optional chapter number to filter by
            
        Returns:
            Dictionary with ranked results including metadata
        """
        try:
            total_started = time.perf_counter()
            collection_name = self.create_collection_name(pdf_url)
            collection = self.get_or_create_collection(collection_name)
            
            # Check if collection is empty
            if collection.count() == 0:
                logger.warning(f"Collection {collection_name} is empty")
                return {
                    "documents": [],
                    "distances": [],
                    "metadatas": [],
                    "scores": []
                }
            
            # Generate query embedding
            phase_started = time.perf_counter()
            query_embedding = (await self.get_embeddings([query]))[0]
            log_phase(logger, "vector.query", "embed_query", phase_started, query_chars=len(query))
            
            # Retrieve more results for reranking
            retrieve_n = min(n_results * 3, collection.count())
            
            # Query collection
            phase_started = time.perf_counter()
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=retrieve_n
            )
            log_phase(logger, "vector.query", "chroma_query", phase_started, retrieve_n=retrieve_n)
            
            if not results["documents"] or not results["documents"][0]:
                return {
                    "documents": [],
                    "distances": [],
                    "metadatas": [],
                    "scores": []
                }
            
            # Process and rerank results
            phase_started = time.perf_counter()
            ranked_results = self._rerank_results(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
                query,
                n_results,
                chapter,
                preferred_section_codes or []
            )
            log_phase(
                logger,
                "vector.query",
                "rerank",
                phase_started,
                returned=len(ranked_results.get("documents") or []),
            )
            log_phase(logger, "vector.query", "total", total_started, returned=len(ranked_results.get("documents") or []))
            
            return ranked_results
            
        except Exception as e:
            logger.error(f"Error querying vector DB: {e}")
            raise

    async def query_documents_multi(
        self,
        pdf_url: str,
        queries: List[str],
        n_results: int = 5,
        chapter: Optional[int] = None,
        preferred_section_codes: Optional[List[str]] = None
    ) -> List[Dict]:
        """Query a PDF collection for multiple query variants in one batched embedding request."""
        try:
            total_started = time.perf_counter()
            cleaned_queries = [str(query or "").strip() for query in queries if str(query or "").strip()]
            if not cleaned_queries:
                return []

            collection_name = self.create_collection_name(pdf_url)
            collection = self.get_or_create_collection(collection_name)

            if collection.count() == 0:
                logger.warning(f"Collection {collection_name} is empty")
                empty = {
                    "documents": [],
                    "distances": [],
                    "metadatas": [],
                    "scores": []
                }
                return [empty.copy() for _ in cleaned_queries]

            phase_started = time.perf_counter()
            query_embeddings = await self.get_embeddings(cleaned_queries)
            log_phase(logger, "vector.multi", "embed_queries", phase_started, query_count=len(cleaned_queries))
            retrieve_n = min(n_results * 3, collection.count())
            phase_started = time.perf_counter()
            results = collection.query(
                query_embeddings=query_embeddings,
                n_results=retrieve_n
            )
            log_phase(logger, "vector.multi", "chroma_query", phase_started, query_count=len(cleaned_queries), retrieve_n=retrieve_n)

            documents_groups = results.get("documents", []) or []
            metadatas_groups = results.get("metadatas", []) or []
            distances_groups = results.get("distances", []) or []

            ranked_sets: List[Dict] = []
            phase_started = time.perf_counter()
            for idx, query in enumerate(cleaned_queries):
                documents = documents_groups[idx] if idx < len(documents_groups) else []
                metadatas = metadatas_groups[idx] if idx < len(metadatas_groups) else []
                distances = distances_groups[idx] if idx < len(distances_groups) else []
                ranked_sets.append(
                    self._rerank_results(
                        documents,
                        metadatas,
                        distances,
                        query,
                        n_results,
                        chapter,
                        preferred_section_codes or []
                    )
                )
            log_phase(logger, "vector.multi", "rerank", phase_started, query_count=len(cleaned_queries))
            log_phase(logger, "vector.multi", "total", total_started, query_count=len(cleaned_queries))

            return ranked_sets

        except Exception as e:
            logger.error(f"Error querying vector DB with multiple queries: {e}")
            raise
    
    def _rerank_results(
        self,
        documents: list,
        metadatas: list,
        distances: list,
        query: str,
        n_results: int,
        chapter: Optional[int] = None,
        preferred_section_codes: Optional[List[str]] = None
    ) -> Dict:
        """
        Rerank search results based on relevance and metadata
        
        Args:
            documents: List of document chunks
            metadatas: List of metadata for chunks
            distances: Distances from query
            query: Original query
            n_results: Number of results to return
            chapter: Optional chapter filter
            
        Returns:
            Reranked results
        """
        preferred_section_codes = [str(code or "").strip() for code in (preferred_section_codes or []) if str(code or "").strip()]
        scored_results = []
        
        for doc, meta, distance in zip(documents, metadatas, distances):
            score = 1 - distance  # Convert distance to similarity score
            
            # Filter by chapter if specified
            if chapter is not None:
                doc_chapter = meta.get("metadata", {}).get("chapter") if isinstance(meta, dict) else None
                if doc_chapter and int(doc_chapter) != chapter:
                    continue
            
            # Boost score if query terms appear in document
            query_terms = query.lower().split()
            doc_lower = doc.lower()
            term_matches = sum(1 for term in query_terms if term in doc_lower)
            if term_matches > 0:
                score += 0.1 * min(term_matches, 3)  # Boost up to 0.3
            
            # Boost score based on metadata relevance
            if isinstance(meta, dict):
                meta_dict = meta.get("metadata", meta)
                if isinstance(meta_dict, dict):
                    if meta_dict.get("topic") and query.lower() in str(meta_dict.get("topic", "")).lower():
                        score += 0.15
                    section_code = str(meta_dict.get("section_code", "") or "").strip()
                    if section_code and section_code in query:
                        score += 0.25
                    if section_code and preferred_section_codes:
                        if section_code in preferred_section_codes:
                            score += 0.35
                        elif any(
                            section_code.startswith(f"{preferred}.") or preferred.startswith(f"{section_code}.")
                            for preferred in preferred_section_codes
                        ):
                            score += 0.2
                    section_title = str(meta_dict.get("section_title", "") or "").lower()
                    if section_title and any(term in section_title for term in query_terms):
                        score += 0.15

            scored_results.append({
                "document": doc,
                "metadata": meta,
                "score": min(score, 1.0),  # Cap at 1.0
                "distance": distance
            })
        
        # Sort by score (descending)
        scored_results.sort(key=lambda x: x["score"], reverse=True)
        
        # Take top n results
        top_results = scored_results[:n_results]
        
        return {
            "documents": [r["document"] for r in top_results],
            "metadatas": [r["metadata"] for r in top_results],
            "distances": [r["distance"] for r in top_results],
            "scores": [r["score"] for r in top_results]
        }
    
    def delete_collection(self, pdf_url: str):
        """Delete a collection (cleanup)"""
        try:
            collection_name = self.create_collection_name(pdf_url)
            self.client.delete_collection(collection_name)
            logger.info(f"Deleted collection {collection_name}")
        except Exception as e:
            logger.error(f"Error deleting collection: {e}")
    
    def collection_exists(self, pdf_url: str) -> bool:
        """Check if collection exists for a PDF"""
        try:
            collection_name = self.create_collection_name(pdf_url)
            collections = self.client.list_collections()
            return any(col.name == collection_name for col in collections)
        except:
            return False

    def collection_has_documents(self, pdf_url: str) -> bool:
        """Fast check for non-empty collection without listing all collections."""
        try:
            collection_name = self.create_collection_name(pdf_url)
            collection = self.get_or_create_collection(collection_name)
            return collection.count() > 0
        except Exception:
            return False

# Global vector DB instance
vector_db = VectorDB()

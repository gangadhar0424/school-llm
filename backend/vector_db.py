"""
ChromaDB vector database for storing and retrieving document embeddings
Used for RAG (Retrieval Augmented Generation) in Q&A feature
"""
import chromadb
import asyncio
from chromadb.config import Settings
from typing import List, Dict
import hashlib
import logging
from sentence_transformers import SentenceTransformer
from config import settings as app_settings
from ai.ollama_client import ollama_client

logger = logging.getLogger(__name__)

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
        # Use hash of URL to create valid collection name
        hash_object = hashlib.md5(pdf_url.encode())
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
    
    async def query_documents(self, pdf_url: str, query: str, n_results: int = 5) -> Dict:
        """Query vector database for relevant chunks"""
        try:
            collection_name = self.create_collection_name(pdf_url)
            collection = self.get_or_create_collection(collection_name)
            
            # Check if collection is empty
            if collection.count() == 0:
                logger.warning(f"Collection {collection_name} is empty")
                return {
                    "documents": [],
                    "distances": [],
                    "metadatas": []
                }
            
            # Generate query embedding
            query_embedding = (await self.get_embeddings([query]))[0]
            
            # Query collection
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(n_results, collection.count())
            )
            
            return {
                "documents": results["documents"][0] if results["documents"] else [],
                "distances": results["distances"][0] if results["distances"] else [],
                "metadatas": results["metadatas"][0] if results["metadatas"] else []
            }
            
        except Exception as e:
            logger.error(f"Error querying vector DB: {e}")
            raise
    
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

# Global vector DB instance
vector_db = VectorDB()

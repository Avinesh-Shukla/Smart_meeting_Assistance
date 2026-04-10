from typing import Any

from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec

from backend.config import get_settings


class PineconeService:
    def __init__(self) -> None:
        settings = get_settings()
        self._enabled = bool(settings.pinecone_api_key and settings.openai_api_key)
        self._index_name = settings.pinecone_index_name
        self._vector_dim = 1536
        self._openai = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self._pc = Pinecone(api_key=settings.pinecone_api_key) if settings.pinecone_api_key else None

        if self._enabled and self._pc:
            existing = [index["name"] for index in self._pc.list_indexes()]
            if self._index_name not in existing:
                self._pc.create_index(
                    name=self._index_name,
                    dimension=self._vector_dim,
                    metric="cosine",
                    spec=ServerlessSpec(cloud="aws", region="us-east-1"),
                )
            self._index = self._pc.Index(self._index_name)
        else:
            self._index = None

    def upsert_transcript(self, meeting_id: str, chunks: list[dict[str, Any]]) -> int:
        if not self._enabled or not self._index or not self._openai or not chunks:
            return 0

        vectors = []
        for i, chunk in enumerate(chunks):
            line = chunk.get("line", "")
            if not line:
                continue
            embedding = self._openai.embeddings.create(model="text-embedding-3-small", input=line)
            vectors.append(
                {
                    "id": f"{meeting_id}-{i}",
                    "values": embedding.data[0].embedding,
                    "metadata": {
                        "meeting_id": meeting_id,
                        "line": line,
                        "source": chunk.get("source", "unknown"),
                        "at": chunk.get("at", ""),
                    },
                }
            )

        if vectors:
            self._index.upsert(vectors=vectors, namespace=meeting_id)

        return len(vectors)

"""Study material and RAG chunk models."""

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from app.config import settings
from app.database import Base


class StudyMaterial(Base):
    """Uploaded learning material available to Tutor retrieval."""

    __tablename__ = "study_materials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(100), ForeignKey("users.username", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(20), nullable=False, index=True)
    content_type = Column(String(120), nullable=True)
    storage_path = Column(String(500), nullable=False)
    status = Column(String(30), nullable=False, default="ready")
    error = Column(Text, nullable=True)
    char_count = Column(Integer, default=0, nullable=False)
    chunk_count = Column(Integer, default=0, nullable=False)
    created_at = Column(String(50), nullable=False, index=True)
    updated_at = Column(String(50), nullable=False, index=True)

    chunks = relationship(
        "StudyMaterialChunk",
        back_populates="material",
        cascade="all, delete-orphan",
        order_by="StudyMaterialChunk.chunk_index",
    )


class StudyMaterialChunk(Base):
    """One searchable text chunk from a study material."""

    __tablename__ = "study_material_chunks"
    __table_args__ = (
        Index(
            "idx_study_material_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(Integer, ForeignKey("study_materials.id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    source_label = Column(String(255), nullable=False)
    embedding = Column(Vector(settings.RAG_VECTOR_DIM), nullable=False)
    created_at = Column(String(50), nullable=False, index=True)

    material = relationship("StudyMaterial", back_populates="chunks")

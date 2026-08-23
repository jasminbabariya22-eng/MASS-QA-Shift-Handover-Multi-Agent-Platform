from typing import List
import logfire
from langchain_text_splitters import RecursiveCharacterTextSplitter

def chunk_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> List[str]:
    """
    Splits document text into overlapping chunks using RecursiveCharacterTextSplitter.
    Preserves context continuity across diagram captions, table rows, and technical paragraphs.
    """
    with logfire.span("✂️ Text Chunking", text_length=len(text)):
        if not text or not text.strip():
            return []

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""]
        )

        chunks = splitter.split_text(text)
        valid_chunks = [c.strip() for c in chunks if c.strip()]
        logfire.info(f"✅ Generated {len(valid_chunks)} chunks (size={chunk_size}, overlap={chunk_overlap}).")
        return valid_chunks


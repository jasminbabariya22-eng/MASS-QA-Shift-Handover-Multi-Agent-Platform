import hashlib
import os


def compute_file_hash(file_path: str) -> str:
    """
    Computes a deterministic SHA-256 hash of a file for duplicate detection and idempotent ingestion.
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

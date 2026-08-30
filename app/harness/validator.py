import re
from typing import List, Dict, Any, Optional, Tuple
import logfire

from app.harness.contracts import HarnessValidationResult


class HarnessOutputValidator:
    """
    Output validation boundary for AI Harness.
    Enforces grounding, citation structure, engineering conflict reporting, and secret sanitization.
    """

    SECRET_PATTERNS = [
        # Database URIs
        (re.compile(r"postgres(?:ql)?://[^\s:@]+:[^\s:@]+@[^\s/]+/[^\s]+", re.IGNORECASE), "[REDACTED_DB_URI]"),
        # JWT Tokens
        (re.compile(r"eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+"), "[REDACTED_JWT_TOKEN]"),
        # Standard API Keys
        (re.compile(r"\b(?:sk|pk|api)_[A-Za-z0-9_-]{20,}\b"), "[REDACTED_API_KEY]"),
        # Google API Keys
        (re.compile(r"\bAIza[0-9A-Za-z-_]{35}\b"), "[REDACTED_API_KEY]"),
        # Internal IPv4
        (re.compile(r"\b(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})\b"), "[REDACTED_INTERNAL_IP]"),
    ]

    def validate(
        self,
        response_text: str,
        citations: List[Dict[str, Any]],
        query_type: str = "general",
        metadata: Optional[Dict[str, Any]] = None,
        is_error: bool = False
    ) -> HarnessValidationResult:
        """
        Validate agent response against quality, grounding, citation, and secret leakage rules.
        """
        errors: List[str] = []
        meta = metadata or {}

        # 1. Sanitize Secrets & Stack Traces
        sanitized_text, has_secret = self.sanitize_secrets(response_text)
        if has_secret:
            logfire.warning("[HarnessValidator] Potential sensitive credential or internal IP sanitized.")

        # 2. Citation Structure Validation
        citations_valid = True
        for cit in citations:
            if not cit.get("document_name"):
                citations_valid = False
                errors.append("Citation missing document_name.")
            if not cit.get("source_type"):
                citations_valid = False
                errors.append("Citation missing source_type.")

        # 3. Grounding Validation
        grounding_valid = True
        is_technical_query = query_type in ["technical_qa", "loop_summary", "signal_path", "document_lookup"]
        # If response claims to be grounded but has zero citations on technical queries
        if is_technical_query and not citations and not is_error:
            # Check if text contains factual assertions
            if len(sanitized_text) > 100 and "could not be found" not in sanitized_text.lower():
                grounding_valid = False
                errors.append("Technical query response lacks mandatory source document citations.")

        # 4. Engineering Conflict Validation
        conflicts_detected = False
        if meta.get("conflict_code") == "LOOP_CONFIGURATION_CONFLICT" or "Potential Engineering Inconsistency" in sanitized_text:
            conflicts_detected = True
            logfire.info(f"[HarnessValidator] Loop engineering conflict confirmed in output: {meta.get('conflict_code')}")

        is_valid = len(errors) == 0

        return HarnessValidationResult(
            is_valid=is_valid,
            grounding_valid=grounding_valid,
            citations_valid=citations_valid,
            conflicts_detected=conflicts_detected,
            secrets_sanitized=has_secret,
            errors=errors,
            sanitized_response=sanitized_text
        )

    def sanitize_secrets(self, text: Optional[str]) -> Tuple[str, bool]:
        """
        Mask any credentials, JWTs, DB URIs, and internal network addresses.
        """
        if not text:
            return "", False

        sanitized = text
        secret_found = False

        for pattern, replacement in self.SECRET_PATTERNS:
            if pattern.search(sanitized):
                secret_found = True
                sanitized = pattern.sub(replacement, sanitized)

        # Sanitize internal Python tracebacks if leaked
        if "Traceback (most recent call last):" in sanitized:
            secret_found = True
            sanitized = re.sub(
                r"Traceback \(most recent call last\):.*?(?=(?:\n[A-Z]|\Z))",
                "An internal operational error occurred. Details have been logged securely.",
                sanitized,
                flags=re.DOTALL
            )

        return sanitized, secret_found



# Global Validator Singleton
output_validator = HarnessOutputValidator()

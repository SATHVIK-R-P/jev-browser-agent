import re
from typing import Optional, Tuple
from backend.decision_engine.decision_models import RiskLevel, ActionType

HIGH_RISK_KEYWORDS = [
    "purchase", "buy", "order now", "pay", "payment", "checkout", "place order",
    "credit card", "card number", "cvv", "expir", "debit", "upi pin", "bank", "wire transfer",
    "delete account", "delete database", "drop table", "remove account", "destroy",
    "password", "new password", "current password", "reset password",
    "security settings", "2fa", "two-factor", "mfa", "api key", "secret", "private key"
]

MEDIUM_RISK_KEYWORDS = [
    "submit", "send message", "contact us", "post comment", "upload", "upload file",
    "save profile", "update profile", "edit profile", "apply", "subscribe", "newsletter",
    "sign in", "sign up", "register", "login", "create account"
]

SENSITIVE_PATTERNS = [
    (re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*(\S+)"), r"\1=********"),
    (re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b"), "****-****-****-****"),  # CC numbers
    (re.compile(r"(?i)(api[_-]?key|bearer|token)\s*[:=]\s*(\S+)"), r"\1=********"),
]

class RiskClassifier:
    """
    Classifies browser actions into LOW, MEDIUM, or HIGH risk categories,
    and sanitizes logs against sensitive credentials.
    """

    @staticmethod
    def classify(
        action_type: ActionType,
        target_text: Optional[str] = None,
        target_selector: Optional[str] = None,
        value: Optional[str] = None,
        description: Optional[str] = None
    ) -> Tuple[RiskLevel, str]:
        corpus = f"{target_text or ''} {target_selector or ''} {value or ''} {description or ''}".lower()

        # Check HIGH risk first
        for kw in HIGH_RISK_KEYWORDS:
            if kw in corpus:
                return (
                    RiskLevel.HIGH,
                    f"Contains high-risk security/financial keyword: '{kw}'."
                )

        # Check MEDIUM risk
        if action_type == ActionType.SUBMIT:
            return (
                RiskLevel.MEDIUM,
                "Form submission action with potential external side effects."
            )

        for kw in MEDIUM_RISK_KEYWORDS:
            if kw in corpus:
                return (
                    RiskLevel.MEDIUM,
                    f"Contains interactive side-effect keyword: '{kw}'."
                )

        # Default to LOW risk (navigation, inspection, scrolling, searching)
        return (
            RiskLevel.LOW,
            "Low-risk reading, navigation, or benign search interaction."
        )

    @staticmethod
    def sanitize(text: Optional[str]) -> str:
        """Sanitizes text by stripping sensitive tokens, passwords, and credentials."""
        if not text:
            return ""
        sanitized = text
        for pattern, replacement in SENSITIVE_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized

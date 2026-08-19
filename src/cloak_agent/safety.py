"""Navigation and human-approval policy for browser actions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import ipaddress
import sys
from typing import Callable
from urllib.parse import urlparse


class ApprovalMode(str, Enum):
    ASK = "ask"
    DENY = "deny"
    ALLOW = "allow"


class SafetyError(RuntimeError):
    """Raised when a requested browser operation violates policy."""


RISKY_ACTION_TERMS = (
    "buy now",
    "purchase",
    "checkout",
    "place order",
    "pay now",
    "transfer",
    "withdraw",
    "delete",
    "remove account",
    "close account",
    "send message",
    "send email",
    "publish",
    "post now",
    "confirm booking",
    "subscribe",
    "unsubscribe",
    "upload",
    "立即购买",
    "结账",
    "付款",
    "支付",
    "转账",
    "提现",
    "删除",
    "注销账户",
    "发送消息",
    "发送邮件",
    "发布",
    "确认预订",
    "订阅",
    "取消订阅",
    "上传",
)

SENSITIVE_INPUT_TYPES = frozenset({"password", "file"})
SENSITIVE_FIELD_TERMS = (
    "password",
    "passcode",
    "one-time",
    "otp",
    "verification code",
    "credit card",
    "card number",
    "cvv",
    "密码",
    "验证码",
    "信用卡",
    "银行卡",
)


@dataclass(slots=True)
class SafetyPolicy:
    allowed_domains: tuple[str, ...] = ()
    allow_private_network: bool = False
    approval_mode: ApprovalMode = ApprovalMode.ASK
    approval_callback: Callable[[str], bool] | None = None

    def validate_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise SafetyError("Only http:// and https:// URLs are allowed")
        if parsed.username or parsed.password:
            raise SafetyError("Credentials embedded in a URL are not allowed")
        hostname = (parsed.hostname or "").lower().rstrip(".")
        if not hostname:
            raise SafetyError("URL must include a hostname")

        if self.allowed_domains and not any(
            hostname == domain or hostname.endswith(f".{domain}")
            for domain in self.allowed_domains
        ):
            raise SafetyError(f"Domain is outside the allowlist: {hostname}")

        if not self.allow_private_network and self._is_private_host(hostname):
            raise SafetyError(f"Private or local network target is blocked: {hostname}")
        return url

    def authorize_click(self, label: str, href: str | None = None) -> None:
        details = " ".join(part for part in (label, href or "") if part).lower()
        if any(term in details for term in RISKY_ACTION_TERMS):
            self._require_approval(f"Click potentially consequential control: {label!r}")

    def authorize_input(self, label: str, input_type: str) -> None:
        details = f"{label} {input_type}".lower()
        if input_type.lower() in SENSITIVE_INPUT_TYPES or any(
            term in details for term in SENSITIVE_FIELD_TERMS
        ):
            self._require_approval(
                f"Enter data into a sensitive field: {label!r} ({input_type or 'text'})"
            )

    def _require_approval(self, message: str) -> None:
        if self.approval_mode is ApprovalMode.ALLOW:
            return
        if self.approval_mode is ApprovalMode.DENY:
            raise SafetyError(f"Approval denied by policy. {message}")
        callback = self.approval_callback or terminal_approval
        if not callback(message):
            raise SafetyError(f"User did not approve. {message}")

    @staticmethod
    def _is_private_host(hostname: str) -> bool:
        if hostname in {"localhost", "localhost.localdomain"}:
            return True
        if hostname.endswith((".local", ".internal", ".localhost")):
            return True
        try:
            address = ipaddress.ip_address(hostname.strip("[]"))
        except ValueError:
            return False
        return not address.is_global


def terminal_approval(message: str) -> bool:
    if not sys.stdin.isatty():
        return False
    answer = input(f"\n[approval required] {message}\nApprove? [y/N] ").strip().lower()
    return answer in {"y", "yes"}

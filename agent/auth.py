"""HMAC-SHA256 authentication and replay protection for Sandbox Execution Agent."""

import hashlib
import hmac
import logging
import threading
import time
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Maximum permissible clock skew between Control Plane and Sandbox Agent (5 minutes)
MAX_TIMESTAMP_DRIFT_SECONDS: float = 300.0

# HTTP Headers used for authenticated RPC communication
HEADER_SIGNATURE = "X-ReleaseProof-Signature"
HEADER_TIMESTAMP = "X-ReleaseProof-Timestamp"
HEADER_NONCE = "X-ReleaseProof-Nonce"


class AuthenticationError(Exception):
    """Raised when request signature, timestamp, or nonce verification fails."""
    pass


class ReplayProtectionTracker:
    """Thread-safe nonce tracker enforcing one-time use per validity window."""

    def __init__(self, ttl_seconds: float = MAX_TIMESTAMP_DRIFT_SECONDS):
        self.ttl_seconds = ttl_seconds
        self._seen_nonces: Dict[str, float] = {}
        self._lock = threading.Lock()

    def is_nonce_valid_and_record(self, nonce: str, timestamp: float) -> bool:
        """Atomically check if nonce is unused and within validity window; record it if valid."""
        with self._lock:
            now = time.time()
            self._prune_expired(now)

            if not nonce or len(nonce) < 8 or len(nonce) > 128:
                return False

            if nonce in self._seen_nonces:
                return False

            self._seen_nonces[nonce] = now
            return True

    def _prune_expired(self, current_time: float) -> None:
        """Evict nonces whose timestamps have passed the validity window. Must be called under lock."""
        cutoff = current_time - self.ttl_seconds
        expired_keys = [k for k, t in self._seen_nonces.items() if t < cutoff]
        for k in expired_keys:
            del self._seen_nonces[k]

    def clear(self) -> None:
        """Clear all tracked nonces (primarily for testing)."""
        with self._lock:
            self._seen_nonces.clear()


# Global tracker instance for the agent process
_replay_tracker = ReplayProtectionTracker()


def compute_body_sha256(body: bytes) -> str:
    """Compute the hexadecimal SHA-256 digest of a request payload."""
    return hashlib.sha256(body).hexdigest()


def build_canonical_string(
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    body_sha256: str,
) -> str:
    """Construct deterministic multi-line string for HMAC signing."""
    clean_method = method.strip().upper()
    clean_path = path.strip()
    return f"{clean_method}\n{clean_path}\n{timestamp}\n{nonce}\n{body_sha256}"


def sign_request(
    secret: str,
    method: str,
    path: str,
    body: bytes,
    timestamp: Optional[str] = None,
    nonce: Optional[str] = None,
) -> Tuple[Dict[str, str], str]:
    """Generate signed headers for an outgoing HTTP request from Control Plane to Agent."""
    if not secret:
        raise ValueError("Cannot sign request: shared secret is empty or missing")

    ts = timestamp if timestamp is not None else str(int(time.time()))
    import uuid
    n = nonce if nonce is not None else uuid.uuid4().hex

    body_hash = compute_body_sha256(body)
    canonical = build_canonical_string(method=method, path=path, timestamp=ts, nonce=n, body_sha256=body_hash)
    signature = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()

    headers = {
        HEADER_SIGNATURE: signature,
        HEADER_TIMESTAMP: ts,
        HEADER_NONCE: n,
    }
    return headers, signature


def verify_request_signature(
    secret: str,
    method: str,
    path: str,
    body: bytes,
    signature: Optional[str],
    timestamp_str: Optional[str],
    nonce: Optional[str],
    tracker: Optional[ReplayProtectionTracker] = None,
) -> bool:
    """Validate incoming request signature using constant-time comparison, clock skew, and replay protection."""
    if not secret:
        logger.error("Authentication failed: server shared secret is not configured")
        raise AuthenticationError("Server worker secret is not configured")

    if not signature or not timestamp_str or not nonce:
        raise AuthenticationError("Missing required authentication headers (signature, timestamp, or nonce)")

    # 1. Enforce timestamp validity and clock skew
    try:
        req_ts = float(timestamp_str)
    except ValueError:
        raise AuthenticationError("Malformed timestamp header")

    now = time.time()
    drift = abs(now - req_ts)
    if drift > MAX_TIMESTAMP_DRIFT_SECONDS:
        raise AuthenticationError(
            f"Request timestamp expired (drift of {drift:.1f}s exceeds maximum allowed {MAX_TIMESTAMP_DRIFT_SECONDS}s)"
        )

    # 2. Enforce nonce replay protection
    active_tracker = tracker or _replay_tracker
    if not active_tracker.is_nonce_valid_and_record(nonce, req_ts):
        raise AuthenticationError("Replay attack detected or invalid nonce")

    # 3. Compute expected signature and perform constant-time comparison
    body_hash = compute_body_sha256(body)
    canonical = build_canonical_string(method=method, path=path, timestamp=timestamp_str, nonce=nonce, body_sha256=body_hash)
    expected_sig = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected_sig, signature):
        logger.warning("HMAC signature mismatch on path '%s'", path)
        raise AuthenticationError("Invalid request signature")

    return True

"""Unit tests for Sandbox Execution Agent HMAC-SHA256 authentication."""

import time
import pytest

from agent.auth import (
    AuthenticationError,
    ReplayProtectionTracker,
    build_canonical_string,
    compute_body_sha256,
    sign_request,
    verify_request_signature,
)

SECRET = "super-secret-test-key-12345"


def test_hmac_sign_and_verify_success():
    """Verify standard signing and verification flow succeeds with valid secret and body."""
    tracker = ReplayProtectionTracker()
    body = b'{"hello": "world"}'
    headers, signature = sign_request(secret=SECRET, method="POST", path="/agent/jobs/submit", body=body)

    assert "X-ReleaseProof-Signature" in headers
    assert "X-ReleaseProof-Timestamp" in headers
    assert "X-ReleaseProof-Nonce" in headers

    is_valid = verify_request_signature(
        secret=SECRET,
        method="POST",
        path="/agent/jobs/submit",
        body=body,
        signature=headers["X-ReleaseProof-Signature"],
        timestamp_str=headers["X-ReleaseProof-Timestamp"],
        nonce=headers["X-ReleaseProof-Nonce"],
        tracker=tracker,
    )
    assert is_valid is True


def test_hmac_tampered_body_rejected():
    """Verify modifying body after signing triggers signature mismatch."""
    tracker = ReplayProtectionTracker()
    body = b'{"hello": "world"}'
    headers, _ = sign_request(secret=SECRET, method="POST", path="/agent/jobs/submit", body=body)

    tampered_body = b'{"hello": "world_tampered"}'
    with pytest.raises(AuthenticationError, match="Invalid request signature"):
        verify_request_signature(
            secret=SECRET,
            method="POST",
            path="/agent/jobs/submit",
            body=tampered_body,
            signature=headers["X-ReleaseProof-Signature"],
            timestamp_str=headers["X-ReleaseProof-Timestamp"],
            nonce=headers["X-ReleaseProof-Nonce"],
            tracker=tracker,
        )


def test_hmac_tampered_path_rejected():
    """Verify modifying request path after signing triggers signature mismatch."""
    tracker = ReplayProtectionTracker()
    body = b'{"test": 1}'
    headers, _ = sign_request(secret=SECRET, method="POST", path="/agent/jobs/submit", body=body)

    with pytest.raises(AuthenticationError, match="Invalid request signature"):
        verify_request_signature(
            secret=SECRET,
            method="POST",
            path="/agent/jobs/abort",  # altered path
            body=body,
            signature=headers["X-ReleaseProof-Signature"],
            timestamp_str=headers["X-ReleaseProof-Timestamp"],
            nonce=headers["X-ReleaseProof-Nonce"],
            tracker=tracker,
        )


def test_hmac_tampered_method_rejected():
    """Verify modifying request method after signing triggers signature mismatch."""
    tracker = ReplayProtectionTracker()
    body = b'{"test": 1}'
    headers, _ = sign_request(secret=SECRET, method="POST", path="/agent/jobs/submit", body=body)

    with pytest.raises(AuthenticationError, match="Invalid request signature"):
        verify_request_signature(
            secret=SECRET,
            method="GET",  # altered method
            path="/agent/jobs/submit",
            body=body,
            signature=headers["X-ReleaseProof-Signature"],
            timestamp_str=headers["X-ReleaseProof-Timestamp"],
            nonce=headers["X-ReleaseProof-Nonce"],
            tracker=tracker,
        )


def test_hmac_expired_timestamp_rejected():
    """Verify timestamps older than 300s are rejected."""
    tracker = ReplayProtectionTracker()
    body = b"{}"
    expired_ts = str(int(time.time()) - 400)
    headers, _ = sign_request(secret=SECRET, method="POST", path="/agent/jobs/submit", body=body, timestamp=expired_ts)

    with pytest.raises(AuthenticationError, match="Request timestamp expired"):
        verify_request_signature(
            secret=SECRET,
            method="POST",
            path="/agent/jobs/submit",
            body=body,
            signature=headers["X-ReleaseProof-Signature"],
            timestamp_str=headers["X-ReleaseProof-Timestamp"],
            nonce=headers["X-ReleaseProof-Nonce"],
            tracker=tracker,
        )


def test_hmac_future_timestamp_skew_rejected():
    """Verify timestamps far in the future (> 300s) are rejected."""
    tracker = ReplayProtectionTracker()
    body = b"{}"
    future_ts = str(int(time.time()) + 400)
    headers, _ = sign_request(secret=SECRET, method="POST", path="/agent/jobs/submit", body=body, timestamp=future_ts)

    with pytest.raises(AuthenticationError, match="Request timestamp expired"):
        verify_request_signature(
            secret=SECRET,
            method="POST",
            path="/agent/jobs/submit",
            body=body,
            signature=headers["X-ReleaseProof-Signature"],
            timestamp_str=headers["X-ReleaseProof-Timestamp"],
            nonce=headers["X-ReleaseProof-Nonce"],
            tracker=tracker,
        )


def test_hmac_replay_attack_rejected():
    """Verify re-using the same nonce within validity window is blocked."""
    tracker = ReplayProtectionTracker()
    body = b'{"command": "run"}'
    headers, _ = sign_request(secret=SECRET, method="POST", path="/agent/jobs/submit", body=body)

    # First request: OK
    assert verify_request_signature(
        secret=SECRET,
        method="POST",
        path="/agent/jobs/submit",
        body=body,
        signature=headers["X-ReleaseProof-Signature"],
        timestamp_str=headers["X-ReleaseProof-Timestamp"],
        nonce=headers["X-ReleaseProof-Nonce"],
        tracker=tracker,
    ) is True

    # Replayed identical request with same nonce: REJECTED
    with pytest.raises(AuthenticationError, match="Replay attack detected"):
        verify_request_signature(
            secret=SECRET,
            method="POST",
            path="/agent/jobs/submit",
            body=body,
            signature=headers["X-ReleaseProof-Signature"],
            timestamp_str=headers["X-ReleaseProof-Timestamp"],
            nonce=headers["X-ReleaseProof-Nonce"],
            tracker=tracker,
        )


def test_hmac_missing_headers_rejected():
    """Verify missing signature or timestamp headers are rejected."""
    with pytest.raises(AuthenticationError, match="Missing required authentication headers"):
        verify_request_signature(
            secret=SECRET,
            method="POST",
            path="/agent/jobs/submit",
            body=b"{}",
            signature=None,
            timestamp_str="12345",
            nonce="nonce-1",
        )


def test_hmac_concurrent_replay_protection():
    """Verify that multiple concurrent threads attempting to use the same nonce have exactly one winner."""
    import concurrent.futures
    tracker = ReplayProtectionTracker()
    body = b'{"concurrent": "test"}'
    headers, _ = sign_request(secret=SECRET, method="POST", path="/agent/jobs/submit", body=body)

    def attempt_verify():
        try:
            return verify_request_signature(
                secret=SECRET,
                method="POST",
                path="/agent/jobs/submit",
                body=body,
                signature=headers["X-ReleaseProof-Signature"],
                timestamp_str=headers["X-ReleaseProof-Timestamp"],
                nonce=headers["X-ReleaseProof-Nonce"],
                tracker=tracker,
            )
        except AuthenticationError:
            return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(attempt_verify) for _ in range(20)]
        results = [f.result() for f in futures]

    assert results.count(True) == 1
    assert results.count(False) == 19


def test_hmac_nonce_persistence_throughout_validity_window():
    """Verify that recorded nonces persist in tracking state and are not prematurely evicted."""
    tracker = ReplayProtectionTracker(ttl_seconds=300.0)
    nonce = "persistent-nonce-test-12345678"
    now = time.time()

    assert tracker.is_nonce_valid_and_record(nonce=nonce, timestamp=now) is True

    # 10s later (well within 300s window)
    tracker._prune_expired(current_time=now + 10.0)
    assert nonce in tracker._seen_nonces
    assert tracker.is_nonce_valid_and_record(nonce=nonce, timestamp=now + 10.0) is False

    # 299s later (right at boundary)
    tracker._prune_expired(current_time=now + 299.0)
    assert nonce in tracker._seen_nonces
    assert tracker.is_nonce_valid_and_record(nonce=nonce, timestamp=now + 299.0) is False

    # 301s later (safely expired)
    tracker._prune_expired(current_time=now + 301.0)
    assert nonce not in tracker._seen_nonces

"""Configuration settings for Sandbox Execution Agent.

DEPLOYMENT SECURITY MODEL:
The Sandbox Execution Agent must NEVER be exposed directly to the public internet
or bound to 0.0.0.0 without network-level protections.

Recommended production deployment topologies on Vultr Compute:
1. Private VPC / Private Network: Control Plane and Agent communicate over a private
   VPC IP (e.g. 10.x.x.x) with firewall rules restricting inbound port 8001 strictly
   to the Control Plane IP.
2. Reverse Proxy with TLS termination (e.g., Caddy, Nginx) on the worker host,
   enforcing TLS/HTTPS externally with Uvicorn bound to 127.0.0.1 or a UNIX domain socket.
3. Direct TLS in Uvicorn:
   uvicorn agent.main:agent_app --host 127.0.0.1 --port 8001 \\
       --ssl-keyfile /path/to/key.pem --ssl-certfile /path/to/cert.pem

In all configurations, request authentication is enforced via HMAC-SHA256 with
timestamp expiration and replay protection.
"""

import os
from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    """Configuration for the isolated sandbox worker agent."""

    model_config = SettingsConfigDict(
        env_file=(".env", "agent/.env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    AGENT_HOST: str = Field(
        default="127.0.0.1",
        description="Agent bind host (loopback or private VPC IP; never 0.0.0.0 without firewall)",
    )
    AGENT_PORT: int = Field(default=8001, description="Agent bind port")
    AGENT_USE_TLS: bool = Field(
        default=False,
        description="Whether TLS is terminated directly by the agent uvicorn server",
    )
    AGENT_TLS_CERT_PATH: Optional[str] = Field(
        default=None,
        description="Path to TLS certificate bundle file when AGENT_USE_TLS=true",
    )
    AGENT_TLS_KEY_PATH: Optional[str] = Field(
        default=None,
        description="Path to TLS private key file when AGENT_USE_TLS=true",
    )
    WORKER_SHARED_SECRET: Optional[str] = Field(
        default=None, description="Pre-shared HMAC key shared between Control Plane and Agent"
    )

    # Docker Engine Settings
    DOCKER_SOCKET_PATH: str = Field(
        default="/var/run/docker.sock",
        description="Path to local Docker UNIX domain socket on the worker VM",
    )
    SANDBOX_BASE_IMAGE: str = Field(
        default="mcp-releaseproof-runner:latest",
        description="Pre-warmed immutable base container image",
    )
    SANDBOX_CONTAINER_USER: str = Field(
        default="10001:10001",
        description="Non-root UID:GID enforced in sandbox container",
    )
    SANDBOX_WORKSPACE_ROOT: str = Field(
        default="/tmp/releaseproof-workspaces",
        description="Host directory under which ephemeral job workspaces are provisioned",
    )

    # Pre-warmed dependency allowlist (pinned in agent/requirements-sandbox.txt)
    PREWARMED_PACKAGES: List[str] = Field(
        default_factory=lambda: [
            "mcp==1.2.1",
            "fastmcp==0.4.1",
            "pydantic==2.10.6",
            "pytest==8.3.4",
            "pytest-asyncio==0.25.3",
            "httpx==0.28.1",
            "anyio==4.8.0",
            "typing_extensions==4.12.2",
        ],
        description="Packages pre-warmed in the immutable base image",
    )

    MAX_JOB_TIMEOUT_SECONDS: int = Field(
        default=300, description="Absolute ceiling on job execution duration"
    )
    MAX_OUTPUT_BYTES: int = Field(
        default=65_536, description="Maximum captured stdout/stderr size in bytes (64KB)"
    )


_agent_settings: Optional[AgentSettings] = None


def get_agent_settings() -> AgentSettings:
    global _agent_settings
    if _agent_settings is None:
        _agent_settings = AgentSettings()
    return _agent_settings

# Development and Local Setup

## Prerequisites

Do not assume these tools are installed. Check versions and ask the developer to install missing tools.

Required:
- Git.
- Python version supported by the chosen MCP SDK.
- Node.js version supported by the selected Vite release.
- Docker Engine and Compose plugin.
- PostgreSQL.
- Redis.
- Access to Vultr Serverless Inference.

## Environment setup

1. Clone the repository.
2. Copy `.env.example` to `.env`.
3. Obtain the Vultr inference key from the Vultr console.
4. Select a current model ID from the Vultr model catalogue.
5. Configure actual database and Redis URLs.
6. Generate a worker shared secret.
7. Confirm `.env` is ignored by Git.

If any required values are unknown, stop and ask the developer. Do not invent them.

## Local development

Frontend:
- Install dependencies using the lockfile.
- Start Vite development server.
- Configure API base URL using a non-secret public frontend setting.

Backend:
- Create Python virtual environment.
- Install pinned dependencies.
- Apply database migrations.
- Start FastAPI.

Worker:
- Start only after Docker and worker configuration are verified.
- The worker must not receive inference credentials.
- For local development, keep untrusted execution isolated and never run submitted code directly on the host.

## Configuration checks

At startup, validate:
- Required environment variables exist.
- URLs parse correctly.
- Inference base URL is expected.
- Model ID is configured.
- Database is reachable.
- Redis is reachable.
- Worker secret meets minimum length.
- Artifact directory is writable.
- Docker is reachable only by trusted worker service.

Do not print secret values during validation.

## Dependency management

- Pin dependencies.
- Commit lockfiles.
- Avoid unnecessary packages.
- Review packages that execute install scripts.
- Keep frontend and backend dependencies separate.

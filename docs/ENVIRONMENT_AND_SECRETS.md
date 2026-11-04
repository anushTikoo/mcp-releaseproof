# Environment Variables and Secrets

## General rules

- `.env` is local and must never be committed.
- `.env.example` contains placeholders only.
- Never put secrets in frontend variables.
- Vite variables prefixed with `VITE_` are embedded in browser code and are public.
- The AI IDE must ask the developer to populate missing values.
- Do not generate fake production secrets or silently use insecure defaults.
- Do not log secret values.

## Control-plane `.env.example`

```dotenv
# Application
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
PUBLIC_BASE_URL=REPLACE_WITH_ACTUAL_CONTROL_PLANE_URL
CORS_ORIGINS=REPLACE_WITH_ACTUAL_FRONTEND_ORIGIN

# Vultr Serverless Inference
VULTR_INFERENCE_BASE_URL=https://api.vultrinference.com/v1
VULTR_INFERENCE_API_KEY=REPLACE_WITH_KEY_CREATED_IN_VULTR_CONSOLE
VULTR_INFERENCE_MODEL=REPLACE_WITH_MODEL_ID_FROM_CURRENT_VULTR_CATALOG

# Database
DATABASE_URL=postgresql+psycopg://REPLACE_USER:REPLACE_PASSWORD@REPLACE_HOST:5432/REPLACE_DATABASE

# Redis
REDIS_URL=redis://REPLACE_HOST:6379/0

# Worker authentication
WORKER_SHARED_SECRET=REPLACE_WITH_LOCALLY_GENERATED_RANDOM_SECRET

# Artifact storage
ARTIFACT_STORAGE_MODE=local
ARTIFACT_ROOT=./data/artifacts

# Limits
MAX_REPOSITORY_SIZE_MB=200
MAX_SCAN_DURATION_SECONDS=600
MAX_SCENARIOS_PER_SCAN=10
MAX_TOOL_CALLS_PER_SCAN=50
MAX_ARTIFACT_SIZE_MB=50
```

The values above are placeholders. Do not use them literally. The AI IDE must not assume a database host, Redis host, public URL, model ID, or key.

## Worker `.env.example`

```dotenv
WORKER_ID=REPLACE_WITH_UNIQUE_WORKER_IDENTIFIER
CONTROL_PLANE_URL=REPLACE_WITH_ACTUAL_CONTROL_PLANE_URL
WORKER_SHARED_SECRET=REPLACE_WITH_SAME_SECRET_AS_CONTROL_PLANE
WORKER_WORK_ROOT=/var/lib/releaseproof/work
DOCKER_NETWORK_POLICY=REPLACE_WITH_VERIFIED_NETWORK_POLICY_NAME
MAX_CONCURRENT_JOBS=1
MAX_JOB_DURATION_SECONDS=600
```

The worker does not receive:
- `VULTR_INFERENCE_API_KEY`
- `DATABASE_URL`
- `REDIS_URL`
- GitHub token
- Control-plane application secrets

## Optional Object Storage variables

Only add if Object Storage is configured:

```dotenv
ARTIFACT_STORAGE_MODE=s3
S3_ENDPOINT_URL=REPLACE_WITH_ACTUAL_VULTR_OBJECT_STORAGE_ENDPOINT
S3_REGION=REPLACE_WITH_ACTUAL_REGION
S3_BUCKET=REPLACE_WITH_ACTUAL_BUCKET
S3_ACCESS_KEY_ID=REPLACE_WITH_ACCESS_KEY
S3_SECRET_ACCESS_KEY=REPLACE_WITH_SECRET_KEY
```

## Optional Vultr API variables

Not required for manual VM provisioning. If a future feature uses the Vultr API, add a separate secret only after the user explicitly configures the API token:

```dotenv
VULTR_API_KEY=REPLACE_ONLY_IF_VULTR_API_AUTOMATION_IS_IMPLEMENTED
```

Never confuse `VULTR_API_KEY` with `VULTR_INFERENCE_API_KEY`.

## Local setup instructions

1. Copy `.env.example` to `.env`.
2. Obtain the inference API key from the Vultr console.
3. Select a model from the current Vultr model catalogue.
4. Obtain actual database and Redis connection details.
5. Generate a strong worker shared secret locally.
6. Enter actual service URLs and origins.
7. Verify `.env` is in `.gitignore`.
8. Start services only after required values are present.

If any required value is unknown, ask the developer to supply it. Do not guess.

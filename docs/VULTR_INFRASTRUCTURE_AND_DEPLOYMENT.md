# Vultr Infrastructure and Deployment Guide

## Important: manual setup is required

Do not assume any Vultr resource already exists. The developer must create or verify the account resources in the Vultr console. Do not invent VM IDs, IP addresses, regions, firewall IDs, VPC IDs, API keys, hostnames, or SSH keys.

The AI IDE must ask the developer to perform each manual console action and provide the resulting non-secret configuration values before generating deployment configuration that depends on them.

## Recommended topology

### Control-plane VM
Hosts:
- Reverse proxy and HTTPS.
- React frontend.
- FastAPI backend.
- PostgreSQL.
- Redis.
- Orchestrator and report generation.

### Sandbox-worker VM
Hosts:
- Worker agent.
- Docker Engine.
- Host-side monitoring.
- Runtime egress enforcement.
- Temporary source/build/execution storage.

The two-VM layout creates a clearer separation between the control plane and the machine executing untrusted code. A one-VM fallback is possible for a constrained demonstration but weakens isolation and must be documented.

Do not decide VM size, region, OS image, disk, or network configuration without checking current Vultr offerings, credits, project requirements, and user confirmation.

## Manual setup checklist

### A. Account and credits
1. Sign in to the Vultr account.
2. Confirm account verification and billing configuration.
3. Confirm hackathon credits have been applied, if eligible.
4. Check current credit balance and resource pricing before creating instances.
5. Do not create paid resources without user confirmation.

### B. Serverless Inference
1. Open the Vultr Serverless Inference documentation and console.
2. Confirm the service is available to the account.
3. Create an inference API key.
4. Select a model from the current model catalogue.
5. Place the key in the control-plane `.env` as `VULTR_INFERENCE_API_KEY`.
6. Place the selected model ID in `VULTR_INFERENCE_MODEL`.
7. Never place the key in frontend code, Git, or the sandbox worker.

Docs:
- https://api.vultrinference.com/docs
- https://api.vultrinference.com/docs/get-started/quickstart
- https://api.vultrinference.com/docs/get-started/authentication
- https://api.vultrinference.com/docs/models
- https://api.vultrinference.com/docs/reference

### C. Create the control-plane VM
In the Vultr console:
1. Create a Cloud Compute instance.
2. Select an OS supported by the project dependencies.
3. Select region and plan based on latency, cost and capacity.
4. Add an SSH key.
5. Configure firewall rules.
6. Record public IP, OS, username, region and instance identifier.
7. Verify SSH access.

Do not assume Ubuntu version, IP address, username, or plan.

Docs:
- https://docs.vultr.com/products/compute/instances/cloud-compute
- https://www.vultr.com/api/

### D. Create the sandbox-worker VM
Repeat the instance process for a separate worker.
- Use a separate SSH key or carefully controlled access.
- Do not expose Docker TCP API.
- Restrict administrative ingress.
- Configure worker-to-control-plane connectivity.
- Record its actual IP and OS.
- Verify disk and memory capacity for Docker builds.

### E. Firewall and network
Configure the Vultr Firewall or host firewall based on the actual topology.

At minimum:
- Public HTTPS ingress to control plane only.
- SSH ingress restricted to the developer's known IP where practical.
- Worker control-plane communication restricted to the actual control-plane endpoint.
- No public Docker API.
- No public worker telemetry endpoint.
- Target runtime egress denied by host/network policy.

Do not invent IP allowlists. Ask the user for actual addresses and confirm rules before applying them.

Vultr Compute networking documentation:
https://docs.vultr.com/products/compute/instances/cloud-compute

### F. Install operating system dependencies
The AI IDE must first detect the OS and package manager. Do not blindly run Ubuntu commands on an unknown distribution.

Likely requirements:
- Docker Engine and Compose plugin.
- Python version compatible with selected MCP SDK.
- Node.js version compatible with current Vite.
- Git.
- Reverse proxy.
- PostgreSQL and Redis, either local or managed.
- Host monitoring and firewall tools.

Use official installation instructions for the detected OS. Verify service status after installation.

### G. DNS and HTTPS
If using a domain:
1. Ask the developer for the domain name and DNS provider.
2. Ask them to create the correct DNS record pointing to the control-plane IP.
3. Verify DNS propagation.
4. Configure HTTPS.
5. Do not invent or assume the domain.

A raw IP deployment may be used for initial connectivity testing, but the final public product URL should use a properly configured HTTPS hostname where possible.

### H. Worker registration
1. Generate a strong random `WORKER_SHARED_SECRET` locally.
2. Put the same value in the control-plane and worker environment files.
3. Do not commit either file.
4. Configure the worker's control-plane base URL using the actual deployment URL.
5. Verify authenticated worker heartbeat and job claim.
6. Never pass this secret into target containers.

## Vultr API

Vultr API documentation:
https://www.vultr.com/api/

The MVP does not require programmatic VM provisioning. Manual console provisioning is acceptable. If later automating resource creation, first ask the user to create a Vultr API token with only the required permissions and store it as a secret. Do not assume an API token exists.

## Object Storage (optional)

Object Storage is not required for the first working version. Local persistent storage can hold artifacts initially. If adding Object Storage:
- Create a bucket manually.
- Create S3-compatible access credentials.
- Record the actual endpoint and region.
- Keep access and secret keys server-side.
- Configure private bucket access.
- Verify SDK compatibility and lifecycle support.

Docs:
- https://docs.vultr.com/products/storage/object-storage
- https://docs.vultr.com/products/storage/object-storage/s3-compatibility-matrix
- https://docs.vultr.com/platform/security-best-practices/vultr-object-storage

## Deployment verification

Before declaring deployment complete, verify:
- Control-plane public endpoint responds.
- HTTPS works if configured.
- Frontend can reach API.
- API can reach PostgreSQL and Redis.
- API can reach Vultr Serverless Inference.
- Worker can authenticate to API.
- Worker can create and destroy a test container.
- Target container cannot reach external network during runtime.
- Target container cannot reach control-plane private services.
- Worker can upload events.
- Artifacts persist after process restart.
- No secrets appear in logs or frontend bundles.

## Cost discipline

Before provisioning:
- Check current instance pricing and estimated monthly cost.
- Check storage and bandwidth pricing.
- Check remaining hackathon credits.
- Ask for confirmation before creating or resizing paid resources.
- Stop or destroy unused instances after the event if no longer needed.

**Docker Deployment Guide**

follow the steps to deploy the application services in a containerized environment. The setup supports both **Linux/ARM64** environments (for our oracle vm) and **x86_64** environments (Intel/AMD local computers).

---

**Prerequisites**
Ensure your target deployment host has the following installed:
* **Docker Engine** (version 20.10+)
* **Docker Compose V2** (usually included with Docker Desktop, or installed as `docker-compose-plugin`)

---

**Step 1: Create Global Environment Configuration**
Create a `.env` file in the **root** of the project directory (where your docker-compose files reside) to supply secrets to the container orchestration layer:

```env
# Root .env configuration
OPENAI_API_KEY="your-openai-api-key"
MONGO_URI="mongodb+srv://..."
DIGIKEY_CLIENT_ID="your-digikey-client-id"
DIGIKEY_CLIENT_SECRET="your-digikey-client-secret"

# Docker registry publishing variables (only needed for building/pushing)
DOCKERHUB_USERNAME="yourusername"
TARGET_PLATFORM="linux/arm64"
```

---

**Step 2: How the Docker Architecture is Set Up**

**Multi-Container Networking**
A custom bridge network named `hpe-network` is established. All cross-service HTTP requests communicate via DNS aliases of the service containers (e.g., `http://hpe-database:8081` or `http://hpe-extractor:8085`) rather than loopback IP (`127.0.0.1`).

**Shared File Storage (Upload Volume)**
A named docker volume `shared-datasheets` is defined and mounted at `/app/datasheets` in both:
* `main-app` (where PDFs are uploaded and saved)
* `pdf_processor` (where PDFs are read for parsing, layout analysis, and rendering)

This ensures that even without a shared host filesystem, the isolated containers share a synchronized storage volume for PDF datasheets.

---

**Option A: Run locally by Pulling from Docker Hub (Production/No Source Code Needed)**
If you are running the system on a remote host or local system and want to **pull the pre-built images directly from Docker Hub** instead of building locally, use the production compose file:

```bash
# Pull the latest pre-built images from raihan/ namespace
docker compose -f docker-compose.prod.yml pull

# Run the stack in detached mode
docker compose -f docker-compose.prod.yml up -d
```
---

**Option B: Build and Run the Services Locally from Source**
The Dockerfiles and local Compose configurations are **architecture-agnostic**. Docker will automatically compile and run native binaries matching the host's platform.

**Case A: Running Natively (x86 locally OR ARM64 VM locally)**
If you are building and running on the **same** machine, simply run:
```bash
# Build native images
docker compose build

# Start all containers in detached mode
docker compose up -d
```

### Case B: Cross-Building Locally (e.g. Building on x86 to Deploy on ARM64 VM)
If you are on your local x86 computer but want to build images to export/deploy onto your ARM64 VM, run:
```bash
# Force build targeting ARM64 architecture
DOCKER_DEFAULT_PLATFORM=linux/arm64 docker compose build
```
---

**Step 4: Publish to Docker Hub (and clean up local files)**
To compile the images for a target platform (e.g., `linux/arm64`), publish them to Docker Hub, and then clean up all local copies to save disk space, follow these steps:

**1. Configure variables in root `.env`**
Specify your target configuration inside the root `.env` file:
* Set `DOCKERHUB_USERNAME` to your Docker Hub username.
* Set `TARGET_PLATFORM` to your target CPU architecture (e.g., `linux/arm64` or `linux/amd64`).

**2. Log in, Build, Push, and Clean Up**
Run this chained command from the project root:
```bash
# Login to Docker Hub
docker login

# Build, Push, and clean up local images
docker compose -f docker-compose.push.yml build && docker compose -f docker-compose.push.yml push && docker compose -f docker-compose.push.yml down --rmi all
```

---

**Step 5: Verify the Deployment**
Check the running status of the containers:
```bash
docker compose ps
```

You should see 5 running containers:
* `hpe-main-app` (Port 8000)
* `hpe-extractor` (Port 8085)
* `hpe-pdf-processor` (Port 8084)
* `hpe-database` (Port 8081)
* `hpe-llm` (Port 8086)

**Checking Logs**
To monitor live logs for all services:
```bash
docker compose logs -f
```
Or for a specific service:
```bash
docker compose logs -f main-app
```

---

**Step 6: Stop or Tear Down**
To stop the services without deleting data:
```bash
docker compose down
```
To stop the services and completely purge the network and volume mounts:
```bash
docker compose down -v
```

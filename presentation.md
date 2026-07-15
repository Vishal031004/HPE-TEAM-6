# 8-Minute Presentation: Containerized Microservices Deployment Strategy
**Project:** HPE TEAM 6 — Parametric Extraction & Verification Platform
**Topic:** Infrastructure Orchestration, Multi-Platform Building, and Secure Deployment

---

## Slide 1: Presentation Overview & Objectives
### ⏱️ Time: 0:00 - 0:45 (45 Seconds)

```
========================================================================
|                   DEPLOYING HPE TEAM 6 AT SCALE                      |
|       Containerized Microservices & Multi-Platform Orchestration     |
|                                                                      |
|  Presenter: [Your Name]                                              |
|  Duration: 8 Minutes                                                 |
========================================================================
```

### 📝 Slide Content
* **Objective:** Establish a highly secure, scalable, and cross-platform containerized environment.
* **Target Platforms:** 
  * *Local Development:* Native x86_64 or Apple Silicon architectures.
  * *Production/Staging:* Oracle VM cloud instances running Linux/ARM64.
* **Core Mechanisms:**
  * Multi-container composition via Docker Compose.
  * Architecture-agnostic local/cross-builds.
  * Custom isolated networking & persistent shared volumes.

---

### 🗣️ Presenter Speaking Notes
> "Good morning/afternoon everyone. Today, I'm going to take you through the deployment and infrastructure orchestration strategy for the HPE Team 6 Parametric Extraction project. Over the next eight minutes, we'll examine how we transformed a complex multi-stage python application into a production-ready, decoupled, and secure containerized environment. 
> 
> Our main challenge was designing a deployment system that runs seamlessly during local development on standard x86 and Apple Silicon laptops, while being fully compatible with our production environment—which is an Oracle VM running Linux on ARM64. Let's look at how we structured the microservices to support this goal."

---

## Slide 2: The Decoupled 6-Service Architecture
### ⏱️ Time: 0:45 - 1:45 (60 Seconds)

```
       +----------------------- hpe-network (Bridge) -----------------------+
       |                                                                    |
       |     [hpe-main-app] (Port 8000)                                     |
       |           |                                                        |
       |     +-----+----------------+---------------+                      |
       |     |                      |               |                      |
       |     v                      v               v                      |
[hpe-database] (8081)    [hpe-extractor] (8085)  [hpe-pdf-processor] (8084) |
       |     |                      |               |                      |
       |     +-----+----------------+               |                      |
       |           |  +-----------------------------+                      |
       |           v  v                                                    |
[hpe-llm] (8086) ------> External OpenAI API (HTTPS)                       |
[hpe-hwapi] (8087) ----> External DigiKey API (HTTPS)                      |
       |                                                                    |
       +--------------------------------------------------------------------+
```

### 📝 Slide Content
1. **`main-app` (Port 8000):** Frontend/UI gateway and entry point; manages user file uploads.
2. **`database` (Port 8081):** FastAPI layer interfacing with **MongoDB Atlas**, caching specs and managing sessions.
3. **`pdf_processor` (Port 8084):** Computes hashes, parses layout, and renders page previews.
4. **`extractor` (Port 8085):** Orchestrates multi-stage parametric value extraction.
5. **`llm` (Port 8086):** Single egress gateway for OpenAI API requests (embeddings, completions).
6. **`hwapi` (Port 8087):** Decoupled gateway for Digikey API requests with credential/token caching.

---

### 🗣️ Presenter Speaking Notes
> "To understand the deployment, we must understand the architecture. We transitioned from a monolithic code structure into a 6-service microservice layout.
> 
> * First, the `main-app` acts as our gateway, serving the user interface and accepting uploads.
> * Second, the `database` service handles all MongoDB queries, vector-based similarity caches, and user authentication.
> * Third, the `pdf_processor` analyzes uploaded files, computes hashes, and renders page previews.
> * Fourth, the `extractor` is the brain that orchestrates the RAG pipeline and parametric extraction.
> * Finally, we have two egress-focused services: the `llm` service and the newly decoupled `hwapi` service. 
> 
> This segregation is critical because it isolates complex processing—like LLM API calls and DigiKey catalog searches—into single-purpose, throttled containers, ensuring one service's load doesn't crash the rest of the application."

---

## Slide 3: Secure Isolation: Network & Storage Boundaries
### ⏱️ Time: 1:45 - 2:45 (60 Seconds)

```
                     +---------------------------+
                     |     hpe-main-app (8000)   |
                     +-------------+-------------+
                                   | (Uploads PDF)
                                   v
             =============================================
             ||  SHARED VOLUME: shared-datasheets       ||
             ||  Mounted at: /app/datasheets            ||
             =============================================
                                   | (Reads & Processes)
                                   v
                     +---------------------------+
                     |  hpe-pdf-processor (8084) |
                     +---------------------------+
```

### 📝 Slide Content
* **Network Isolation (`hpe-network`):**
  * A custom bridge network isolates internal service communication.
  * Inter-container communication uses container name DNS (e.g., `http://hpe-database:8081`) rather than localhost.
  * Restricts direct DB and internal tool access from the public internet.
* **Storage Synchronization (`shared-datasheets`):**
  * A named Docker volume mounts `/app/datasheets` inside both `main-app` and `pdf_processor`.
  * Avoids mounting physical host directories, decoupling containers from the underlying OS filesystem layout.
  * Guarantees instantaneous, low-latency PDF access across service boundaries.

---

### 🗣️ Presenter Speaking Notes
> "Now let's talk about security and persistence. How do these containers interact without exposing vulnerabilities?
> 
> We solved this through two core mechanisms: Network Isolation and Shared Volumes. 
> 
> We define a custom bridge network called `hpe-network`. External users can only hit Port 8000 on the `main-app`. Internal services communicate using secure Docker DNS aliases like `http://hpe-database:8081` instead of public IPs or localhost loopbacks. This means our database layer, LLM controller, and extractor are completely hidden from external access.
> 
> For data storage, we use a named Docker volume called `shared-datasheets`. When a user uploads a PDF datasheet, the `main-app` writes it to its mounted `/app/datasheets` directory. Because the volume is shared, the `pdf_processor` immediately detects and processes it without having to copy files over the network or rely on fragile host-relative file paths. This keeps our containers stateless and portable."

---

## Slide 4: Multi-Environment Configurations (.env)
### ⏱️ Time: 2:45 - 3:45 (60 Seconds)

```
                              [ .env Root Config ]
                                      |
         +----------------------------+----------------------------+
         |                                                         |
         v                                                         v
 [ Application Secrets ]                                  [ Deployment Variables ]
 - OPENAI_API_KEY="..."                                    - DOCKERHUB_USERNAME="raihannaeem"
 - MONGO_URI="mongodb+srv://..."                          - TARGET_PLATFORM="linux/arm64"
 - DIGIKEY_CLIENT_ID="..."                                 
 - DIGIKEY_CLIENT_SECRET="..."                             
```

### 📝 Slide Content
* **Single Source of Truth:** A centralized `.env` file in the project root supplies config variables to all containers.
* **Secret Injection:** Environment variables are dynamically loaded at runtime to populate:
  * API Keys (OpenAI API key)
  * Database credentials (MongoDB connection string)
  * Hardware Provider Auth (DigiKey Client ID & Secret)
* **Build Targets:** Controls publish variables (`DOCKERHUB_USERNAME`, `TARGET_PLATFORM`).
* **Environment Separation:** Local developer credentials stay isolated from staging or production values.

---

### 🗣️ Presenter Speaking Notes
> "To keep our configurations modular, we utilize a centralized `.env` file at the project root. This file acts as our single source of truth and is split into two categories: Application Secrets and Build Settings.
> 
> The application secrets contain the API keys for external services like OpenAI and DigiKey, as well as the MongoDB connection string. These secrets are injected into the respective containers at runtime and are never hardcoded in Dockerfiles or images.
> 
> The build settings, which include our DockerHub username and target platform, are used by our continuous integration scripts. This ensures that a developer can quickly swap out development credentials for staging or production environment variables without modifying the core compose files."

---

## Slide 5: The Build Strategies (Local vs Cross-Builds)
### ⏱️ Time: 3:45 - 5:00 (75 Seconds)

```
                       [ Build & Deploy Orchestration ]
                                      |
         +----------------------------+----------------------------+
         | (Same-machine Dev)                                      | (Local to Remote VM)
         v                                                         v
  [ Local Native Build ]                                    [ Cross-Platform Build ]
  $ docker compose build                                    $ DOCKER_DEFAULT_PLATFORM=linux/arm64 \
  $ docker compose up -d                                      docker compose build
```

### 📝 Slide Content
* **Local Native Building (Developer Machine):**
  * Uses `docker-compose.yml`.
  * Compiles Dockerfiles locally matching the developer's CPU architecture (e.g. x86_64 on Intel, arm64 on Apple M-series).
  * Fast compilation times; ideal for rapid inner-loop development.
* **Cross-Building for Oracle Cloud VM (ARM64 Target):**
  * Target cloud hosting is Oracle VM running Linux/ARM64.
  * Developers build on x86 machines but target ARM64 output using build emulation:
    ```bash
    DOCKER_DEFAULT_PLATFORM=linux/arm64 docker compose build
    ```
  * Builds compatible binaries ready for cloud execution.

---

### 🗣️ Presenter Speaking Notes
> "Let's discuss how we build and compile these services. We have two distinct build modes: Local Native builds and Cross-Platform builds.
> 
> When developing locally, running a simple `docker compose build` compiles native binaries matching the developer's hardware. This keeps development fast and responsive.
> 
> However, our staging environment runs on an Oracle VM, which is an ARM64-based Linux architecture. To bridge the gap when developers are using Intel or AMD x86 computers, we support cross-building. By prepending the platform environment variable—`DOCKER_DEFAULT_PLATFORM=linux/arm64`—Docker uses Buildx and QEMU emulation behind the scenes to compile binaries optimized specifically for the ARM64 Oracle VM. This guarantees that code that compiles locally runs flawlessly when deployed to the cloud, avoiding architecture-related library mismatches."

---

## Slide 6: Production Pipeline & Publishing
### ⏱️ Time: 5:00 - 6:00 (60 Seconds)

```
1. CONFIGURE           2. BUILD & PUSH                      3. DEPLOY (Oracle VM)
+------------+         +-------------------------------+    +-------------------------+
|  .env      |  ---->  | docker-compose.push.yml build | -> | docker-compose.prod.yml |
|  Settings  |         | & docker compose push         |    | pull & up -d            |
+------------+         +-------------------------------+    +-------------------------+
```

### 📝 Slide Content
* **Build-and-Push Config (`docker-compose.push.yml`):**
  * Tag-synchronized setup linking local images directly to DockerHub.
  * Automates platform target injection using `${TARGET_PLATFORM}`.
* **Command Sequence:**
  ```bash
  docker login
  docker compose -f docker-compose.push.yml build && \
  docker compose -f docker-compose.push.yml push && \
  docker compose -f docker-compose.push.yml down --rmi all
  ```
  * *Cleanup:* The last step deletes local platform-emulated images to conserve disk space.
* **Production Startup on Oracle VM:**
  ```bash
  docker compose -f docker-compose.prod.yml pull
  docker compose -f docker-compose.prod.yml up -d
  ```

---

### 🗣️ Presenter Speaking Notes
> "To deploy to production, we created a streamlined pipeline using two specialized Docker Compose files: `docker-compose.push.yml` and `docker-compose.prod.yml`.
> 
> First, on the build server or developer laptop, we log in to Docker Hub and execute the push compose command. This builds our microservices for the target architecture, pushes the tagged images to the Docker Hub registry under the `raihannaeem` namespace, and immediately cleans up the local copies to prevent disk space saturation.
> 
> Second, on the destination Oracle VM, we don't need any source code at all. We copy only the production compose configuration and the `.env` file, and run `docker compose pull` followed by `docker compose up -d`. This pulls the pre-built, ARM64-compiled images directly from Docker Hub and launches them instantly. This keeps our server deployment lightweight, fast, and secure."

---

## Slide 7: Verification & Health Checks
### ⏱️ Time: 6:00 - 7:00 (60 Seconds)

```
$ docker compose ps

NAME                 IMAGE                                  PORTS                    STATUS
hpe-main-app         raihannaeem/hpe-main-app:latest        0.0.0.0:8000->8000/tcp   running
hpe-extractor        raihannaeem/hpe-extractor:latest       0.0.0.0:8085->8085/tcp   running
hpe-pdf-processor    raihannaeem/hpe-pdf-processor:latest   0.0.0.0:8084->8084/tcp   running
hpe-database         raihannaeem/hpe-database:latest        0.0.0.0:8081->8081/tcp   running
hpe-llm              raihannaeem/hpe-llm:latest             0.0.0.0:8086->8086/tcp   running
hpe-hwapi            raihannaeem/hpe-hwapi:latest           0.0.0.0:8087->8087/tcp   running
```

### 📝 Slide Content
* **Status Auditing:** 
  * Run `docker compose ps` to verify that all 6 services are up and mapped to their appropriate ports.
* **Logging & Observability:**
  * View unified real-time logs for system tracing:
    ```bash
    docker compose logs -f
    ```
  * Drill down into specific service bottlenecks (e.g. tracking LLM response times or extractor errors):
    ```bash
    docker compose logs -f main-app
    ```
* **Resource Cleanup:**
  * Standard teardown: `docker compose down`
  * Volume purge (resets files & caches): `docker compose down -v`

---

### 🗣️ Presenter Speaking Notes
> "Once deployed, we need to verify that everything is running correctly. This is done using Docker Compose's built-in monitoring tools.
> 
> Running `docker compose ps` gives us a real-time status table of all containers. We verify that all six services—from our entry point `hpe-main-app` on port 8000 to our custom `hpe-hwapi` service on port 8087—are in the 'running' state and properly mapped.
> 
> For debugging, we use Docker's unified logging. Running `docker compose logs -f` gives us a colored stream of logs from all six microservices combined, which makes tracking multi-hop API requests (e.g. from the frontend, through the extractor, into the LLM service) extremely simple. If we want to isolate logs, we just append the service name. Finally, we can safely tear down or reset the environment using the `down` command, optionally adding the `-v` flag to clear out files and DB caches."

---

## Slide 8: Deployment Advantages & Takeaways
### ⏱️ Time: 7:00 - 8:00 (60 Seconds)

```
========================================================================
|                           KEY ACHIEVEMENTS                           |
|                                                                      |
|  [Decoupled]      [Agnostic]         [Isolated]        [Observable]  |
|  6 microservices  Local x86 to       Custom network    Centralized   |
|  running in       Remote ARM64 VM    with shared       logs & state  |
|  harmony          emulations         data volumes      resets        |
========================================================================
```

### 📝 Slide Content
* **Architecture Highlights:**
  * Decoupled architecture prevents resource starvation (e.g., PDF parsing doesn't block the UI).
  * Complete API key isolation via centralized environment configs.
* **Operations Value:**
  * Clean, 1-command build-and-push workflow.
  * Zero-code-dependency deployment on remote VMs using pre-built images.
  * Built-in scalability: individual services can be scaled/reloaded without downtime.

---

### 🗣️ Presenter Speaking Notes
> "To conclude, this deployment strategy gives us several key advantages:
> 
> First, it decouples resource-heavy tasks like layout parsing and LLM API calls from our user interface, ensuring the application remains responsive under heavy load.
> 
> Second, our environment configuration keeps all sensitive keys secure and outside of version control.
> 
> Third, our multi-platform build setup lets developers build on whatever hardware they prefer, while guaranteeing seamless deployment onto our ARM64 Oracle cloud infrastructure.
> 
> Ultimately, we have established a deployment pipeline that is clean, secure, highly observable, and ready for production scale. 
> 
> Thank you, and I would be happy to take any questions you have regarding our deployment process."

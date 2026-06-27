# 🚀 HPE Component Analysis Pipeline (Local Running Guide)

This guide provides simple, step-by-step instructions to get the decoupled microservice application up and running on your local machine.

---

## 📋 Prerequisites
* **Python:** Python 3.10 or higher
* **Database:** Access to a MongoDB instance (local or MongoDB Atlas)

---

## 🏃 Steps to Get Started

### Step 1: Create & Activate a Virtual Environment
From the root workspace directory, run:
```bash
# Create venv
python -m venv venv

# Activate venv (Windows)
venv\Scripts\activate

# Activate venv (Mac/Linux)
source venv/bin/activate
```

### Step 2: Install Global Dependencies
Install the combined dependencies required for all microservices:
```bash
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables
You need to create a local `.env` file in **each** service folder. Refer to [environment_variable_setup.md](environment_variable_setup.md) for full descriptions.

At a minimum, configure the following keys:
1. **`llm/.env`**
   ```env
   OPENAI_API_KEY="your-openai-api-key"
   ```
2. **`database/.env`**
   ```env
   MONGO_URI="your-mongodb-connection-string"
   DIGIKEY_CLIENT_ID="your-digikey-client-id"
   DIGIKEY_CLIENT_SECRET="your-digikey-client-secret"
   ```
3. **`pdf_processor/.env`**
   ```env
   DATASHEETS_DIR="C:/path/to/HPE-TEAM-6/main-app/datasheets"
   ```
4. **`main-app/.env`**
   ```env
   DATASHEETS_DIR="C:/path/to/HPE-TEAM-6/main-app/datasheets"
   DB_SERVER_URL="http://127.0.0.1:8081"
   EXTRACTOR_SERVER_URL="http://127.0.0.1:8085"
   PDF_PROCESSOR_SERVER_URL="http://127.0.0.1:8084"
   ```

---

### Step 4: Run the Microservices
Open **5 separate terminal sessions**, activate your virtual environment in each, and start the servers using uvicorn:

#### 1. Start LLM Service (Port 8086)
```bash
cd llm
uvicorn llmServer:app --port 8086
```

#### 2. Start Database Service (Port 8081)
```bash
cd database
uvicorn databaseServer:app --port 8081
```

#### 3. Start Extractor Service (Port 8085)
```bash
cd extractor
uvicorn extractorServer:app --port 8085
```

#### 4. Start PDF Processor Service (Port 8084)
```bash
cd pdf_processor
uvicorn pdfProcessorServer:app --port 8084
```

#### 5. Start Main App Dashboard (Port 8000)
```bash
cd main-app
uvicorn app:app --port 8000
```

---

### Step 5: Access the Dashboard
Once all 5 services are running, open your web browser and navigate to:
👉 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

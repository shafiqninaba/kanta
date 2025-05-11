# Face Encoding Service

A FastAPI micro-service for uploading images, detecting faces, generating embeddings, storing in Azure Blob Storage + PostgreSQL, and querying by clusters or similarity.

---

## 🛠 Prerequisites

* **Python 3.10+**
* **PostgreSQL 12+** (with `vector` extension enabled)
* **Azure Storage Account** (to host Blob container)
* `face_recognition` dependencies (dlib, cmake, etc.)

---

## ⚙️ Installation

1. **Clone & install dependencies**

   ```bash
   git clone https://github.com/shafiqninaba/kanta.git
   cd kanta/encode-faces
   python -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

2. **Environment Variables**
   Copy `.env.example` → `.env` and fill in your values:

   ```ini
   DBHOST=your_db_host
   DBPORT=5432
   DBUSER=your_db_user
   DBPASSWORD=your_db_password
   DBNAME=your_db_name
   SSLMODE=require
   AZURE_STORAGE_CONNECTION_STRING=your_azure_connection_string
   AZURE_CONTAINER_NAME=images
   ```

---

## 🗄 Database Setup

### 1. Enable the `vector` extension on Azure PostgreSQL

In the Azure Portal, under your server's **Server parameters**, add `vector` to **Allowed extensions**.

### 2. Create schema via psql

```bash
# Connect to your server
psql "host=kanta-test.postgres.database.azure.com port=5432 user=kanta_admin dbname=postgres sslmode=require"

# List databases
\l

# Switch to your database or create one
CREATE DATABASE test_db;
\c test_db

# Run the provided schema
\i schema.sql

# Verify tables
\dt

# Quit
\q
```

### 3. (Optional) Using Alembic migrations

If you prefer migrations:

```bash
alembic init alembic
# Edit alembic.ini → sqlalchemy.url = postgresql+asyncpg://...
# Edit alembic/env.py to import models and target_metadata
alembic revision --autogenerate -m "Initial schema"
alembic upgrade head
```

---

## ☁️ Azure Blob Storage Setup

1. Create an **Azure Storage Account** in the Portal.
2. Under **Access keys**, copy the **Connection string** into your `.env`.
3. The service will auto-create container named by `AZURE_CONTAINER_NAME` (default: `images`).

---

## 🚀 Running the Server

```bash
uvicorn main:app --reload
```

or

```bash
uv run fastapi dev
```

By default it binds to `0.0.0.0:8000`.
---

## 📡 API Endpoints

1. **POST** `/upload-image`
   Upload JPEG/PNG, detect faces, store in Azure & DB.

   ```bash
   curl -X POST http://localhost:8000/upload-image \
     -F "image=@data/test/family.jpg"
   ```

2. **GET** `/pics`
   List images with optional filters:

   * `limit`, `offset`
   * `date_from`, `date_to` (ISO8601)
   * `min_faces`, `max_faces`
   * `cluster_list_id` (repeatable)

   ```bash
   curl "http://localhost:8000/pics?limit=10&cluster_list_id=3&cluster_list_id=5"
   ```

3. **GET** `/pics/{uuid}`
   Fetch one image’s metadata + its faces:

   ```bash
   curl http://localhost:8000/pics/<uuid>
   ```

4. **DELETE** `/pics/{uuid}`
   Delete DB rows + Azure blob:

   ```bash
   curl -X DELETE http://localhost:8000/pics/<uuid>
   ```

5. **GET** `/clusters`

   * **Without** query → returns per-cluster summary (counts + up to 5 samples).
   * **With** `?cluster_ids=…` → 307 redirect to `/pics?cluster_list_id=…`.

   ```bash
   curl http://localhost:8000/clusters
   curl -v "http://localhost:8000/clusters?cluster_ids=3&cluster_ids=5"
   ```

6. **POST** `/find-similar`
   Upload exactly one face, return top-K similar faces:

   ```bash
   curl -X POST http://localhost:8000/find-similar?metric=cosine&top_k=5 \
     -F "image=@data/test/family.jpg"
   ```

7. **GET** `/blob/pics` & `/blob/pics/{uuid}`
   Unchanged infinite-scroll listing / single-blob metadata.

8. **GET** `/health`
   Liveness/readiness probe:

   ```bash
   curl http://localhost:8000/health
   ```

---

## 🧪 Testing

Your test suite covers both raw‐SQL and ORM variants. To run:

```bash
pytest -vv
```

---

## 🔧 Common psql Commands

```sql
-- List all databases
\l

-- Connect to a database
\c your_database_name

-- List tables
\dt

-- Run a SQL file
\i schema.sql

-- Quit psql
\q
```

---

## ⚠️ Tips

* Ensure your PostgreSQL firewall allows your app’s IP.
* Face detection (dlib) can be CPU-heavy—consider a GPU build for large scale.
* In production, lock down CORS origins.

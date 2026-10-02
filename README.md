# 🇲🇦 Moroccan CNIE OCR & KYC Verification Pipeline

A production-grade, enterprise-ready Optical Character Recognition (OCR) and automated KYC (Know Your Customer) identity verification pipeline engineered specifically for the Moroccan **Carte Nationale d'Identité Electronique (CNIE)**.

Supports both **Post-2020 Biometric CNIEs** (with 3-line ICAO 9303 MRZ) and **Pre-2020 Classic CNIEs** (visual layout).

---

## 🚀 Key Features

* **Dual-Generation Card Layout Parsing**:
  * **Post-2020 Electronic CNIE**: Extracts visual text, citizen face portrait, and 3-line TD1 Machine Readable Zone (`MRZ`) with UN ICAO 9303 7-3-1 modulus-10 check digits.
  * **Pre-2020 Classic CNIE**: Extracts visual names, 4-digit/classic CNIE numbers (e.g. `AS3919`), visual gender (`Sexe: M/F`), parents' names (`Fils de` / `et de`), and registration act numbers.
* **Cross-Card Affiliation & Fraud Detection**:
  * Cross-references CNIE numbers, dates of birth, and names between Front (Recto) and Back (Verso).
  * Automatically detects and flags **mismatched pairs** (e.g. Customer A's front uploaded with Customer B's back).
  * Diagnoses duplicate sides (e.g. 2 front sides uploaded) and flags missing sides.
* **Automated Dual-Card Contour Splitting**:
  * Ingests single scans or photos containing both Recto and Verso (or A4 photocopies) and automatically segments them into individual card regions via OpenCV contour analysis.
* **Biometric Citizen Portrait Isolation**:
  * Automatically detects photo position (Left for Post-2020, Right for Pre-2020) and crops citizen face portraits into isolated JPEG files or zero-disk Base64 strings.
* **Interactive KYC Web Dashboard**:
  * Modern, responsive glassmorphic web UI with dark/light themes, real-time client-side blur score indicators, dual drag-and-drop dropzones, and one-click JSON export.
* **Bulk Batch Processing CLI**:
  * Autonomous directory scanning with smart filename pairing (`recto1.png` + `verso1.png` ➔ `card_pair_1`) and consolidated CSV/JSON audit reporting.
* **Production Docker Containerization**:
  * Dockerized with pre-cached EasyOCR weights and volume persistence for instant offline startup.

---

## 🏗️ Architecture Overview

```
                          ┌─────────────────────────────────────┐
                          │   Input: Scans, Uploads, Composite   │
                          └──────────────────┬──────────────────┘
                                             │
                                    [ Preprocessing ]
                           (Blur Estimation & Contour Split)
                                             │
                        ┌────────────────────┴────────────────────┐
                        ▼                                         ▼
                 [ RECTO (Front) ]                        [ VERSO (Back) ]
            • CNIE Number                            • Father / Mother Name
            • Surname & Given Name                   • Registered Address
            • Birth Date & Place                     • Civil Registration Act
            • Expiry Date                            • TD1 MRZ (Post-2020)
            • Citizen Photo Crop                     • Visual Gender (Pre-2020)
                        │                                         │
                        └────────────────────┬────────────────────┘
                                             │
                                  [ Affiliation Guard ]
                          (Cross-Card Integrity & ICAO Checksum)
                                             │
             ┌───────────────────────────────┼───────────────────────────────┐
             ▼                               ▼                               ▼
     [ Interactive Web UI ]         [ FastAPI REST API ]            [ Batch CLI ]
   (http://localhost:8000/)          (/api/v1/extract)         (reports/kyc_summary.csv)
```

---

## 🛠️ Quickstart Guide

### 1. Local Environment Setup

Clone the repository and set up a virtual environment:

```bash
git clone git@github.com:CrocoMan29/Cin-Ocr-Pipeline.git
cd Cin-Ocr-Pipeline

# Create and activate virtual environment
python3 -m venv myenv
source myenv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

### 2. Interactive KYC Web Dashboard & REST API

Launch the FastAPI microservice:

```bash
uvicorn src.api:app --reload
```

* **Interactive Web Dashboard**: [http://localhost:8000/](http://localhost:8000/)
* **Interactive Swagger Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
* **System Health Check**: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

---

### 3. Command Line Interface (CLI)

#### Process a Single Card Pair:
```bash
python src/main.py data/recto1.png data/verso1.png
```

#### Process a Composite Scan (Auto-split):
```bash
python src/main.py data/combined_test.png
```

#### Run Batch Processing on a Directory:
```bash
python src/main.py --batch data/ --output reports/kyc_summary.csv
```
* Generates both `reports/kyc_summary.csv` (Excel-compatible) and `reports/kyc_summary.json` with an executive audit summary in the terminal.

---

### 4. Run via Docker Compose

Run the entire application in a container with pre-cached model weights:

```bash
# Build and launch
docker compose up --build

# Open in browser
open http://localhost:8000/

# Stop container
docker compose down
```

---

## 📡 REST API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/` | `GET` | Serves the interactive KYC Web Dashboard |
| `/api/v1/extract` | `POST` | Primary OCR extraction & affiliation validation |
| `/api/v1/health` | `GET` | Health check & microservice diagnostics |
| `/docs` | `GET` | Interactive OpenAPI Swagger UI |
| `/static/extracted_faces/{filename}` | `GET` | Static file URL for cropped citizen portraits |

### Sample API Request (`POST /api/v1/extract`)
```bash
curl -X POST "http://localhost:8000/api/v1/extract?return_base64_photo=false" \
  -H "accept: application/json" \
  -F "recto=@data/recto1.png" \
  -F "verso=@data/verso1.png"
```

### Sample JSON Response
```json
{
  "status": "success",
  "message": "Full Moroccan CNIE profile extracted and verified successfully.",
  "processing_time_ms": 6835.3,
  "card_type": "full_profile",
  "identity": {
    "cnie": "U1234567",
    "first_name": "ZAINEB",
    "last_name": "EL ALAMI",
    "birth_date": "05/12/1983",
    "place_of_birth": "OUARZAZATE",
    "expiry_date": "22/07/2029",
    "gender": "Female",
    "nationality": "MAR"
  },
  "family_and_address": {
    "father_name": "LARBI BEN MOHAMMED",
    "mother_name": "SARA BENT MBAREK",
    "address": "NUM 370 LOT ESSALAM AV MOULAY YOUSSEF OUJDA",
    "civil_act": "1234/5678/1983"
  },
  "validation": {
    "is_affiliated": true,
    "affiliation_status": "verified",
    "affiliation_details": "Verified: Front and Back CNIE match ('U1234567').",
    "sides_detected": ["recto", "verso"],
    "missing_side": null,
    "cnie_cross_verified": true,
    "birth_date_mrz_verified": true,
    "expiry_date_mrz_verified": true,
    "dob_checksum_valid": true,
    "expiry_checksum_valid": true,
    "mrz_detected": true,
    "card_generation": "Post-2020 CNIE"
  },
  "photo_url": "/static/extracted_faces/photo_U1234567.jpg"
}
```

---

## 🔒 Security & Privacy (KYC Compliance)

1. **Anti-Leakage `.gitignore`**: All raw card scans (`data/*.png`, `data/*.jpg`), extracted face photos (`data/extracted_faces/`), and batch reports (`reports/`) are strictly excluded from version control.
2. **Ephemeral Artifact Lifecycle**: The FastAPI service runs an automated background cleanup routine purging extracted face photos older than 1 hour.
3. **Defensive Input Validation**: Enforces a strict 10MB file limit and binary magic-byte inspection (`JPEG`, `PNG`, `WebP`) to prevent Denial-of-Service and arbitrary file upload exploits.
4. **Zero-Disk Transmission**: Supports `return_base64_photo=true` to transmit cropped portrait images purely in-memory via Base64 data URIs.

---

## 📂 Project Structure

```
Cin-Ocr-Pipeline/
├── Dockerfile                 # Production multi-stage Docker container
├── docker-compose.yml         # Container orchestration with volume persistence
├── .dockerignore              # Docker build exclusions
├── .gitignore                 # Strict PII & data exclusion rules
├── requirements.txt           # Python package dependencies
├── README.md                  # System documentation
├── src/
│   ├── api.py                 # FastAPI microservice & static file mount
│   ├── extraction.py          # EasyOCR, MRZ ICAO 9303, Affiliation engine
│   ├── main.py                # Single & Batch Processing CLI
│   ├── preprocessing.py       # Image enhancement, blur test, contour splitter
│   └── schemas.py             # Pydantic data models & response schemas
├── static/
│   ├── index.html             # KYC Web Dashboard markup
│   ├── style.css              # Modern glassmorphic theme styling
│   └── app.js                 # Drag & drop upload, canvas blur detection
├── data/
│   ├── .gitkeep
│   └── extracted_faces/       # Ephemeral cropped citizen portraits
└── reports/                   # Consolidated batch CSV/JSON export directory
```

---

## 📄 License
This project is developed for Moroccan identity document verification and educational/enterprise KYC research.

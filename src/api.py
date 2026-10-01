# src/api.py
"""
FastAPI REST API for Moroccan Carte Nationale d'Identité (CNIE) OCR Microservice.

Tier 2 Hardening Features:
- Defensive Validation: 10MB payload size guard & magic-byte MIME inspection.
- Concurrency: Non-blocking threadpool offloading (run_in_threadpool).
- Data Privacy: Ephemeral face photo cleanup & optional base64 zero-disk mode.
- Structured Logging: Request tracing with latency benchmarks.
- Singleton OCR Engine lifecycle (zero model reload delay per request).
- Interactive Swagger documentation at /docs.
"""

import os
import sys
import time
import base64
import logging
from contextlib import asynccontextmanager
from typing import Optional, List

import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile, HTTPException, Request, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

# Ensure src directory is in sys.path
src_dir = os.path.dirname(os.path.abspath(__file__))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from preprocessing import split_cards_if_composite, prepare_image_for_ocr, estimate_blur
from extraction import OCREngine
from schemas import CINExtractionResponse, IdentityData, FamilyAndAddressData, ValidationStatus

# 1. Setup Structured Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("cnie_ocr_api")

# 2. Security Constraints
MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 Megabytes limit

def validate_image_payload(file_bytes: bytes, filename: str) -> str:
    """
    Validates file payload defensively:
    1. Enforces max 10MB file size (DoS/OOM prevention).
    2. Inspects binary magic bytes to verify genuine JPEG, PNG, or WebP.
    """
    if len(file_bytes) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Uploaded file '{filename}' is empty."
        )

    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        size_mb = len(file_bytes) / (1024 * 1024)
        logger.warning(f"Rejected payload '{filename}': size {size_mb:.2f}MB exceeds 10MB limit.")
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File '{filename}' exceeds maximum allowed size of 10MB ({size_mb:.2f}MB)."
        )

    # Magic Bytes Inspection
    if file_bytes.startswith(b'\xff\xd8\xff'):
        return "image/jpeg"
    elif file_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
        return "image/png"
    elif file_bytes.startswith(b'RIFF') and len(file_bytes) >= 12 and file_bytes[8:12] == b'WEBP':
        return "image/webp"

    logger.warning(f"Rejected payload '{filename}': invalid magic bytes.")
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail=f"File '{filename}' is not a valid JPEG, PNG, or WebP image."
    )

def cleanup_ephemeral_faces(target_dir: str, max_age_seconds: int = 3600) -> int:
    """
    GDPR/Privacy hygiene: Purges extracted face crops older than max_age_seconds (default 1 hour).
    Returns the count of purged files.
    """
    if not os.path.exists(target_dir):
        return 0
    now = time.time()
    purged = 0
    for fname in os.listdir(target_dir):
        fpath = os.path.join(target_dir, fname)
        if os.path.isfile(fpath) and fname.startswith("photo_"):
            if now - os.path.getmtime(fpath) > max_age_seconds:
                try:
                    os.remove(fpath)
                    purged += 1
                except OSError:
                    pass
    return purged

# 3. Application Lifespan: Load OCR engine once as a Singleton
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initializes and warms up the EasyOCR neural network on application startup.
    Keeps model in memory across all requests for optimal throughput.
    """
    logger.info("Initializing EasyOCR Engine (Singleton)...")
    app.state.engine = OCREngine(languages=['en', 'fr'], use_gpu=False)
    
    # Run privacy cleanup on startup
    purged_count = cleanup_ephemeral_faces(faces_dir, max_age_seconds=3600)
    if purged_count > 0:
        logger.info(f"Cleaned up {purged_count} expired identity face artifacts.")
        
    logger.info("OCR Engine initialized and ready.")
    yield
    logger.info("Shutting down OCR Microservice.")

app = FastAPI(
    title="Moroccan CNIE OCR Service",
    description="Production REST API for automated Moroccan Identity Card (CNIE) scanning, validation, and KYC photo extraction.",
    version="1.1.0",
    lifespan=lifespan
)

# 4. CORS Middleware for web and mobile client integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 5. Mount static directory for serving extracted citizen portraits
project_root = os.path.dirname(src_dir)
faces_dir = os.path.join(project_root, "data", "extracted_faces")
os.makedirs(faces_dir, exist_ok=True)
app.mount("/static/extracted_faces", StaticFiles(directory=faces_dir), name="extracted_faces")

def decode_validated_image(file_bytes: bytes, filename: str) -> np.ndarray:
    """
    Validates payload bytes and decodes into an OpenCV matrix.
    """
    validate_image_payload(file_bytes, filename)
    np_arr = np.frombuffer(file_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to decode image from '{filename}'. File content may be corrupted."
        )
    return img

@app.get("/", tags=["System"])
async def root():
    """Service health check and API overview."""
    return {
        "service": "Moroccan CNIE OCR Microservice",
        "status": "healthy",
        "version": "1.1.0",
        "docs_url": "/docs",
        "features": [
            "Magic-byte MIME verification",
            "10MB payload size guard",
            "Non-blocking threadpool concurrency",
            "Dual-side & composite card auto-splitting",
            "Base64 zero-disk photo output",
            "ICAO 9303 checksums"
        ]
    }

@app.post(
    "/api/v1/extract",
    response_model=CINExtractionResponse,
    tags=["Extraction"],
    summary="Extract Identity, Address, and Photo from Moroccan CNIE",
    description="""
Upload either:
1. **A single image** (`file`): Can be a single side OR a scan/photo containing both Recto and Verso.
2. **Two separate images** (`recto` and `verso`): Front and back sides in any order.

**Security & Performance**:
- Maximum upload size: 10MB.
- Supported formats: JPEG, PNG, WebP (verified via binary magic bytes).
- Set `return_base64_photo=True` to receive a base64 data URI (zero disk dependency).
"""
)
async def extract_cin(
    request: Request,
    file: Optional[UploadFile] = File(None, description="Single card image or dual-card composite scan"),
    recto: Optional[UploadFile] = File(None, description="Separate front side (Recto) image"),
    verso: Optional[UploadFile] = File(None, description="Separate back side (Verso) image"),
    return_base64_photo: bool = Query(False, description="Include base64-encoded citizen photo in JSON response")
):
    start_time = time.perf_counter()
    client_ip = request.client.host if request.client else "unknown"
    engine: OCREngine = request.app.state.engine

    # 1. Validate inputs & Decode
    card_matrices: List[np.ndarray] = []

    if recto or verso:
        if recto:
            r_bytes = await recto.read()
            r_img = decode_validated_image(r_bytes, recto.filename)
            card_matrices.append(prepare_image_for_ocr(r_img))
        if verso:
            v_bytes = await verso.read()
            v_img = decode_validated_image(v_bytes, verso.filename)
            card_matrices.append(prepare_image_for_ocr(v_img))
        logger.info(f"[{client_ip}] Received separate uploads: recto={'yes' if recto else 'no'}, verso={'yes' if verso else 'no'}")
    elif file:
        f_bytes = await file.read()
        raw_img = decode_validated_image(f_bytes, file.filename)
        
        _, is_blurry = estimate_blur(raw_img)
        if is_blurry:
            logger.warning(f"[{client_ip}] Uploaded image '{file.filename}' exhibits low sharpness score.")

        sub_cards = split_cards_if_composite(raw_img)
        for c in sub_cards:
            card_matrices.append(prepare_image_for_ocr(c))
        logger.info(f"[{client_ip}] Processed single upload '{file.filename}' -> {len(card_matrices)} card region(s) detected.")
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No image uploaded. Please provide either 'file' or 'recto' / 'verso'."
        )

    # 2. Run OCR Engine in Threadpool (non-blocking for high concurrency)
    try:
        result_package = await run_in_threadpool(engine.process_card_images, card_matrices)
    except Exception as e:
        logger.error(f"[{client_ip}] OCR Pipeline exception: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OCR processing pipeline error: {str(e)}"
        )

    res_type = result_package["type"]
    data = result_package["data"]
    processing_time = round((time.perf_counter() - start_time) * 1000.0, 1)

    # 3. Resolve photo outputs (Static URL + Base64)
    photo_url = None
    photo_base64 = None

    if data.get("photo_path") and os.path.exists(data["photo_path"]):
        photo_filename = os.path.basename(data["photo_path"])
        photo_url = f"/static/extracted_faces/{photo_filename}"
        
        if return_base64_photo:
            try:
                with open(data["photo_path"], "rb") as p_file:
                    b64_str = base64.b64encode(p_file.read()).decode("utf-8")
                    photo_base64 = f"data:image/jpeg;base64,{b64_str}"
            except Exception as b64_err:
                logger.warning(f"Failed to encode base64 photo: {b64_err}")

    logger.info(f"[{client_ip}] Completed in {processing_time}ms | Type: {res_type} | CNIE: {data.get('cnie_number')}")

    # 4. Map into Pydantic Response Schema
    val = data.get("validation", {})
    card_gen = val.get("card_generation", "Post-2020 CNIE" if val.get("mrz_detected") else "Pre-2020 CNIE")

    identity = IdentityData(
        cnie=data.get("cnie_number", "Not detected"),
        first_name=data.get("first_name", "Not detected"),
        last_name=data.get("last_name", "Not detected"),
        birth_date=data.get("birth_date", "Not detected"),
        place_of_birth=data.get("birth_place", "Not detected"),
        expiry_date=data.get("expiry_date", "Not detected"),
        gender=data.get("gender", "Not detected"),
        nationality=data.get("nationality", "MAR")
    )

    family_and_address = FamilyAndAddressData(
        father_name=data.get("father_name", "Not detected"),
        mother_name=data.get("mother_name", "Not detected"),
        address=data.get("address", "Not detected"),
        civil_act=data.get("civil_act", "Not detected")
    )

    validation = ValidationStatus(
        is_affiliated=val.get("is_affiliated"),
        affiliation_status=val.get("affiliation_status", "not_applicable"),
        affiliation_details=val.get("affiliation_details", "Affiliation check completed"),
        sides_detected=val.get("sides_detected", result_package.get("sides_detected", [])),
        missing_side=val.get("missing_side", result_package.get("missing_side")),
        cnie_cross_verified=val.get("cnie_cross_verified", False),
        birth_date_mrz_verified=val.get("birth_date_mrz_verified", False),
        expiry_date_mrz_verified=val.get("expiry_date_mrz_verified", False),
        dob_checksum_valid=val.get("dob_checksum_valid", False),
        expiry_checksum_valid=val.get("expiry_checksum_valid", False),
        mrz_detected=val.get("mrz_detected", False),
        card_generation=card_gen
    )

    if res_type == "full_profile":
        resp_status = "success"
        resp_message = f"Full Moroccan CNIE profile extracted and verified successfully. {val.get('affiliation_details', '')}".strip()
    elif res_type == "mismatched_pair":
        resp_status = "warning"
        resp_message = f"Card affiliation mismatch! {val.get('affiliation_details', 'The uploaded Verso does not belong to the uploaded Recto.')}".strip()
    elif res_type in ("duplicate_recto", "duplicate_verso"):
        resp_status = "warning"
        resp_message = val.get("affiliation_details", f"Duplicate sides detected: {res_type}. The opposite side is missing.")
    elif res_type in ("single_recto", "single_verso"):
        resp_status = "success"
        side_name = "Recto" if res_type == "single_recto" else "Verso"
        opp_side = "Verso" if res_type == "single_recto" else "Recto"
        resp_message = f"Single side ({side_name}) processed successfully. {opp_side} side is missing."
    else:
        resp_status = "success"
        resp_message = "Processed successfully."

    return CINExtractionResponse(
        status=resp_status,
        message=resp_message,
        processing_time_ms=processing_time,
        card_type=res_type,
        identity=identity,
        family_and_address=family_and_address,
        validation=validation,
        photo_url=photo_url,
        photo_base64=photo_base64
    )

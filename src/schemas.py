# src/schemas.py
"""
Pydantic data models for the Moroccan CIN OCR REST API.
Provides type validation, schema definitions, and Swagger UI documentation.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class IdentityData(BaseModel):
    """Extracted personal identity fields from the card."""
    cnie: str = Field(..., description="National identity number (e.g. U1234567, AS3919)", example="U1234567")
    first_name: str = Field(..., description="First name in Latin letters", example="ZAINEB")
    last_name: str = Field(..., description="Last name in Latin letters", example="EL ALAMI")
    birth_date: str = Field(..., description="Date of birth in DD/MM/YYYY format", example="05/12/1983")
    place_of_birth: str = Field(..., description="Place / city of birth", example="OUARZAZATE")
    expiry_date: str = Field(..., description="Document expiry date in DD/MM/YYYY format", example="22/07/2029")
    gender: Optional[str] = Field("Not detected", description="Gender (Male / Female)", example="Female")
    nationality: Optional[str] = Field("MAR", description="Three-letter nationality code", example="MAR")

class FamilyAndAddressData(BaseModel):
    """Extracted lineage and residence metadata from the Verso (back side)."""
    father_name: Optional[str] = Field("Not detected", description="Father's full name", example="LARBI BEN MOHAMMED")
    mother_name: Optional[str] = Field("Not detected", description="Mother's full name", example="SARA BENT MBAREK")
    address: Optional[str] = Field("Not detected", description="Registered residential address", example="NUM 370 LOT ESSALAM AV MOULAY YOUSSEF OUJDA")
    civil_act: Optional[str] = Field("Not detected", description="Civil registration act number", example="1234/5678/1983")

class AffiliationStatus(BaseModel):
    """Integrity check verifying whether Verso belongs to the same citizen as Recto."""
    is_affiliated: Optional[bool] = Field(None, description="True if Front and Back belong to the same person, False if mismatched, None if single side")
    status: str = Field("not_applicable", description="verified, mismatch, inconclusive, duplicate_side, or not_applicable", example="verified")
    cnie_match: bool = Field(False, description="True if CNIE number matches between Front and Back")
    dob_match: Optional[bool] = Field(None, description="True if visual birth date matches back MRZ")
    name_match: Optional[bool] = Field(None, description="True if visual name matches back MRZ")
    details: str = Field("Affiliation check completed", description="Detailed explanation of the affiliation cross-check", example="Front and Back CNIE numbers match (U1234567)")

class ValidationStatus(BaseModel):
    """Integrity, affiliation, and cryptographic checksum validation results."""
    is_affiliated: Optional[bool] = Field(None, description="True if Verso belongs to Recto; False if mismatched; None if single side")
    affiliation_status: str = Field("not_applicable", description="verified, mismatch, inconclusive, duplicate_side, or not_applicable", example="verified")
    affiliation_details: str = Field("Affiliation check completed", description="Summary explanation of affiliation cross-check")
    sides_detected: List[str] = Field(default_factory=list, description="Detected sides in upload (e.g. ['recto', 'verso'], ['recto', 'recto'])", example=["recto", "verso"])
    missing_side: Optional[str] = Field(None, description="Name of missing side: 'recto', 'verso', or None if both present", example=None)
    cnie_cross_verified: bool = Field(..., description="True if CNIE matches between Front and Back")
    birth_date_mrz_verified: Optional[bool] = Field(None, description="True if visual birth date matches back MRZ, None if no MRZ on card")
    expiry_date_mrz_verified: Optional[bool] = Field(None, description="True if visual expiry date matches back MRZ, None if no MRZ on card")
    dob_checksum_valid: Optional[bool] = Field(None, description="True if ICAO 9303 DOB checksum passed, None if no MRZ on card")
    expiry_checksum_valid: Optional[bool] = Field(None, description="True if ICAO 9303 Expiry checksum passed, None if no MRZ on card")
    mrz_detected: bool = Field(..., description="True if 3-line MRZ is present on back")
    card_generation: str = Field(..., description="Post-2020 (electronic MRZ) or Pre-2020 (classic visual)", example="Post-2020 CNIE")

class CINExtractionResponse(BaseModel):
    """Top-level unified JSON response schema returned by the extraction API."""
    status: str = Field(..., description="Execution status: success, warning, or error", example="success")
    message: str = Field(..., description="Human-readable result summary", example="Card processed successfully")
    processing_time_ms: float = Field(..., description="Total processing time in milliseconds", example=650.4)
    card_type: str = Field(..., description="Result layout type (full_profile, single_recto, single_verso, duplicate_recto, duplicate_verso, mismatched_pair)", example="full_profile")
    identity: IdentityData
    family_and_address: FamilyAndAddressData
    validation: ValidationStatus
    photo_url: Optional[str] = Field(None, description="Static URL to the cropped citizen portrait photo", example="/static/extracted_faces/photo_U1234567.jpg")
    photo_base64: Optional[str] = Field(None, description="Base64-encoded image string for zero-disk transmission", example="data:image/jpeg;base64,/9j/4AAQSkZJRg...")

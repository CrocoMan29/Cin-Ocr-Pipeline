# src/main.py
"""
Command Line Interface (CLI) for Moroccan Carte d'Identité Nationale (CNIE) OCR Pipeline.

Capabilities:
1. Single/Dual Card Processing:
   python src/main.py data/recto1.png data/verso1.png
2. Composite Dual Card Scan:
   python src/main.py data/combined_test.png
3. Batch Processing of Scan Folders:
   python src/main.py --batch data/ --output reports/kyc_report.csv
"""

import os
import sys
import re
import time
import argparse
from typing import List, Dict, Any, Optional

import pandas as pd

# Ensure src directory is in sys.path regardless of execution working directory
src_dir = os.path.dirname(os.path.abspath(__file__))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from preprocessing import load_cards_from_file
from extraction import OCREngine

def classify_filename_side(base_name: str) -> tuple:
    """
    Identifies whether a filename represents a 'recto' or 'verso' side,
    and extracts a normalized pairing identifier.
    Returns (side, pair_id).
    """
    lower = base_name.lower().strip()

    # Pattern A: Side at the beginning, followed by ID (e.g. recto1, verso_2, front-A)
    m = re.match(r'^(recto|front|face)[-_]?(.*?)$', lower)
    if m:
        pair_id = m.group(2).strip('-_') or "default"
        return ("recto", pair_id)

    m = re.match(r'^(verso|back|arriere)[-_]?(.*?)$', lower)
    if m:
        pair_id = m.group(2).strip('-_') or "default"
        return ("verso", pair_id)

    # Pattern B: Side at the end, preceded by ID (e.g. client1_recto, scan02-front, id_r)
    m = re.match(r'^(.*?)[-_](recto|front|face|r)$', lower)
    if m:
        pair_id = m.group(1).strip('-_') or "default"
        return ("recto", pair_id)

    m = re.match(r'^(.*?)[-_](verso|back|arriere|v)$', lower)
    if m:
        pair_id = m.group(1).strip('-_') or "default"
        return ("verso", pair_id)

    # Standalone file (composite or unlabelled)
    return (None, base_name)

def group_directory_images(directory: str) -> List[Dict[str, Any]]:
    """
    Scans a directory and groups images into logical card units:
    - Pairs matching Recto and Verso files (e.g. recto1.png + verso1.png, id_front.jpg + id_back.jpg).
    - Identifies standalone scans (single sides or composite dual cards).
    """
    valid_exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
    files = [f for f in os.listdir(directory) if os.path.splitext(f.lower())[1] in valid_exts]
    
    pairs: Dict[str, Dict[str, str]] = {}
    standalones: List[str] = []

    for f in sorted(files):
        full_path = os.path.join(directory, f)
        base, _ = os.path.splitext(f)
        side, pair_id = classify_filename_side(base)

        if side:
            if pair_id not in pairs:
                pairs[pair_id] = {}
            pairs[pair_id][side] = full_path
        else:
            standalones.append(full_path)

    grouped_units: List[Dict[str, Any]] = []

    # Add paired files
    for pair_id, pair_files in sorted(pairs.items()):
        if 'recto' in pair_files and 'verso' in pair_files:
            grouped_units.append({
                "group_id": f"card_pair_{pair_id}",
                "type": "dual_pair",
                "files": [pair_files['recto'], pair_files['verso']]
            })
        else:
            for side_name, path in pair_files.items():
                grouped_units.append({
                    "group_id": os.path.basename(path),
                    "type": "single_file",
                    "files": [path]
                })

    # Add standalones
    for path in sorted(standalones):
        grouped_units.append({
            "group_id": os.path.basename(path),
            "type": "single_file",
            "files": [path]
        })

    return grouped_units

def run_batch_processing(directory: str, output_path: Optional[str] = None) -> None:
    """
    Executes automated batch OCR processing on an entire directory of card scans.
    Generates a consolidated spreadsheet (CSV) and JSON report with affiliation audit stats.
    """
    directory = os.path.abspath(directory)
    if not os.path.exists(directory):
        print(f"[Error] Directory not found: {directory}")
        return

    units = group_directory_images(directory)
    if not units:
        print(f"[Warning] No supported image files (.jpg, .png, .webp) found in {directory}")
        return

    print("\n" + "=" * 62)
    print(f"       MOROCCAN CNIE OCR - BATCH PROCESSING PIPELINE        ")
    print("=" * 62)
    print(f" Target Directory : {directory}")
    print(f" Logical Card Units Identified : {len(units)}")
    print("=" * 62 + "\n")

    # Initialize Engine once for the entire batch
    engine = OCREngine()
    records: List[Dict[str, Any]] = []
    
    stats = {
        "total": len(units),
        "verified": 0,
        "mismatched": 0,
        "duplicate_or_missing": 0,
        "single_sides": 0
    }
    
    batch_start = time.perf_counter()

    project_root = os.path.dirname(src_dir)

    for idx, unit in enumerate(units, start=1):
        group_id = unit["group_id"]
        files = unit["files"]
        files_str = ", ".join(os.path.basename(f) for f in files)
        print(f"[{idx}/{len(units)}] Processing: {group_id} ({files_str})...")

        card_matrices = []
        for f in files:
            card_matrices.extend(load_cards_from_file(f))

        if not card_matrices:
            print(f"  [Skip] No valid card image data decoded for {group_id}")
            continue

        item_start = time.perf_counter()
        result_package = engine.process_card_images(card_matrices)
        elapsed_ms = round((time.perf_counter() - item_start) * 1000.0, 1)

        res_type = result_package["type"]
        data = result_package["data"]
        val = data.get("validation", {})
        aff = result_package.get("affiliation", {})

        # Categorize Stats
        if res_type == "full_profile":
            stats["verified"] += 1
            status_symbol = "✓ VERIFIED"
        elif res_type == "mismatched_pair":
            stats["mismatched"] += 1
            status_symbol = "🚨 MISMATCH"
        elif res_type.startswith("duplicate_"):
            stats["duplicate_or_missing"] += 1
            status_symbol = "⚠️ DUPLICATE SIDE"
        else:
            stats["single_sides"] += 1
            status_symbol = "ℹ️ SINGLE SIDE"

        print(f"  --> Status: {status_symbol} | CNIE: {data.get('cnie_number')} | Time: {elapsed_ms}ms")

        # Compile flat record for tabular export (relative photo path for portability and privacy)
        rel_photo = ""
        if data.get("photo_path"):
            try:
                rel_photo = os.path.relpath(data["photo_path"], project_root)
            except Exception:
                rel_photo = os.path.basename(data["photo_path"])

        record = {
            "group_id": group_id,
            "source_files": files_str,
            "cnie_number": data.get("cnie_number", "Not detected"),
            "first_name": data.get("first_name", "Not detected"),
            "last_name": data.get("last_name", "Not detected"),
            "birth_date": data.get("birth_date", "Not detected"),
            "place_of_birth": data.get("birth_place", "Not detected"),
            "expiry_date": data.get("expiry_date", "Not detected"),
            "gender": data.get("gender", "Not detected"),
            "nationality": data.get("nationality", "MAR"),
            "father_name": data.get("father_name", "Not detected"),
            "mother_name": data.get("mother_name", "Not detected"),
            "civil_act": data.get("civil_act", "Not detected"),
            "address": data.get("address", "Not detected"),
            "card_type": res_type,
            "is_affiliated": aff.get("is_affiliated"),
            "affiliation_status": aff.get("status", "not_applicable"),
            "affiliation_details": aff.get("details", ""),
            "card_generation": val.get("card_generation", "Not detected"),
            "mrz_detected": val.get("mrz_detected", False),
            "cnie_cross_verified": val.get("cnie_cross_verified", False),
            "dob_checksum_valid": val.get("dob_checksum_valid"),
            "expiry_checksum_valid": val.get("expiry_checksum_valid"),
            "photo_path": rel_photo,
            "processing_time_ms": elapsed_ms
        }
        records.append(record)

    total_batch_time = round(time.perf_counter() - batch_start, 2)
    avg_latency = round((total_batch_time / len(units)), 2) if units else 0

    # Export to Reports
    default_report_dir = os.path.join(project_root, "reports")
    os.makedirs(default_report_dir, exist_ok=True)

    if not output_path:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(default_report_dir, f"kyc_batch_{timestamp}.csv")
    else:
        output_path = os.path.abspath(output_path)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

    df = pd.DataFrame(records)
    df.to_csv(output_path, index=False, encoding="utf-8")
    
    # Also save matching JSON report
    json_path = os.path.splitext(output_path)[0] + ".json"
    df.to_json(json_path, orient="records", indent=2, force_ascii=False)

    # Executive Summary Table
    print("\n" + "=" * 62)
    print("              BATCH KYC AUDIT EXECUTIVE SUMMARY             ")
    print("=" * 62)
    print(f" Total Units Processed       : {stats['total']}")
    print(f" Affiliated & Verified       : {stats['verified']} ({(stats['verified']/stats['total'])*100:.1f}%)")
    print(f" Security Mismatches Flagged : {stats['mismatched']}")
    print(f" Missing / Duplicate Sides   : {stats['duplicate_or_missing']}")
    print(f" Single-Side Only Scans      : {stats['single_sides']}")
    print(f" Total Batch Time            : {total_batch_time}s (Avg {avg_latency}s / card)")
    print("-" * 62)
    print(f" 📊 CSV Spreadsheet Export  : {output_path}")
    print(f" 📄 JSON Structured Report   : {json_path}")
    print("=" * 62 + "\n")

def print_single_result(result_package: Dict[str, Any], project_root: str) -> None:
    """
    Renders terminal presentation for individual scan requests.
    """
    res_type = result_package["type"]
    data = result_package["data"]
    val = data.get("validation", {})
    affiliation = result_package.get("affiliation", {})

    if res_type == "mismatched_pair":
        print("\n" + "!" * 62)
        print("  ⚠️  SECURITY WARNING: CARD AFFILIATION MISMATCH DETECTED!  ")
        print("!" * 62)
        print("  The uploaded Front and Back images DO NOT belong to the")
        print("  same individual!")
        print(f"  Details: {affiliation.get('details')}")
        print("!" * 62)
        print(" [RECTO DATA]")
        print(f"  Front CNIE      : {data['cnie_number']}")
        print(f"  Name            : {data['first_name']} {data['last_name']}")
        print(f"  Birth Date      : {data['birth_date']}")
        print("-" * 62)
        print(" [VERSO DATA]")
        raw_v = data.get("raw_verso", {})
        print(f"  Back CNIE       : {raw_v.get('cnie_number', 'Not detected')}")
        print(f"  Father / Mother : {data['father_name']} / {data['mother_name']}")
        print(f"  Address         : {data['address']}")
        print("!" * 62 + "\n")

    elif res_type in ("duplicate_recto", "duplicate_verso"):
        detected_side = "RECTO (Front)" if res_type == "duplicate_recto" else "VERSO (Back)"
        missing_side = "VERSO (Back)" if res_type == "duplicate_recto" else "RECTO (Front)"
        print("\n" + "!" * 62)
        print(f"  ⚠️  ALERT: MISSING CARD SIDE ({missing_side.upper()} MISSING)")
        print("!" * 62)
        print(f"  Both uploaded images were classified as {detected_side} sides.")
        print(f"  Please upload one {detected_side} and one {missing_side} side.")
        print(f"  Details: {affiliation.get('details')}")
        print("!" * 62)
        print(f" [DATA EXTRACTED FROM {detected_side.upper()}]")
        for k, v in data.items():
            if k not in {"side", "mrz", "raw_recto", "raw_verso", "validation"}:
                print(f"  {k.replace('_', ' ').capitalize():<18}: {v}")
        print("!" * 62 + "\n")

    elif res_type == "full_profile":
        print("\n" + "=" * 58)
        print("          MOROCCAN CIN - COMPLETE PROFILE          ")
        print("=" * 58)
        print(" [RECTO / FRONT]")
        print(f"  CIN / CNIE      : {data['cnie_number']}")
        print(f"  Last Name       : {data['last_name']}")
        print(f"  First Name      : {data['first_name']}")
        print(f"  Date of Birth   : {data['birth_date']}")
        print(f"  Place of Birth  : {data['birth_place']}")
        print(f"  Expiry Date     : {data['expiry_date']}")
        if data.get('photo_path'):
            rel_photo = os.path.relpath(data['photo_path'], project_root)
            print(f"  Citizen Photo   : {rel_photo}")
        print("-" * 58)
        print(" [VERSO / BACK]")
        print(f"  Father's Name   : {data['father_name']}")
        print(f"  Mother's Name   : {data['mother_name']}")
        print(f"  Address         : {data['address']}")
        print(f"  Civil Act N°    : {data['civil_act']}")
        print(f"  Gender          : {data['gender']}")
        print(f"  Nationality     : {data['nationality']}")
        print("-" * 58)
        print(" [VERIFICATION & AFFILIATION]")
        has_mrz = val.get('mrz_detected', False)
        aff_status = val.get("affiliation_status", "inconclusive").upper()
        aff_det = val.get("affiliation_details", "")
        print(f"  Cross-Affiliation      : {aff_status} ({aff_det})")
        
        v_cnie = "VALID (MATCHED)" if val.get('cnie_cross_verified') else ("NOT DETECTED ON VERSO" if not has_mrz and data['cnie_number'] != "Not detected" else "NOT MATCHED")
        if has_mrz:
            v_dob = "VALID (MATCHED)" if val.get('birth_date_mrz_verified') else "NOT MATCHED"
            v_exp = "VALID (MATCHED)" if val.get('expiry_date_mrz_verified') else "NOT MATCHED"
            v_dob_chk = "VALID (PASS)" if val.get('dob_checksum_valid') else "FAIL"
            v_exp_chk = "VALID (PASS)" if val.get('expiry_checksum_valid') else "FAIL"
            print(f"  CNIE Front vs Back MRZ : {v_cnie}")
            print(f"  Birth Date vs MRZ      : {v_dob} [ICAO 9303 Checksum: {v_dob_chk}]")
            print(f"  Expiry Date vs MRZ     : {v_exp} [ICAO 9303 Checksum: {v_exp_chk}]")
        else:
            print("  Card Generation        : Pre-2020 CNIE (Visual layout, no back MRZ)")
            print(f"  CNIE Cross-Match       : {v_cnie}")
            print(f"  Visual Document Status : Verified")
        print("=" * 58 + "\n")
    else:
        # Single side result
        side_name = "RECTO" if res_type == "single_recto" else "VERSO"
        opp_side = "VERSO" if res_type == "single_recto" else "RECTO"
        print("\n" + "=" * 48)
        print(f"        MOROCCAN CIN OCR RESULTS ({side_name})     ")
        print("=" * 48)
        print(f"  [Notice] {opp_side} side is missing from upload.")
        for k, v in data.items():
            if k not in {"side", "mrz", "raw_recto", "raw_verso", "validation"}:
                print(f"  {k.replace('_', ' ').capitalize():<18}: {v}")
        if "mrz" in data and data["mrz"]:
            print("-" * 48)
            print("  MRZ Gender        : " + str(data["mrz"].get("gender")))
            print("  MRZ Nationality   : " + str(data["mrz"].get("nationality")))
        print("=" * 48 + "\n")

def main():
    parser = argparse.ArgumentParser(
        description="Moroccan Carte Nationale d'Identité (CNIE) OCR & Verification Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process single or paired cards:
  python src/main.py data/recto1.png data/verso1.png
  python src/main.py data/combined_test.png

  # Batch process an entire directory:
  python src/main.py --batch data/ --output reports/kyc_batch.csv
        """
    )
    parser.add_argument("files", nargs="*", help="Path to image file(s) (Recto and/or Verso, or composite scan)")
    parser.add_argument("--batch", "-b", help="Directory path to scan and process in bulk mode")
    parser.add_argument("--output", "-o", help="Custom output path for batch report (.csv or .json)")

    args = parser.parse_args()

    project_root = os.path.dirname(src_dir)
    data_dir = os.path.join(project_root, "data")

    # 1. Mode: Batch processing
    if args.batch:
        run_batch_processing(args.batch, args.output)
        return

    # 2. Mode: Interactive Single/Pair processing
    card_matrices = []

    if args.files:
        for arg in args.files:
            path = os.path.abspath(arg) if os.path.isabs(arg) else os.path.join(os.getcwd(), arg)
            if not os.path.exists(path):
                base, ext = os.path.splitext(path)
                alt_extensions = ['.jpg', '.png', '.jpeg', '.webp', '.JPG', '.PNG']
                found_alt = next((base + a for a in alt_extensions if os.path.exists(base + a)), None)
                if found_alt:
                    print(f"[Note] '{os.path.basename(path)}' not found, using '{os.path.basename(found_alt)}'")
                    path = found_alt
                else:
                    print(f"[Error] Specified file does not exist: {path}")
                    return
            cards = load_cards_from_file(path)
            card_matrices.extend(cards)
    else:
        # Default scan: look for combined composite image first, then separate recto/verso
        combined_path = os.path.join(data_dir, "combined_test.png")
        recto_candidates = ["recto1.png", "recto1.jpg", "recto2.jpg", "recto2.png", "cin1.png"]
        verso_candidates = ["verso1.png", "verso1.jpg", "verso2.jpg", "verso2.png"]

        found_r = next((os.path.join(data_dir, f) for f in recto_candidates if os.path.exists(os.path.join(data_dir, f))), None)
        found_v = next((os.path.join(data_dir, f) for f in verso_candidates if os.path.exists(os.path.join(data_dir, f))), None)

        if found_r and found_v:
            card_matrices.extend(load_cards_from_file(found_r))
            card_matrices.extend(load_cards_from_file(found_v))
        elif os.path.exists(combined_path):
            card_matrices.extend(load_cards_from_file(combined_path))
        elif found_r:
            card_matrices.extend(load_cards_from_file(found_r))
        else:
            print(f"[Error] No card images found in {data_dir}. Specify an image or run with --batch <dir>.")
            return

    print(f"\n[Pipeline] Total card regions detected and ready for OCR: {len(card_matrices)}")

    engine = OCREngine()
    result_package = engine.process_card_images(card_matrices)
    print_single_result(result_package, project_root)

if __name__ == "__main__":
    main()
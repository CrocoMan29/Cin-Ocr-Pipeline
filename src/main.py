# src/main.py

import os
import sys

# Ensure src directory is in sys.path regardless of execution working directory
src_dir = os.path.dirname(os.path.abspath(__file__))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from preprocessing import load_cards_from_file
from extraction import OCREngine

def main():
    project_root = os.path.dirname(src_dir)
    data_dir = os.path.join(project_root, "data")

    # 1. Resolve image input paths from CLI arguments or default directory scan
    cli_args = sys.argv[1:]
    card_matrices = []

    if cli_args:
        # User specified file(s) on CLI
        for arg in cli_args:
            path = os.path.abspath(arg) if os.path.isabs(arg) else os.path.join(os.getcwd(), arg)
            if not os.path.exists(path):
                # Try common image extensions if user typed wrong extension
                base, ext = os.path.splitext(path)
                alt_extensions = ['.jpg', '.png', '.jpeg', '.webp', '.JPG', '.PNG']
                found_alt = None
                for alt_ext in alt_extensions:
                    alt_path = base + alt_ext
                    if os.path.exists(alt_path):
                        found_alt = alt_path
                        break
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
            print(f"[Error] No card images found in {data_dir}")
            return

    print(f"\n[Pipeline] Total card regions detected and ready for OCR: {len(card_matrices)}")

    # 2. Run OCR Engine with auto side-classification & MRZ verification
    engine = OCREngine()
    result_package = engine.process_card_images(card_matrices)

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

if __name__ == "__main__":
    main()
import os
import re
import cv2
import easyocr
import numpy as np

def extract_id_photo(recto_image: np.ndarray, name_bbox_x: float = None, save_path: str = None) -> tuple:
    """
    Extracts the citizen's portrait from a Moroccan CNIE (Front / Recto).
    Auto-detects layout:
      - Post-2020 CNIE: Photo is on the left side
      - Pre-2020 CNIE: Photo is on the right side
    """
    h, w = recto_image.shape[:2]

    # If text is on the left (x < 35% of width), photo is on the right
    is_pre_2020 = (name_bbox_x is not None) and ((name_bbox_x / float(w)) < 0.35)

    if is_pre_2020:
        y1, y2 = int(h * 0.15), int(h * 0.85)
        x1, x2 = int(w * 0.62), int(w * 0.98)
    else:
        y1, y2 = int(h * 0.16), int(h * 0.88)
        x1, x2 = int(w * 0.02), int(w * 0.38)

    photo_crop = recto_image[y1:y2, x1:x2]

    if save_path:
        os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
        to_save = cv2.cvtColor(photo_crop, cv2.COLOR_RGB2BGR) if len(photo_crop.shape) == 3 else photo_crop
        cv2.imwrite(save_path, to_save)

    return photo_crop, save_path

def mrz_char_value(c: str) -> int:
    """ICAO 9303 character values for MRZ checksum."""
    if c.isdigit():
        return int(c)
    elif c.isalpha():
        return ord(c.upper()) - ord('A') + 10
    return 0

def compute_mrz_checksum(data_str: str) -> int:
    """Computes ICAO 9303 7-3-1 modulus 10 check digit."""
    weights = [7, 3, 1]
    total = 0
    for idx, ch in enumerate(data_str):
        total += mrz_char_value(ch) * weights[idx % 3]
    return total % 10

def repair_numeric_field(field_str: str) -> str:
    """Fixes typical OCR character confusions in numeric zones."""
    subs = {
        'O': '0', 'o': '0', 'Q': '0',
        'I': '1', 'i': '1', 'l': '1', 'L': '1',
        'Z': '2', 'z': '2',
        'S': '5', 's': '5',
        'B': '8', 'b': '8'
    }
    return "".join(subs.get(ch, ch) for ch in field_str)

def clean_cnie_number(raw_text: str) -> str:
    """Normalizes CNIE number: 1-2 letters prefix + 4-8 digits."""
    match = re.search(r'\b([A-Z]{1,2})\s*([0-9A-Za-z]{4,8})\b', raw_text.strip().upper())
    if match:
        prefix = match.group(1)
        suffix = repair_numeric_field(match.group(2))
        return f"{prefix}{suffix}"
    return raw_text.replace(' ', '')

class OCREngine:
    def __init__(self, languages=None, use_gpu=False):
        if languages is None:
            # Moroccan CIN Latin script (French/English)
            languages = ['en', 'fr']
        print(f"[Extraction] Initializing EasyOCR Engine for {languages} (use_gpu={use_gpu})...")
        self.reader = easyocr.Reader(languages, gpu=use_gpu)

    def classify_card_side(self, raw_results: list) -> str:
        """
        Classifies an OCR result as 'recto' (front) or 'verso' (back)
        based on visual keywords and MRZ presence.
        """
        recto_keywords = {'ROYAUME', 'MAROC', 'CARTE', 'NATIONALE', 'IDENTITE', 'DIDENTITE', 'SPECIMEN', 'VALABLE'}
        verso_keywords = {'IDMAR', 'FILS', 'FILLE', 'ADRESSE', 'AESSE', 'ETAT', 'CIVIL'}

        recto_score = 0
        verso_score = 0

        for _, text, _ in raw_results:
            upper = text.strip().upper()
            if '<<<' in upper or 'MAR<<<' in upper or upper.startswith('I<MAR'):
                verso_score += 5
            for kw in recto_keywords:
                if kw in upper:
                    recto_score += 2
            for kw in verso_keywords:
                if kw in upper:
                    verso_score += 2

        if verso_score > recto_score:
            return "verso"
        return "recto"

    def extract_recto(self, image_matrix: np.ndarray, pre_results: list = None) -> dict:
        """
        Extracts front-side (Recto) fields:
        CNIE number, Full Name, Date of Birth, Place of Birth, Expiry Date.
        """
        print("[Extraction] Running OCR on Recto (front) image...")
        raw_results = pre_results if pre_results is not None else self.reader.readtext(image_matrix)

        header_keywords = {'ROYAUME', 'MAROC', 'CARTE', 'NATIONALE', 'IDENTITE', 'DIDENTITE', 'SPECIMEN', 'CAMSCANNER', 'SCANNED'}
        
        cin_number = None
        dates = []
        name_candidates = []
        name_x_coords = []
        birth_place = None

        for bbox, text, prob in raw_results:
            cleaned = text.strip()
            upper = cleaned.upper()

            if any(h in upper for h in header_keywords):
                continue

            # 1. Date Extraction (handle slashes, dots, dashes, or OCR misreads)
            date_match = re.search(r'\b(\d{2})[/.-]?(\d{2})[/1I.-]?(19\d{2}|20\d{2})\b', cleaned)
            if date_match:
                formatted_date = f"{date_match.group(1)}/{date_match.group(2)}/{date_match.group(3)}"
                dates.append(formatted_date)
                continue

            # 2. CIN Number Extraction (1-2 letters + 4-8 digits, e.g. AS3919, U1234567, confidence > 0.40)
            cin_match = re.search(r'\b([A-Za-z]{1,2}\s*[0-9A-Za-z]{4,8})\b', cleaned)
            if prob > 0.40 and cin_match and not cin_number:
                cand_cnie = clean_cnie_number(cin_match.group(1))
                if re.match(r'^[A-Z]{1,2}\d{4,8}$', cand_cnie):
                    cin_number = cand_cnie
                    continue

            # 3. Explicit Place of Birth (e.g. "à TAZA", "a OUARZAZATE")
            place_match = re.search(r'^[aàAÀ]\s+([A-Za-z\s\'-]+)$', cleaned)
            if place_match and not birth_place:
                cand_place = place_match.group(1).strip()
                if not any(k in cand_place.upper() for k in ['VALABLE', 'JUSQU', 'MAROC']):
                    birth_place = cand_place
                    continue

            # 4. Names extraction (Latin letters only, confidence > 0.35)
            if prob > 0.35 and re.match(r'^[A-Za-z\s\'-]+$', cleaned):
                word_clean = cleaned.strip()
                if len(word_clean) > 2 and not any(w in upper for w in ['ROYAUME', 'MAROC', 'CARTE', 'IDENTITE', 'VALABLE', 'JUSQU', 'CAMSCANNER', 'SCANNED']):
                    if not dates and word_clean not in name_candidates:
                        name_candidates.append(word_clean)
                        min_x = min(pt[0] for pt in bbox)
                        name_x_coords.append(min_x)
                    elif dates and not birth_place:
                        cand_bp = re.sub(r'^[aàAÀ]\s+', '', word_clean).strip()
                        if not any(k in cand_bp.upper() for k in ['VALABLE', 'JUSQU', 'CAMSCANNER']):
                            birth_place = cand_bp

        last_name = name_candidates[0] if len(name_candidates) > 0 else "Not detected"
        first_name = name_candidates[1] if len(name_candidates) > 1 else "Not detected"
        birth_date = dates[0] if len(dates) > 0 else "Not detected"
        expiry_date = dates[1] if len(dates) > 1 else "Not detected"

        # 5. Automatically Crop and Save Citizen Photo
        primary_name_x = name_x_coords[0] if name_x_coords else None
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        safe_cnie = (cin_number or "unknown").replace("/", "_")
        photo_save_path = os.path.join(project_root, "data", "extracted_faces", f"photo_{safe_cnie}.jpg")
        _, saved_path = extract_id_photo(image_matrix, name_bbox_x=primary_name_x, save_path=photo_save_path)

        return {
            "cnie_number": cin_number or "Not detected",
            "last_name": last_name,
            "first_name": first_name,
            "birth_date": birth_date,
            "birth_place": birth_place or "Not detected",
            "expiry_date": expiry_date,
            "photo_path": saved_path,
            "side": "recto"
        }

    # Backward compatibility alias
    def extract_cin_data(self, image_matrix: np.ndarray) -> dict:
        return self.extract_recto(image_matrix)

    def parse_mrz(self, mrz_lines: list) -> dict:
        """
        Parses Moroccan 3-line TD1 Machine Readable Zone (MRZ)
        with ICAO 9303 checksum verification and digit repair.
        """
        if len(mrz_lines) < 3:
            return {}

        l1 = mrz_lines[0].replace(' ', '').upper()
        l2 = mrz_lines[1].replace(' ', '').upper()
        l3 = mrz_lines[2].replace(' ', '').upper()

        # Parse Line 2: YYMMDD[Check][Sex][YYMMDD][Check][Nationality]
        l2_match = re.search(r'([0-9A-Za-z]{6})([0-9A-Za-z])?([MF<])([0-9A-Za-z]{6})([0-9A-Za-z])?([A-Z]{3})?', l2)
        birth_date = None
        expiry_date = None
        gender = None
        nationality = "MAR"
        dob_checksum_valid = False
        exp_checksum_valid = False

        if l2_match:
            raw_dob = repair_numeric_field(l2_match.group(1))
            dob_check = repair_numeric_field(l2_match.group(2) or '')
            raw_sex = l2_match.group(3)
            raw_exp = repair_numeric_field(l2_match.group(4))
            exp_check = repair_numeric_field(l2_match.group(5) or '')
            nationality = l2_match.group(6) or "MAR"

            # Verify Checksums (ICAO 9303)
            if dob_check and dob_check.isdigit():
                dob_checksum_valid = (compute_mrz_checksum(raw_dob) == int(dob_check))
            if exp_check and exp_check.isdigit():
                exp_checksum_valid = (compute_mrz_checksum(raw_exp) == int(exp_check))

            yy, mm, dd = raw_dob[:2], raw_dob[2:4], raw_dob[4:6]
            century = "19" if int(yy) > 40 else "20"
            birth_date = f"{dd}/{mm}/{century}{yy}"

            eyy, emm, edd = raw_exp[:2], raw_exp[2:4], raw_exp[4:6]
            expiry_date = f"{edd}/{emm}/20{eyy}"

            gender = "Female" if raw_sex == "F" else ("Male" if raw_sex == "M" else "Unspecified")

        # Parse Line 3 (Names)
        name_parts = [p.replace('<', ' ').strip() for p in l3.split('<<') if p.replace('<', '').strip()]
        last_name = name_parts[0] if len(name_parts) > 0 else None
        first_name = name_parts[1] if len(name_parts) > 1 else None

        # Parse CNIE from Line 1
        cnie_match = re.search(r'([A-Z]{1,2}[0-9A-Za-z]{5,8})', l1)
        cnie_number = clean_cnie_number(cnie_match.group(1)) if cnie_match else None

        return {
            "mrz_valid": True,
            "cnie_number": cnie_number,
            "birth_date": birth_date,
            "expiry_date": expiry_date,
            "gender": gender,
            "nationality": nationality,
            "last_name": last_name,
            "first_name": first_name,
            "dob_checksum_valid": dob_checksum_valid,
            "expiry_checksum_valid": exp_checksum_valid,
            "raw_lines": [l1, l2, l3]
        }

    def extract_verso(self, image_matrix: np.ndarray, pre_results: list = None) -> dict:
        """
        Extracts back-side (Verso) fields:
        Father's Name, Mother's Name, Multi-line Address, Civil Status number, and MRZ data.
        """
        print("[Extraction] Running OCR on Verso (back) image...")
        raw_results = pre_results if pre_results is not None else self.reader.readtext(image_matrix)

        father_name = None
        mother_name = None
        address_parts = []
        is_collecting_address = False
        civil_act = None
        cin_number = None
        mrz_lines = []

        last_was_father_label = False
        last_was_mother_label = False
        last_was_sexe_label = False
        visual_gender = None

        for bbox, text, prob in raw_results:
            cleaned = text.strip()
            upper = cleaned.upper()

            # 1. Identify MRZ lines
            if '<<<' in upper or upper.startswith('I<MAR') or re.search(r'\d{6,}[MF<]\d{6,}', upper.replace(' ', '')):
                mrz_lines.append(cleaned)
                is_collecting_address = False
                continue

            # 2. CNIE number on verso (4-8 digits, e.g. AS3919, U1234567, confidence > 0.40)
            c_match = re.search(r'\b([A-Za-z]{1,2}\s*[0-9A-Za-z]{4,8})\b', cleaned)
            if prob > 0.40 and c_match and not cin_number and not any(k in upper for k in ['VALABLE', 'SEXE', 'LOT', 'NUM', 'CIVIL']):
                cand_cnie = clean_cnie_number(c_match.group(1))
                if re.match(r'^[A-Z]{1,2}\d{4,8}$', cand_cnie):
                    cin_number = cand_cnie

            # 3. Civil Status registration number (e.g. 1234/5678/1983 or 364/2000)
            act_match = re.search(r'\b(\d{1,4}/\d{1,4}(?:/\d{4})?)\b', cleaned)
            if act_match and not civil_act:
                civil_act = act_match.group(1)

            # 4. Visual Sexe/Gender (pre-2020 CNIE)
            if re.match(r'^sexe\b', cleaned, re.IGNORECASE):
                last_was_sexe_label = True
                continue
            if last_was_sexe_label and not visual_gender:
                if cleaned.upper() in ['M', 'F']:
                    visual_gender = "Male" if cleaned.upper() == 'M' else "Female"
                last_was_sexe_label = False
                continue

            # 5. Father's name
            # Case A: Standalone label (e.g. "Fils de")
            if re.match(r'^fils?\s+de\b', cleaned, re.IGNORECASE):
                last_was_father_label = True
                continue
            if last_was_father_label and not father_name:
                father_name = cleaned
                last_was_father_label = False
                continue

            # Case B: Inline label (e.g. "Fils de LARBI...")
            f_match = re.search(r'(?:F[i1l]{1,2}(?:s|le|e)?\s*(?:de)?|(?<=\b)de)\s+([A-Za-z\s]{3,})', cleaned, re.IGNORECASE)
            if f_match and not father_name:
                candidate = f_match.group(1).strip()
                if candidate.upper() not in {'MAROC', 'IDENTITE', 'CARTE', 'CAMSCANNER'}:
                    father_name = candidate
                    continue

            # 6. Mother's name handling
            if re.match(r'^(?:et\s+de|e[il1]d(?:\s*de)?)$', cleaned, re.IGNORECASE):
                last_was_mother_label = True
                continue
            m_match = re.search(r'(?:et\s+de|e[il1]d(?:\s*de)?)\s+([A-Za-z\s]{3,})', cleaned, re.IGNORECASE)
            if m_match and not mother_name:
                mother_name = m_match.group(1).strip()
                continue
            if last_was_mother_label and not mother_name:
                if re.match(r'^[A-Za-z\s\'-]{3,}$', cleaned) and not any(w in upper for w in ['NUM', 'LOT', 'AV', 'RUE', 'ADRESSE']):
                    mother_name = cleaned
                    last_was_mother_label = False
                    continue
            if 'BENT' in upper and not mother_name and cleaned != father_name:
                mother_name = cleaned
                continue

            # 7. Multi-line Address Accumulation
            is_parent_or_act = bool(act_match or re.search(r'\b(?:fils|fille|et\s+de|eid|eld|sexe|etat|état)\b', cleaned, re.IGNORECASE))
            is_addr_start = (
                re.search(r'^(?:ADRESSE|AESSE|ACESSE|AEAA|ADR)\b', cleaned, re.IGNORECASE)
                or re.search(r'\b(?:NUM\s*\d+|LOT\s+[A-Za-z0-9]+|(?:RUE|BOULEVARD|BD|AVENUE|RESIDENCE|DOUAR|QUARTIER)\s+[A-Za-z]|AV\s+[A-Z])\b', cleaned)
            )

            if is_addr_start and not is_parent_or_act and not is_collecting_address:
                clean_first = re.sub(r'^(?:ADRESSE|AESSE|ACESSE|AEAA|ADRE|ADR)\s*', '', cleaned, flags=re.IGNORECASE).strip()
                if clean_first:
                    address_parts.append(clean_first)
                is_collecting_address = True
                continue

            if is_collecting_address:
                if is_parent_or_act or len(cleaned) < 2 or '<<<' in upper or 'CAMSCANNER' in upper or 'ETAT' in upper or 'ÉTAT' in upper:
                    is_collecting_address = False
                else:
                    address_parts.append(cleaned)

        mrz_data = self.parse_mrz(mrz_lines) if len(mrz_lines) >= 3 else {}
        full_address = " ".join(address_parts).strip() if address_parts else "Not detected"

        return {
            "cnie_number": cin_number or mrz_data.get("cnie_number") or "Not detected",
            "father_name": father_name or "Not detected",
            "mother_name": mother_name or "Not detected",
            "address": full_address,
            "civil_act": civil_act or "Not detected",
            "visual_gender": visual_gender,
            "mrz": mrz_data,
            "side": "verso"
        }

    def extract_full_card(self, recto_matrix: np.ndarray, verso_matrix: np.ndarray) -> dict:
        """
        Combines Recto and Verso extraction into a single verified identity record.
        Cross-validates fields between visual inspection and MRZ.
        """
        recto = self.extract_recto(recto_matrix)
        verso = self.extract_verso(verso_matrix)
        mrz = verso.get("mrz", {})

        # Validation checks
        cnie_match = (
            recto["cnie_number"] != "Not detected"
            and verso["cnie_number"] != "Not detected"
            and recto["cnie_number"] == verso["cnie_number"]
        )

        dob_match = (
            recto["birth_date"] != "Not detected"
            and mrz.get("birth_date") is not None
            and recto["birth_date"] == mrz.get("birth_date")
        )

        expiry_match = (
            recto["expiry_date"] != "Not detected"
            and mrz.get("expiry_date") is not None
            and recto["expiry_date"] == mrz.get("expiry_date")
        )

        return {
            "cnie_number": recto["cnie_number"],
            "last_name": recto["last_name"],
            "first_name": recto["first_name"],
            "gender": mrz.get("gender") or verso.get("visual_gender") or "Not detected",
            "nationality": mrz.get("nationality", "MAR"),
            "birth_date": recto["birth_date"],
            "birth_place": recto["birth_place"],
            "expiry_date": recto["expiry_date"],
            "photo_path": recto.get("photo_path"),
            "father_name": verso["father_name"],
            "mother_name": verso["mother_name"],
            "address": verso["address"],
            "civil_act": verso["civil_act"],
            "validation": {
                "cnie_cross_verified": cnie_match,
                "birth_date_mrz_verified": dob_match,
                "expiry_date_mrz_verified": expiry_match,
                "dob_checksum_valid": mrz.get("dob_checksum_valid", False),
                "expiry_checksum_valid": mrz.get("expiry_checksum_valid", False),
                "mrz_detected": bool(mrz)
            },
            "raw_recto": recto,
            "raw_verso": verso
        }

    def process_card_images(self, card_matrices: list) -> dict:
        """
        Automatic card side identification and routing:
        Handles 1 or 2 card images regardless of user ordering or orientation.
        """
        if not card_matrices:
            raise ValueError("No card images provided to process.")

        if len(card_matrices) == 1:
            raw = self.reader.readtext(card_matrices[0])
            side = self.classify_card_side(raw)
            print(f"[Extraction] Auto-detected card side: {side.upper()}")
            if side == "verso":
                return {"type": "single_verso", "data": self.extract_verso(card_matrices[0], pre_results=raw)}
            return {"type": "single_recto", "data": self.extract_recto(card_matrices[0], pre_results=raw)}

        # Two card matrices (from composite image or 2 separate uploads)
        raw_1 = self.reader.readtext(card_matrices[0])
        side_1 = self.classify_card_side(raw_1)

        raw_2 = self.reader.readtext(card_matrices[1])
        side_2 = self.classify_card_side(raw_2)

        print(f"[Extraction] Card 1 auto-classified as: {side_1.upper()}")
        print(f"[Extraction] Card 2 auto-classified as: {side_2.upper()}")

        if side_1 == "verso" and side_2 == "recto":
            # Inverted upload order: automatically swap!
            recto_mat, recto_raw = card_matrices[1], raw_2
            verso_mat, verso_raw = card_matrices[0], raw_1
        else:
            recto_mat, recto_raw = card_matrices[0], raw_1
            verso_mat, verso_raw = card_matrices[1], raw_2

        recto_data = self.extract_recto(recto_mat, pre_results=recto_raw)
        verso_data = self.extract_verso(verso_mat, pre_results=verso_raw)
        mrz = verso_data.get("mrz", {})

        cnie_match = (
            recto_data["cnie_number"] != "Not detected"
            and verso_data["cnie_number"] != "Not detected"
            and recto_data["cnie_number"] == verso_data["cnie_number"]
        )

        dob_match = (
            recto_data["birth_date"] != "Not detected"
            and mrz.get("birth_date") is not None
            and recto_data["birth_date"] == mrz.get("birth_date")
        )

        expiry_match = (
            recto_data["expiry_date"] != "Not detected"
            and mrz.get("expiry_date") is not None
            and recto_data["expiry_date"] == mrz.get("expiry_date")
        )

        return {
            "type": "full_profile",
            "data": {
                "cnie_number": recto_data["cnie_number"],
                "last_name": recto_data["last_name"],
                "first_name": recto_data["first_name"],
                "gender": mrz.get("gender") or verso_data.get("visual_gender") or "Not detected",
                "nationality": mrz.get("nationality", "MAR"),
                "birth_date": recto_data["birth_date"],
                "birth_place": recto_data["birth_place"],
                "expiry_date": recto_data["expiry_date"],
                "photo_path": recto_data.get("photo_path"),
                "father_name": verso_data["father_name"],
                "mother_name": verso_data["mother_name"],
                "address": verso_data["address"],
                "civil_act": verso_data["civil_act"],
                "validation": {
                    "cnie_cross_verified": cnie_match,
                    "birth_date_mrz_verified": dob_match,
                    "expiry_date_mrz_verified": expiry_match,
                    "dob_checksum_valid": mrz.get("dob_checksum_valid", False),
                    "expiry_checksum_valid": mrz.get("expiry_checksum_valid", False),
                    "mrz_detected": bool(mrz)
                },
                "raw_recto": recto_data,
                "raw_verso": verso_data
            }
        }
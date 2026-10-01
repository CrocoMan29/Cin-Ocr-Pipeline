import os
import cv2
import numpy as np

def estimate_blur(image: np.ndarray, threshold: float = 60.0) -> tuple[float, bool]:
    """
    Computes Laplacian variance to estimate image sharpness.
    Returns (variance_score, is_blurry).
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    variance = cv2.Laplacian(gray, cv2.CV_64F).var()
    return float(variance), bool(variance < threshold)

def split_cards_if_composite(image: np.ndarray) -> list[np.ndarray]:
    """
    Detects if an image contains both Recto and Verso cards (e.g. photocopy or scan)
    and splits them into individual card images.
    Returns a list of 1 or 2 card images.
    """
    h, w = image.shape[:2]
    aspect = w / float(h)
    
    # 1. Try contour-based card detection
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)
    
    thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 4
    )
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
    closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=3)
    
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    img_area = float(h * w)
    
    card_boxes = []
    for c in contours:
        area = cv2.contourArea(c)
        if area > 0.08 * img_area:
            bx, by, bw, bh = cv2.boundingRect(c)
            b_aspect = bw / float(bh)
            # Standard ID-1 card aspect ratio is ~1.58, allow rotated/skewed ~0.45 to 2.3
            if 0.45 <= b_aspect <= 2.3:
                card_boxes.append((by, bx, bw, bh))
                
    if len(card_boxes) == 2:
        print("[Preprocessing] Detected 2 distinct card regions via contours. Splitting...")
        card_boxes.sort() # Top-to-bottom
        cards = []
        for by, bx, bw, bh in card_boxes:
            pad_y = int(bh * 0.02)
            pad_x = int(bw * 0.02)
            y1 = max(0, by - pad_y)
            y2 = min(h, by + bh + pad_y)
            x1 = max(0, bx - pad_x)
            x2 = min(w, bx + bw + pad_x)
            cards.append(image[y1:y2, x1:x2])
        return cards
        
    # 2. Heuristic split based on aspect ratio:
    # Very tall image (e.g. A4 scan with 2 cards stacked vertically)
    if aspect < 0.95:
        print("[Preprocessing] Detected vertical composite layout (aspect < 0.95). Splitting top/bottom...")
        mid_y = h // 2
        return [image[0:mid_y, 0:w], image[mid_y:h, 0:w]]
        
    # Very wide image (2 cards placed side-by-side)
    if aspect > 2.3:
        print("[Preprocessing] Detected horizontal composite layout (aspect > 2.3). Splitting left/right...")
        mid_x = w // 2
        return [image[0:h, 0:mid_x], image[0:h, mid_x:w]]
        
    return [image]

def prepare_image_for_ocr(image: np.ndarray) -> np.ndarray:
    """
    Standardizes image format and resizes for optimal EasyOCR accuracy:
    - Handles RGBA (4 channels) or Grayscale (1 channel) safely.
    - Conditionally upscales if width < 1200px (avoids bloating high-res photos).
    - Converts to RGB format.
    """
    # Safe color conversion
    if len(image.shape) == 2:
        bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    elif image.shape[2] == 4:
        bgr = cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
    else:
        bgr = image

    # Dynamic scaling
    h, w = bgr.shape[:2]
    if w < 1200:
        scale = 1200.0 / w
        bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    # Convert BGR to RGB for EasyOCR
    rgb_image = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    return rgb_image

def load_cards_from_file(image_path: str) -> list[np.ndarray]:
    """
    Loads an image file, detects if it contains both sides (composite),
    splits if necessary, and returns a list of prepared RGB numpy matrices.
    """
    print(f"[Preprocessing] Loading image: {image_path}")
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found at path: {image_path}")
        
    raw = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
    if raw is None:
        raise ValueError(f"Failed to read image at: {image_path}")

    # Blur check
    variance, is_blurry = estimate_blur(raw)
    if is_blurry:
        print(f"[Preprocessing] Warning: Image may be blurry (sharpness score: {variance:.1f})")

    # Split if composite
    card_sub_images = split_cards_if_composite(raw)
    
    # Preprocess each card
    return [prepare_image_for_ocr(c) for c in card_sub_images]

def clean_image_for_ocr(image_path: str) -> np.ndarray:
    """
    Backward-compatible single image loader.
    """
    cards = load_cards_from_file(image_path)
    return cards[0]
// static/app.js
/**
 * Moroccan CNIE OCR & KYC Verification Frontend
 * Handles interactive dual-dropzone uploads, client-side blur diagnostics,
 * FastAPI microservice integration, and visual affiliation alerts.
 */

document.addEventListener('DOMContentLoaded', () => {
  // 1. State Management
  const state = {
    mode: 'dual', // 'dual' | 'composite'
    rectoFile: null,
    versoFile: null,
    singleFile: null,
    latestResult: null,
    theme: localStorage.getItem('cnie_theme') || 'dark'
  };

  // 2. DOM Elements
  const themeToggle = document.getElementById('themeToggle');
  const themeIcon = document.getElementById('themeIcon');
  const tabDual = document.getElementById('tabDual');
  const tabComposite = document.getElementById('tabComposite');
  const dualUploadZone = document.getElementById('dualUploadZone');
  const compositeUploadZone = document.getElementById('compositeUploadZone');

  // Dropzones & Inputs
  const rectoDropzone = document.getElementById('rectoDropzone');
  const rectoInput = document.getElementById('rectoInput');
  const rectoPlaceholder = document.getElementById('rectoPlaceholder');
  const rectoPreview = document.getElementById('rectoPreview');
  const rectoImg = document.getElementById('rectoImg');
  const rectoRemove = document.getElementById('rectoRemove');
  const rectoQuality = document.getElementById('rectoQuality');

  const versoDropzone = document.getElementById('versoDropzone');
  const versoInput = document.getElementById('versoInput');
  const versoPlaceholder = document.getElementById('versoPlaceholder');
  const versoPreview = document.getElementById('versoPreview');
  const versoImg = document.getElementById('versoImg');
  const versoRemove = document.getElementById('versoRemove');
  const versoQuality = document.getElementById('versoQuality');

  const singleDropzone = document.getElementById('singleDropzone');
  const singleInput = document.getElementById('singleInput');
  const singlePlaceholder = document.getElementById('singlePlaceholder');
  const singlePreview = document.getElementById('singlePreview');
  const singleImg = document.getElementById('singleImg');
  const singleRemove = document.getElementById('singleRemove');
  const singleQuality = document.getElementById('singleQuality');

  const chkBase64 = document.getElementById('chkBase64');
  const btnExtract = document.getElementById('btnExtract');
  const btnSpinner = document.getElementById('btnSpinner');
  const btnText = document.getElementById('btnText');

  // Results elements
  const emptyState = document.getElementById('emptyState');
  const resultsWrapper = document.getElementById('resultsWrapper');
  const affiliationBanner = document.getElementById('affiliationBanner');
  const affIcon = document.getElementById('affIcon');
  const affTitle = document.getElementById('affTitle');
  const affDetails = document.getElementById('affDetails');
  const latencyBadge = document.getElementById('latencyBadge');

  const resPhoto = document.getElementById('resPhoto');
  const resCardGen = document.getElementById('resCardGen');
  const valCnie = document.getElementById('valCnie');
  const valGenderNat = document.getElementById('valGenderNat');
  const valLastName = document.getElementById('valLastName');
  const valFirstName = document.getElementById('valFirstName');
  const valBirthDate = document.getElementById('valBirthDate');
  const valBirthPlace = document.getElementById('valBirthPlace');
  const valExpiryDate = document.getElementById('valExpiryDate');
  const valCardType = document.getElementById('valCardType');

  const valFather = document.getElementById('valFather');
  const valMother = document.getElementById('valMother');
  const valCivilAct = document.getElementById('valCivilAct');
  const valAddress = document.getElementById('valAddress');

  const pillCnie = document.getElementById('pillCnie');
  const pillDob = document.getElementById('pillDob');
  const pillExp = document.getElementById('pillExp');
  const pillDobChk = document.getElementById('pillDobChk');
  const pillExpChk = document.getElementById('pillExpChk');

  const btnCopyJson = document.getElementById('btnCopyJson');
  const btnDownloadJson = document.getElementById('btnDownloadJson');
  const btnReset = document.getElementById('btnReset');
  const toastMessage = document.getElementById('toastMessage');

  // 3. Theme Toggle Setup
  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    themeIcon.textContent = (theme === 'dark') ? '☀️' : '🌙';
    localStorage.setItem('cnie_theme', theme);
    state.theme = theme;
  }
  applyTheme(state.theme);

  themeToggle.addEventListener('click', () => {
    applyTheme(state.theme === 'dark' ? 'light' : 'dark');
  });

  // 4. Tab Mode Switching
  tabDual.addEventListener('click', () => {
    state.mode = 'dual';
    tabDual.classList.add('active');
    tabComposite.classList.remove('active');
    dualUploadZone.style.display = 'grid';
    compositeUploadZone.style.display = 'none';
    updateExtractButtonState();
  });

  tabComposite.addEventListener('click', () => {
    state.mode = 'composite';
    tabComposite.classList.add('active');
    tabDual.classList.remove('active');
    dualUploadZone.style.display = 'none';
    compositeUploadZone.style.display = 'block';
    updateExtractButtonState();
  });

  // 5. Client-Side Image Sharpness Estimation via Canvas
  function estimateImageSharpness(imgElement, callback) {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    const w = 120;
    const h = 80;
    canvas.width = w;
    canvas.height = h;

    ctx.drawImage(imgElement, 0, 0, w, h);
    const imgData = ctx.getImageData(0, 0, w, h);
    const data = imgData.data;

    let edgeSum = 0;
    for (let i = 0; i < data.length - 4; i += 4) {
      const g1 = (data[i] + data[i+1] + data[i+2]) / 3;
      const g2 = (data[i+4] + data[i+5] + data[i+6]) / 3;
      edgeSum += Math.abs(g1 - g2);
    }
    const avgEdge = edgeSum / (w * h);
    const isSharp = avgEdge > 4.5;
    callback(isSharp);
  }

  // 6. Dropzone Setup Function
  function setupDropzone(dropzone, input, placeholder, preview, img, removeBtn, qualityBadge, fileKey) {
    // Click to upload
    dropzone.addEventListener('click', (e) => {
      if (e.target !== removeBtn) {
        input.click();
      }
    });

    // Drag events
    ['dragenter', 'dragover'].forEach(name => {
      dropzone.addEventListener(name, (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
      });
    });

    ['dragleave', 'drop'].forEach(name => {
      dropzone.addEventListener(name, (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
      });
    });

    dropzone.addEventListener('drop', (e) => {
      if (e.dataTransfer.files && e.dataTransfer.files[0]) {
        handleFileSelection(e.dataTransfer.files[0], fileKey, placeholder, preview, img, qualityBadge);
      }
    });

    input.addEventListener('change', () => {
      if (input.files && input.files[0]) {
        handleFileSelection(input.files[0], fileKey, placeholder, preview, img, qualityBadge);
      }
    });

    removeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      state[fileKey] = null;
      input.value = '';
      preview.classList.remove('active');
      placeholder.style.display = 'block';
      updateExtractButtonState();
    });
  }

  function handleFileSelection(file, fileKey, placeholder, preview, img, qualityBadge) {
    if (!file.type.match(/image\/(jpeg|png|webp)/)) {
      showToast('Unsupported format. Please upload JPEG, PNG, or WebP.', 'error');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      showToast('File size exceeds maximum 10MB limit.', 'error');
      return;
    }

    state[fileKey] = file;
    const reader = new FileReader();
    reader.onload = (e) => {
      img.src = e.target.result;
      img.onload = () => {
        estimateImageSharpness(img, (isSharp) => {
          if (isSharp) {
            qualityBadge.className = 'quality-badge sharp';
            qualityBadge.textContent = '✓ Sharp Image';
          } else {
            qualityBadge.className = 'quality-badge blurry';
            qualityBadge.textContent = '⚠️ Low Sharpness';
          }
        });
      };
      placeholder.style.display = 'none';
      preview.classList.add('active');
      updateExtractButtonState();
    };
    reader.readAsDataURL(file);
  }

  setupDropzone(rectoDropzone, rectoInput, rectoPlaceholder, rectoPreview, rectoImg, rectoRemove, rectoQuality, 'rectoFile');
  setupDropzone(versoDropzone, versoInput, versoPlaceholder, versoPreview, versoImg, versoRemove, versoQuality, 'versoFile');
  setupDropzone(singleDropzone, singleInput, singlePlaceholder, singlePreview, singleImg, singleRemove, singleQuality, 'singleFile');

  function updateExtractButtonState() {
    if (state.mode === 'dual') {
      btnExtract.disabled = !(state.rectoFile || state.versoFile);
    } else {
      btnExtract.disabled = !state.singleFile;
    }
  }

  // 7. Extract & Verify API Request
  btnExtract.addEventListener('click', async () => {
    btnExtract.disabled = true;
    btnSpinner.style.display = 'inline-block';
    btnText.textContent = 'Processing OCR & Verifying...';

    const formData = new FormData();
    const useBase64 = chkBase64.checked;

    if (state.mode === 'dual') {
      if (state.rectoFile) formData.append('recto', state.rectoFile);
      if (state.versoFile) formData.append('verso', state.versoFile);
    } else {
      if (state.singleFile) formData.append('file', state.singleFile);
    }

    const startTime = performance.now();

    try {
      const response = await fetch(`/api/v1/extract?return_base64_photo=${useBase64}`, {
        method: 'POST',
        body: formData
      });

      const json = await response.json();
      const elapsed = Math.round(performance.now() - startTime);

      if (!response.ok) {
        throw new Error(json.detail || 'Extraction failed with status ' + response.status);
      }

      state.latestResult = json;
      renderResults(json, elapsed);
      showToast('Document analyzed successfully!');
    } catch (err) {
      console.error(err);
      showToast(err.message || 'Error occurred during extraction', 'error');
    } finally {
      btnExtract.disabled = false;
      btnSpinner.style.display = 'none';
      btnText.textContent = 'Analyze & Verify Document';
    }
  });

  // 8. Render Results Panel
  function renderResults(res, clientLatencyMs) {
    emptyState.style.display = 'none';
    resultsWrapper.style.display = 'flex';

    latencyBadge.textContent = `${res.processing_time_ms || clientLatencyMs}ms latency`;

    const identity = res.identity || {};
    const family = res.family_and_address || {};
    const val = res.validation || {};
    const cardType = res.card_type || 'full_profile';

    // 8.1 Affiliation Security Banner
    if (cardType === 'mismatched_pair') {
      affiliationBanner.className = 'affiliation-banner mismatch';
      affIcon.textContent = '🚨';
      affTitle.textContent = 'SECURITY ALERT: Affiliation Mismatch';
      affDetails.textContent = val.affiliation_details || 'The uploaded Verso does not belong to the uploaded Recto. These cards belong to two different individuals.';
    } else if (cardType.startsWith('duplicate_')) {
      affiliationBanner.className = 'affiliation-banner warning';
      affIcon.textContent = '⚠️';
      affTitle.textContent = 'MISSING SIDE ALERT';
      affDetails.textContent = val.affiliation_details || `Duplicate ${cardType} uploaded. The opposite side is missing.`;
    } else if (cardType.startsWith('single_')) {
      affiliationBanner.className = 'affiliation-banner warning';
      affIcon.textContent = 'ℹ️';
      affTitle.textContent = 'SINGLE SIDE PROCESSED';
      affDetails.textContent = `Processed ${cardType.replace('single_', '').toUpperCase()} side. The opposite side is missing.`;
    } else {
      affiliationBanner.className = 'affiliation-banner verified';
      affIcon.textContent = '🛡️';
      affTitle.textContent = 'Identity & Affiliation Verified';
      affDetails.textContent = val.affiliation_details || 'Front and Back sides belong to the same citizen and cross-validation passed.';
    }

    // 8.2 Citizen Photo & Generation
    resCardGen.textContent = val.card_generation || 'Moroccan CNIE';
    if (res.photo_base64) {
      resPhoto.src = res.photo_base64;
    } else if (res.photo_url) {
      resPhoto.src = `${res.photo_url}?t=${Date.now()}`;
    } else {
      resPhoto.src = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="%231e293b"/><text x="50" y="55" font-size="30" text-anchor="middle" fill="%2364748b">👤</text></svg>';
    }

    // 8.3 Fields
    valCnie.textContent = identity.cnie || 'Not detected';
    valGenderNat.textContent = `${identity.gender || 'Not detected'} / ${identity.nationality || 'MAR'}`;
    valLastName.textContent = identity.last_name || 'Not detected';
    valFirstName.textContent = identity.first_name || 'Not detected';
    valBirthDate.textContent = identity.birth_date || 'Not detected';
    valBirthPlace.textContent = identity.place_of_birth || 'Not detected';
    valExpiryDate.textContent = identity.expiry_date || 'Not detected';
    valCardType.textContent = cardType.replace('_', ' ').toUpperCase();

    valFather.textContent = family.father_name || 'Not detected';
    valMother.textContent = family.mother_name || 'Not detected';
    valCivilAct.textContent = family.civil_act || 'Not detected';
    valAddress.textContent = family.address || 'Not detected';

    // 8.4 Cryptographic Checksum Pills
    const hasMrz = Boolean(val.mrz_detected);

    if (val.cnie_cross_verified === true) {
      pillCnie.className = 'pill-badge pass';
      pillCnie.textContent = 'CNIE Cross-Match: PASS';
    } else if (cardType === 'mismatched_pair') {
      pillCnie.className = 'pill-badge fail';
      pillCnie.textContent = 'CNIE Cross-Match: MISMATCH';
    } else if (cardType.startsWith('single_') || cardType.startsWith('duplicate_')) {
      pillCnie.className = 'pill-badge neutral';
      pillCnie.textContent = 'CNIE Cross-Match: N/A';
    } else {
      pillCnie.className = 'pill-badge neutral';
      pillCnie.textContent = 'CNIE Cross-Match: Visual';
    }

    if (hasMrz) {
      setupPill(pillDob, val.birth_date_mrz_verified, 'MRZ DOB Match');
      setupPill(pillExp, val.expiry_date_mrz_verified, 'MRZ Expiry Match');
      setupPill(pillDobChk, val.dob_checksum_valid, 'ICAO 9303 DOB');
      setupPill(pillExpChk, val.expiry_checksum_valid, 'ICAO 9303 EXP');
    } else {
      // Pre-2020 cards do not have an MRZ zone (Traditional visual cards)
      pillDob.className = 'pill-badge neutral';
      pillDob.textContent = 'MRZ DOB: N/A (Pre-2020)';
      pillExp.className = 'pill-badge neutral';
      pillExp.textContent = 'MRZ Expiry: N/A (Pre-2020)';
      pillDobChk.className = 'pill-badge neutral';
      pillDobChk.textContent = 'ICAO 9303 DOB: N/A (No MRZ)';
      pillExpChk.className = 'pill-badge neutral';
      pillExpChk.textContent = 'ICAO 9303 EXP: N/A (No MRZ)';
    }
  }

  function setupPill(pill, isValid, label) {
    if (isValid === true) {
      pill.className = 'pill-badge pass';
      pill.textContent = `${label}: PASS`;
    } else if (isValid === false) {
      pill.className = 'pill-badge fail';
      pill.textContent = `${label}: FAIL`;
    } else {
      pill.className = 'pill-badge neutral';
      pill.textContent = `${label}: N/A`;
    }
  }

  // 9. Actions (Copy JSON, Download JSON, Reset)
  btnCopyJson.addEventListener('click', () => {
    if (!state.latestResult) return;
    navigator.clipboard.writeText(JSON.stringify(state.latestResult, null, 2))
      .then(() => showToast('Full JSON response copied to clipboard!'))
      .catch(() => showToast('Failed to copy to clipboard', 'error'));
  });

  btnDownloadJson.addEventListener('click', () => {
    if (!state.latestResult) return;
    const blob = new Blob([JSON.stringify(state.latestResult, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    const cnie = state.latestResult.identity ? state.latestResult.identity.cnie : 'cnie_export';
    a.href = url;
    a.download = `cnie_kyc_${cnie}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('KYC JSON report downloaded.');
  });

  btnReset.addEventListener('click', () => {
    state.rectoFile = null;
    state.versoFile = null;
    state.singleFile = null;
    state.latestResult = null;

    rectoInput.value = '';
    versoInput.value = '';
    singleInput.value = '';

    rectoPreview.classList.remove('active');
    versoPreview.classList.remove('active');
    singlePreview.classList.remove('active');

    rectoPlaceholder.style.display = 'block';
    versoPlaceholder.style.display = 'block';
    singlePlaceholder.style.display = 'block';

    resultsWrapper.style.display = 'none';
    emptyState.style.display = 'block';
    updateExtractButtonState();
    showToast('Ready for new scan.');
  });

  // 10. Toast Notification Helper
  let toastTimer = null;
  function showToast(message, type = 'info') {
    if (toastTimer) clearTimeout(toastTimer);
    toastMessage.textContent = message;
    toastMessage.style.borderColor = (type === 'error') ? '#ef4444' : 'var(--border-hover)';
    toastMessage.classList.add('show');
    toastTimer = setTimeout(() => {
      toastMessage.classList.remove('show');
    }, 3500);
  }
});

# Project Guidelines: Cin-Ocr-Pipeline

## 1. Terminal Execution
- Provide exact terminal commands for the user to execute in their integrated terminal. Do not run background shell commands via agent tools.

## 2. Python Code Standards
- Use Python type hints on all function arguments and return types.
- Write clean, comprehensive docstrings explaining function behavior, inputs, and outputs.

## 3. Data Privacy & PII Safety
- Never commit sensitive Personally Identifiable Information (PII), Moroccan ID photos, or scanned card data to git.
- Keep all data artifacts in gitignored paths (`data/extracted_faces/`, `data/*.jpg`, `data/*.png`).

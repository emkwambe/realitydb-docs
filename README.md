# RealityDB ReportLab Renderers

Synthetic financial document generators using ReportLab. Produces realistic W-2s and bank statements for IDP/underwriting pipeline testing.

## Quick Start

```bash
pip install -r requirements.txt
python generate_dataset.py
```

## Output

| Document Type | Count | Format |
|--------------|-------|--------|
| W-2 Forms | 20 | PDF (clean + noisy variants) |
| Bank Statements | 10 | PDF (with transaction tables) |

## Files

- `w2_renderer.py` — W-2 wage and tax statement renderer
- `bank_statement_renderer.py` — Bank statement with transaction tables
- `generate_dataset.py` — Batch generator for full dataset

## Integration with PacketWise

Copy generated PDFs to `PacketWise/data/synthetic/` and process via:

```bash
curl -X POST "http://localhost:8000/api/v1/process" \
  -F "files=@data/synthetic/w2_001_clean.pdf"
```

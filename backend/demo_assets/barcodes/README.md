# Demo product barcodes

Run `python scripts/generate_demo_barcodes.py` from the `backend` directory to
regenerate the five EAN-13 PNGs. Their stable values come from
`app/demo_data.py` and match the demo Product rows created by `python -m
app.seed` when `SEED_DEMO_ACCOUNTS=true`.

These are valid, machine-readable EAN-13 images intended for demonstrations.
They are internal-use identifiers, not registered GS1 product numbers.

Important: the current Asset Scan API resolves `EmissionSource.barcode_value`,
whereas Product uses its separate `barcode` field. Scanning these Product PNGs
with an ordinary barcode reader returns the embedded EAN-13 value, but the
application's Asset Scan screen will not resolve them until product scanning is
designed and added to that API contract.

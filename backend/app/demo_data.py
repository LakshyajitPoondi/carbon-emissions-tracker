"""Stable fixture definitions for the opt-in interactive demo environment."""

from datetime import datetime, timezone
from decimal import Decimal

DEMO_ORGANIZATION_NAME = "Demo Organization"
DEMO_INDUSTRY_TYPE = "Manufacturing (Demo)"
DEMO_PASSWORD = "DemoPass123!"
DEMO_RECORDED_BY = "admin-demo@gmail.com"

DEMO_USERS = (
    {"email": "admin-demo@gmail.com", "role": "OWNER", "can_sign_in": True},
    {"email": "employee-demo@gmail.com", "role": "EMPLOYEE", "can_sign_in": True},
    {"email": "operations-lead.demo@example.com", "role": "ADMIN", "can_sign_in": False},
    {"email": "sustainability-manager.demo@example.com", "role": "ADMIN", "can_sign_in": False},
    {"email": "analyst.demo@example.com", "role": "EMPLOYEE", "can_sign_in": False},
    {"email": "plant-manager.demo@example.com", "role": "EMPLOYEE", "can_sign_in": False},
    {"email": "procurement.demo@example.com", "role": "EMPLOYEE", "can_sign_in": False},
)

DEMO_FACILITIES = (
    {"name": "Chennai Production Plant", "location": "Chennai, India", "facility_type": "Factory"},
    {"name": "Bengaluru Distribution Hub", "location": "Bengaluru, India", "facility_type": "Warehouse"},
    {"name": "Pune Research Office", "location": "Pune, India", "facility_type": "Office"},
)

DEMO_SOURCES = (
    {
        "facility": "Chennai Production Plant",
        "source_type": "ENERGY",
        "source_name": "Grid electricity",
        "unit": "kWh",
        "barcode": "DEMO-CHN-GRID",
        "quantities": (Decimal("1180.50"), Decimal("1264.25"), Decimal("1215.75")),
    },
    {
        "facility": "Chennai Production Plant",
        "source_type": "FUEL",
        "source_name": "Diesel generator",
        "unit": "litre",
        "barcode": "DEMO-CHN-DIESEL",
        "quantities": (Decimal("44.00"), Decimal("39.50"), Decimal("47.25")),
    },
    {
        "facility": "Chennai Production Plant",
        "source_type": "RESOURCE",
        "source_name": "Purchased Portland cement",
        "unit": "kg",
        "barcode": "DEMO-CHN-CEMENT",
        "quantities": (Decimal("680.00"), Decimal("745.00"), Decimal("710.00")),
    },
    {
        "facility": "Bengaluru Distribution Hub",
        "source_type": "ENERGY",
        "source_name": "Warehouse grid electricity",
        "unit": "kWh",
        "barcode": "DEMO-BLR-GRID",
        "quantities": (Decimal("720.25"), Decimal("755.50"), Decimal("698.75")),
    },
    {
        "facility": "Bengaluru Distribution Hub",
        "source_type": "FUEL",
        "source_name": "Diesel forklift fleet",
        "unit": "litre",
        "barcode": "DEMO-BLR-FORKLIFT",
        "quantities": (Decimal("25.50"), Decimal("29.25"), Decimal("27.00")),
    },
    {
        "facility": "Pune Research Office",
        "source_type": "ENERGY",
        "source_name": "Office grid electricity",
        "unit": "kWh",
        "barcode": "DEMO-PUN-GRID",
        "quantities": (Decimal("405.00"), Decimal("438.50"), Decimal("419.75")),
    },
    {
        "facility": "Pune Research Office",
        "source_type": "FUEL",
        "source_name": "Backup diesel generator",
        "unit": "litre",
        "barcode": "DEMO-PUN-DIESEL",
        "quantities": (Decimal("8.50"), Decimal("6.25"), Decimal("9.00")),
    },
    {
        "facility": "Pune Research Office",
        "source_type": "RESOURCE",
        "source_name": "Cement for materials lab",
        "unit": "kg",
        "barcode": "DEMO-PUN-CEMENT",
        "quantities": (Decimal("38.00"), Decimal("42.50"), Decimal("35.75")),
    },
)

DEMO_RECORD_TIMES = (
    datetime(2026, 8, 5, 9, 0, tzinfo=timezone.utc),
    datetime(2026, 8, 15, 9, 0, tzinfo=timezone.utc),
    datetime(2026, 8, 25, 9, 0, tzinfo=timezone.utc),
)


def ean13_from_sequence(sequence: int) -> str:
    """Return a valid internal-use EAN-13 value from a positive sequence."""
    if sequence < 0 or sequence > 9_999_999_999:
        raise ValueError("sequence must fit in ten digits")
    body = f"20{sequence:010d}"
    weighted_sum = sum(
        int(digit) * (1 if index % 2 == 0 else 3)
        for index, digit in enumerate(body)
    )
    return f"{body}{(-weighted_sum) % 10}"


DEMO_PRODUCTS = (
    {
        "name": "Recycled Aluminium Bottle",
        "barcode": ean13_from_sequence(1),
        "composition": "85% recycled aluminium, 10% virgin aluminium, 5% polymer cap and coating.",
        "emissions_value": Decimal("1.240000"),
        "emissions_unit": "kg CO2e per bottle",
        "emissions_description": "Illustrative cradle-to-gate product carbon estimate for demo use.",
        "source_reference": "Demo supplier estimate, 2026 (illustrative; not for disclosure).",
    },
    {
        "name": "Low-Carbon Concrete Paver",
        "barcode": ean13_from_sequence(2),
        "composition": "Cementitious binder with fly ash, manufactured sand, aggregate and water.",
        "emissions_value": Decimal("3.850000"),
        "emissions_unit": "kg CO2e per paver",
        "emissions_description": "Illustrative cradle-to-gate product carbon estimate for demo use.",
        "source_reference": "Demo supplier EPD estimate, 2026 (illustrative; not for disclosure).",
    },
    {
        "name": "FSC Cardboard Shipping Carton",
        "barcode": ean13_from_sequence(3),
        "composition": "FSC-certified corrugated board with water-based adhesive and ink.",
        "emissions_value": Decimal("0.620000"),
        "emissions_unit": "kg CO2e per carton",
        "emissions_description": "Illustrative cradle-to-gate product carbon estimate for demo use.",
        "source_reference": "Demo packaging assessment, 2026 (illustrative; not for disclosure).",
    },
    {
        "name": "Recycled PET Safety Helmet",
        "barcode": ean13_from_sequence(4),
        "composition": "70% recycled PET shell, textile suspension and stainless-steel fasteners.",
        "emissions_value": Decimal("2.170000"),
        "emissions_unit": "kg CO2e per helmet",
        "emissions_description": "Illustrative cradle-to-gate product carbon estimate for demo use.",
        "source_reference": "Demo lifecycle screening, 2026 (illustrative; not for disclosure).",
    },
    {
        "name": "Solar-Powered Sensor Unit",
        "barcode": ean13_from_sequence(5),
        "composition": "Small photovoltaic panel, lithium battery, PCB and recycled-polymer enclosure.",
        "emissions_value": Decimal("8.940000"),
        "emissions_unit": "kg CO2e per unit",
        "emissions_description": "Illustrative cradle-to-gate product carbon estimate for demo use.",
        "source_reference": "Demo bill-of-materials model, 2026 (illustrative; not for disclosure).",
    },
)

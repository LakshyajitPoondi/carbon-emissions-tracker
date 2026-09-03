"""Validate explicit Product units without guessing from free-text references."""


def validate_product_configuration(
    consumption_unit: str | None,
    consumption_source_type: str | None,
    emissions_unit: str,
) -> None:
    if consumption_unit is None and consumption_source_type is None:
        return
    if not consumption_unit or consumption_source_type not in {"ENERGY", "FUEL", "RESOURCE"}:
        raise ValueError("Set consumption_unit and consumption_source_type together, or clear both")
    if consumption_unit != consumption_unit.strip() or len(consumption_unit) > 50:
        raise ValueError("consumption_unit must be trimmed and at most 50 characters")
    expected = f"kg CO2e/{consumption_unit}"
    if emissions_unit != expected:
        raise ValueError(f"Configured Product emissions_unit must be exactly '{expected}'")

"""Compose catalog names from editable facts without altering their spelling."""

import unicodedata


def compose_product_name(product_type, brand, product_name, unit, amount) -> str | None:
    parts = [" ".join((value or "").split()) for value in
             (product_type, brand, product_name, unit, amount)]
    identity = lambda value: unicodedata.normalize("NFC", value).lower()
    if parts[2] and identity(parts[2]) in {identity(parts[0]), identity(parts[1])}:
        parts[2] = ""
    # A unit or package amount alone is not a product identity.
    if not any(parts[:3]):
        return None
    return " ".join(part for part in parts if part)


def update_final_name(draft) -> None:
    draft.final_name = compose_product_name(
        draft.product_type, draft.brand, draft.product_name, draft.primary_unit, draft.package_size)

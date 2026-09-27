"""Utilidades para extraer y normalizar números de bus."""
import re


def parse_bus_number(value):
    """Extrae el número entero de bus de un string o valor."""
    if value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    text = str(value).strip()
    if not text:
        return None
    # Quitar prefijos comunes MB, BUS, etc.
    text = re.sub(r'^(MB|BUS|B|N[°º]?)[\s\-_]*', '', text, flags=re.IGNORECASE)
    # Extraer dígitos
    match = re.search(r'(\d{3,5})', text)
    if match:
        try:
            num = int(match.group(1))
            # Normalizar leading zeros: 0806 -> 806
            return num
        except ValueError:
            return None
    try:
        return int(float(text))
    except (ValueError, TypeError):
        return None


def extract_bus_number(raw):
    """Extrae número de bus desde un dict (item BUSAE o Genesis)."""
    if not isinstance(raw, dict):
        return parse_bus_number(raw)

    for key in (
        'bus_number', 'bn', 'bus', 'Bus', 'bus_id', 'busId',
        'numero', 'nro', 'movil', 'móvil', 'unidad',
        'map_marker_title', 'plate_number',
    ):
        if key in raw:
            num = parse_bus_number(raw.get(key))
            if num:
                return num
    return None

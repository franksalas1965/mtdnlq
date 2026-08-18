"""Utilidades de escala MTD (N_ = 1:N 000, base mtdN)."""
from urllib.parse import urlparse

VALID_SCALES = (10000, 25000, 50000, 100000, 250000)


def scale_prefix(scale: int) -> str:
    """10000 → '10_', 100000 → '100_'."""
    return f"{scale // 1000}_"


def database_name(scale: int) -> str:
    """10000 → 'mtd10', 100000 → 'mtd100'."""
    return f"mtd{scale // 1000}"


def scale_label(scale: int) -> str:
    n = scale // 1000
    return f"1:{n} 000"


def parse_scale_from_database_url(database_url: str) -> int:
    """Infiere escala desde el nombre de BD en DATABASE_URL (mtd10 → 10000)."""
    path = urlparse(database_url).path.strip("/")
    if path.startswith("mtd") and path[3:].isdigit():
        return int(path[3:]) * 1000
    return 10000


def parse_enabled_scales(value: str) -> list[int]:
    scales: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        scale = int(part)
        if scale not in VALID_SCALES:
            raise ValueError(f"Escala MTD no soportada: {scale}")
        scales.append(scale)
    return scales or [10000]

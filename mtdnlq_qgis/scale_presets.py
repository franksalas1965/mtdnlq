# -*- coding: utf-8 -*-
"""Escalas MTD y convención de prefijos de esquema (N_ = 1:N 000)."""

SCALE_OPTIONS = [
    {
        "denominator": 10000,
        "label": "1:10 000",
        "prefix": "10_",
        "database": "mtd10",
        "default_port": 8001,
    },
    {
        "denominator": 25000,
        "label": "1:25 000",
        "prefix": "25_",
        "database": "mtd25",
        "default_port": 8002,
    },
    {
        "denominator": 50000,
        "label": "1:50 000",
        "prefix": "50_",
        "database": "mtd50",
        "default_port": 8003,
    },
    {
        "denominator": 100000,
        "label": "1:100 000",
        "prefix": "100_",
        "database": "mtd100",
        "default_port": 8004,
    },
    {
        "denominator": 250000,
        "label": "1:250 000",
        "prefix": "250_",
        "database": "mtd250",
        "default_port": 8005,
    },
]

DEFAULT_SCALE = 10000


def get_scale_option(denominator: int) -> dict:
    for opt in SCALE_OPTIONS:
        if opt["denominator"] == denominator:
            return opt
    return SCALE_OPTIONS[0]


def fill_scale_combo(combo) -> None:
    """Rellena un QComboBox con las escalas MTD disponibles."""
    combo.clear()
    for opt in SCALE_OPTIONS:
        combo.addItem(
            f"{opt['label']}  ({opt['database']}, prefijo {opt['prefix']})",
            opt["denominator"],
        )


def set_combo_scale(combo, denominator: int) -> None:
    idx = combo.findData(int(denominator))
    if idx >= 0:
        combo.setCurrentIndex(idx)


def suggested_api_url(denominator: int, host: str = "localhost") -> str:
    opt = get_scale_option(denominator)
    return f"http://{host}:{opt['default_port']}"


def apply_scale_to_question(question: str, denominator: int) -> str:
    """
    Añade contexto de escala a la pregunta para orientar al LLM.
    No modifica la pregunta si ya incluye el prefijo de escala.
    """
    text = question.strip()
    lower = text.lower()
    if lower.startswith("[escala mtd"):
        return text

    opt = get_scale_option(denominator)
    return (
        f"[Escala MTD {opt['label']}, base de datos {opt['database']}, "
        f"esquemas con prefijo {opt['prefix']}] {text}"
    )

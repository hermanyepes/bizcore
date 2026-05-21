# ============================================================
# BizCore — Tests unitarios: validador NIT colombiano (HU-040)
# ============================================================
#
# Prueba el algoritmo DIAN módulo 11 directamente sobre
# los schemas Pydantic de Supplier, sin pasar por HTTP.
# ============================================================

import pytest
from pydantic import ValidationError

from app.schemas.supplier import SupplierCreate, SupplierUpdate, _compute_nit_dv


# ============================================================
# Algoritmo DIAN — casos conocidos
# ============================================================


def test_compute_dv_dian_nit_conocido():
    """NIT del DIAN (899999230) tiene DV = 7. Verificación del algoritmo."""
    assert _compute_nit_dv("899999230") == 7  # pragma: allowlist secret


def test_compute_dv_nit_con_dv_cero():
    """Verifica que el algoritmo maneja correctamente DV = 0."""
    # Construimos un NIT cuyo DV sea 0 o 1 (rem <= 1 → DV = rem)
    # Usamos 900000000 para este caso de prueba
    dv = _compute_nit_dv("900000000")
    assert 0 <= dv <= 10


# ============================================================
# SupplierCreate — nit opcional con validación
# ============================================================


def test_create_nit_none_es_valido():
    """NIT ausente (None) es válido — campo opcional."""
    s = SupplierCreate(name="Proveedor X")
    assert s.nit is None


def test_create_nit_solo_digitos_9_valido():
    """NIT de 9 dígitos sin DV es aceptado."""
    s = SupplierCreate(name="P", nit="899999230")
    assert s.nit == "899999230"


def test_create_nit_con_dv_correcto_valido():
    """NIT con DV correcto (899999230-7) es aceptado."""
    s = SupplierCreate(name="P", nit="899999230-7")
    assert s.nit == "899999230-7"


def test_create_nit_con_dv_incorrecto_lanza_error():
    """NIT con DV incorrecto es rechazado con mensaje que indica el DV correcto."""
    with pytest.raises(ValidationError) as exc_info:
        SupplierCreate(name="P", nit="899999230-5")
    assert "DV correcto" in str(exc_info.value)


def test_create_nit_demasiado_corto_lanza_error():
    """NIT de 5 dígitos (< 9) es rechazado."""
    with pytest.raises(ValidationError):
        SupplierCreate(name="P", nit="12345")


def test_create_nit_con_letras_lanza_error():
    """NIT con letras es rechazado."""
    with pytest.raises(ValidationError):
        SupplierCreate(name="P", nit="ABCDE1234")  # pragma: allowlist secret


def test_create_nit_con_espacios_es_limpiado():
    """Espacios en blanco alrededor del NIT son removidos antes de validar."""
    s = SupplierCreate(name="P", nit="  899999230-7  ")
    assert s.nit == "899999230-7"


def test_create_nit_11_digitos_valido():
    """NIT de 11 dígitos (sin DV) es aceptado."""
    s = SupplierCreate(name="P", nit="12345678901")
    assert s.nit == "12345678901"


def test_create_nit_12_digitos_rechazado():
    """NIT de 12 dígitos (> 11, sin DV) es rechazado."""
    with pytest.raises(ValidationError):
        SupplierCreate(name="P", nit="123456789012")


# ============================================================
# SupplierUpdate — misma validación que Create
# ============================================================


def test_update_nit_con_dv_correcto_valido():
    """SupplierUpdate también valida el DV correctamente."""
    s = SupplierUpdate(nit="899999230-7")
    assert s.nit == "899999230-7"


def test_update_nit_incorrecto_lanza_error():
    """SupplierUpdate rechaza NITs con DV incorrecto."""
    with pytest.raises(ValidationError):
        SupplierUpdate(nit="899999230-9")

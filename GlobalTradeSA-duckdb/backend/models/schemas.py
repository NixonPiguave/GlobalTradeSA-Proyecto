"""
Modelos Pydantic para request/response de la API REST de GLOBTRADE S.A.

Valida: Requisitos 2.1, 3.7, 4.2, 5.3, 6.1, 6.2, 6.3
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Any
from datetime import date
from decimal import Decimal


class VentaOut(BaseModel):
    """
    Representa una fila de la tabla `ventas` serializada hacia el cliente.
    Valida: Requisito 5.3
    """

    id: int
    region: str
    country: str
    item_type: str
    sales_channel: str
    order_priority: str
    order_date: date
    order_id: int
    ship_date: date
    units_sold: int
    unit_price: Decimal
    unit_cost: Decimal
    total_revenue: Decimal
    total_cost: Decimal
    total_profit: Decimal

    model_config = {"from_attributes": True}


class PaginatedResponse(BaseModel):
    """
    Envuelve cualquier lista paginada con metadatos de paginación.
    Valida: Requisito 4.2, 5.3
    """

    data: List[Any]
    page: int = Field(..., ge=1, description="Número de página actual (≥ 1)")
    page_size: int = Field(..., ge=1, description="Registros por página (≥ 1)")
    total: int = Field(..., ge=0, description="Total de registros que cumplen los filtros")


class KPIResponse(BaseModel):
    """
    Respuesta del endpoint GET /api/dashboard/kpis.
    Valida: Requisito 2.1
    """

    total_revenue: Decimal
    total_cost: Decimal
    total_profit: Decimal
    units_sold: int
    date_from: Optional[date] = None
    date_to: Optional[date] = None

    @field_validator("date_to")
    @classmethod
    def date_to_must_be_gte_date_from(
        cls, date_to: Optional[date], info: Any
    ) -> Optional[date]:
        """Valida que date_to no sea anterior a date_from cuando ambos están presentes."""
        date_from = info.data.get("date_from")
        if date_from is not None and date_to is not None and date_to < date_from:
            raise ValueError(
                "date_to no puede ser anterior a date_from"
            )
        return date_to


class RentabilidadRow(BaseModel):
    """
    Una fila del análisis de rentabilidad agrupado por dimensión.
    Valida: Requisito 6.1, 6.2, 6.3
    """

    dimension: str
    total_revenue: Decimal
    total_cost: Decimal
    total_profit: Decimal
    margen_pct: Optional[Decimal] = None
    clasificacion_margen: Optional[str] = None
    units_sold: Optional[int] = None

    @field_validator("clasificacion_margen")
    @classmethod
    def clasificacion_must_be_valid(cls, v: Optional[str]) -> Optional[str]:
        """Acepta únicamente los valores canónicos de clasificación o None."""
        valid = {"alto", "medio", "bajo"}
        if v is not None and v not in valid:
            raise ValueError(
                f"clasificacion_margen debe ser uno de {valid}, se recibió '{v}'"
            )
        return v

    model_config = {"from_attributes": True}


class ETLResult(BaseModel):
    """
    Resumen del proceso ETL tras la carga de un archivo CSV.
    Valida: Requisito 3.7
    """

    job_id: str = Field(..., description="UUID v4 del job ETL")
    inserted: int = Field(..., ge=0, description="Filas insertadas exitosamente")
    rejected: int = Field(..., ge=0, description="Filas rechazadas (duplicados u otros errores)")
    errors: List[dict] = Field(
        default_factory=list,
        description="Detalle de cada fila rechazada: row, column (opcional), reason",
    )

    @field_validator("errors")
    @classmethod
    def errors_length_matches_rejected(
        cls, errors: List[dict], info: Any
    ) -> List[dict]:
        """
        Garantiza la consistencia del resumen ETL:
        len(errors) == rejected  (Propiedad 3 del diseño).
        """
        rejected = info.data.get("rejected")
        if rejected is not None and len(errors) != rejected:
            raise ValueError(
                f"La longitud de 'errors' ({len(errors)}) debe ser igual a 'rejected' ({rejected})"
            )
        return errors

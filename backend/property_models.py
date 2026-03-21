"""
Pydantic models for live NYC property context endpoints.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class PropertySearchResult(BaseModel):
    bbl: str
    address: str
    borough: str
    zone: str = ""
    overlay: str = ""
    lotArea: float = Field(0, ge=0)
    builtFar: float = Field(0, ge=0)
    numFloors: float = Field(0, ge=0)
    yearBuilt: int = Field(0, ge=0)
    bldgClass: str = ""
    lat: float = 0
    lng: float = 0


class PropertySearchResponse(BaseModel):
    results: list[PropertySearchResult] = Field(default_factory=list)
    query: str = ""


class AcrisDocument(BaseModel):
    document_id: str = ""
    doc_type: str = ""
    doc_date: Optional[str] = None
    recorded_filed: Optional[str] = None
    doc_amount: Optional[float] = None
    party1: str = ""
    party2: str = ""


class AcrisSummary(BaseModel):
    documents: list[AcrisDocument] = Field(default_factory=list)
    last_deed_date: Optional[str] = None
    last_deed_amount: Optional[float] = None
    last_deed_buyer: str = ""
    last_deed_seller: str = ""
    total_mortgage_amount: Optional[float] = None
    open_liens: int = 0


class ValidatedLotInfo(BaseModel):
    bbl: str
    address: str
    lotArea: float = Field(0, ge=0)
    zone: str = ""


class BlockLotInfo(BaseModel):
    lot: int = Field(..., ge=0)
    address: str = ""
    lotArea: float = Field(0, ge=0)
    zone: str = ""


class BlockLotsResponse(BaseModel):
    borough: int = Field(..., ge=1, le=5)
    block: int = Field(..., ge=0)
    lots: list[BlockLotInfo] = Field(default_factory=list)


class PropertyContextRequest(BaseModel):
    primary_bbl: str = Field(..., min_length=10, max_length=10)
    adjacent_bbls: list[str] = Field(default_factory=list)


class PropertyScenario(BaseModel):
    code: str
    label: str
    max_res_floor_area: int = 0
    max_number_of_units: int = 0
    affordable_floor_area: int = 0
    affordable_floor_area_uap: int = 0
    affordable_floor_area_485x: int = 0
    affordable_units_percentage: float = 0
    affordable_units_total: int = 0
    market_rate_units: int = 0
    ami_breakdown: list[dict[str, int]] = Field(default_factory=list)
    triggers_prevailing_wages: bool = False
    triggers_40_ami: bool = False
    is_uap_eligible: bool = True
    available: bool = True
    notes: list[str] = Field(default_factory=list)


class PropertyLotRecord(BaseModel):
    bbl: str
    borough: str
    block: str
    lot: str
    address: str = ""
    zoning: str = ""
    overlay1: Optional[str] = None
    overlay2: Optional[str] = None
    lot_area: float = 0
    building_area: float = 0
    res_far: float = 0
    units_total: int = 0
    year_built: Optional[int] = None
    assessed_value: Optional[float] = None
    market_value: Optional[float] = None
    dof_taxable: Optional[float] = None
    has_pluto: bool = False
    has_dof: bool = False
    has_acris: bool = False
    lot_type_code: Optional[int] = None
    lot_type: str = "unknown"
    raw: dict[str, Any] = Field(default_factory=dict)


class PropertyContext(BaseModel):
    primary_bbl: str
    adjacent_bbls: list[str] = Field(default_factory=list)
    selected_bbls: list[str] = Field(default_factory=list)
    address: str = ""
    borough: str = ""
    block: str = ""
    lots: list[str] = Field(default_factory=list)
    zoning_district: str = ""
    overlay: str = ""
    overlay_far: Optional[float] = None
    community_facility_far: Optional[float] = None
    standard_far: Optional[float] = None
    qah_far: Optional[float] = None
    standard_height_limit: Optional[int] = None
    qah_height_limit: Optional[int] = None
    lot_coverage_corner: Optional[float] = None
    lot_coverage_interior: Optional[float] = None
    street_type_assumption: str = "narrow"
    has_narrow_wide: bool = False
    lot_type: str = "unknown"
    lot_area: float = 0
    building_area: float = 0
    units_total: int = 0
    assessed_value: Optional[float] = None
    market_value: Optional[float] = None
    dof_taxable: Optional[float] = None
    scenarios: list[PropertyScenario] = Field(default_factory=list)
    lots_detail: list[PropertyLotRecord] = Field(default_factory=list)
    acris_summary: Optional[AcrisSummary] = None
    sources: dict[str, Any] = Field(default_factory=dict)
    property_brief: str = ""

"""
Live NYC property lookup and normalized property-context builder.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from property_models import (
    AcrisDocument,
    AcrisSummary,
    ComparableSalesSummary,
    DobJobRecord,
    DobJobSummary,
    DofSaleRecord,
    EcbViolationSummary,
    FdnyVacateSummary,
    HpdLitigationSummary,
    HpdViolationSummary,
    PropertyContext,
    PropertyLotRecord,
    PropertyScenario,
)
from zoning_reference import get_overlay_far, get_zoning_info, infer_lot_type


PLUTO_ENDPOINT = "https://data.cityofnewyork.us/resource/64uk-42ks.json"
DOF_VALUATION_ENDPOINT = "https://data.cityofnewyork.us/resource/8y4t-faws.json"
GEOSEARCH_ENDPOINT = "https://geosearch.planninglabs.nyc/v2/search"
ACRIS_MASTER_ENDPOINT = "https://data.cityofnewyork.us/resource/bnx9-e6tj.json"
ACRIS_PARTIES_ENDPOINT = "https://data.cityofnewyork.us/resource/636b-3b5g.json"
ACRIS_LEGALS_ENDPOINT = "https://data.cityofnewyork.us/resource/8h5j-fqxa.json"
HPD_VIOLATIONS_ENDPOINT = "https://data.cityofnewyork.us/resource/wvxf-dwi5.json"
DOB_JOBS_ENDPOINT = "https://data.cityofnewyork.us/resource/ic3t-wcy2.json"
ECB_VIOLATIONS_ENDPOINT = "https://data.cityofnewyork.us/resource/6bgk-3dad.json"
DOF_SALES_ENDPOINT = "https://data.cityofnewyork.us/resource/usep-8jbt.json"
HPD_LITIGATIONS_ENDPOINT = "https://data.cityofnewyork.us/resource/59kj-x8nc.json"
FDNY_VACATE_ENDPOINT = "https://data.cityofnewyork.us/resource/tb8q-a3ar.json"

BOROUGH_ABBREV = {1: "MN", 2: "BX", 3: "BK", 4: "QN", 5: "SI"}
BOROUGH_NAMES = {1: "Manhattan", 2: "Bronx", 3: "Brooklyn", 4: "Queens", 5: "Staten Island"}
BORO_ALIASES = {
    "MANHATTAN": "1",
    "MN": "1",
    "NEW YORK": "1",
    "NY": "1",
    "BRONX": "2",
    "BX": "2",
    "THE BRONX": "2",
    "BROOKLYN": "3",
    "BK": "3",
    "KINGS": "3",
    "QUEENS": "4",
    "QN": "4",
    "QU": "4",
    "STATEN ISLAND": "5",
    "SI": "5",
    "RICHMOND": "5",
}

SCENARIO_LABELS = {
    "none": "As-of-Right (No Programs)",
    "485x_only": "485-x Only (20% at 80% AMI)",
    "uap_full_bonus": "UAP Full Bonus",
    "avoid_prevailing_wages": "UAP (Avoid Prevailing Wages)",
    "avoid_40_ami": "UAP (Avoid 40% AMI)",
    "ideal_match": "UAP Optimized (Ideal Match)",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_headers() -> dict[str, str]:
    return {"Accept": "application/json"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _escape_socrata_value(value: str) -> str:
    return str(value).replace("'", "''")


def normalize_bbl(value: str) -> str:
    return re.sub(r"\D", "", str(value or "")).strip()


def parse_bbl_parts(value: str) -> tuple[int, str, str]:
    cleaned = normalize_bbl(value)
    if len(cleaned) != 10:
        raise ValueError("BBL must be a 10-digit numeric string.")
    borough = int(cleaned[0])
    block = str(int(cleaned[1:6]))
    lot = str(int(cleaned[6:10]))
    return borough, block, lot


def _parse_address(raw_input: str) -> dict[str, Optional[str]]:
    cleaned = raw_input.strip().replace(",  ", ", ")
    borough = None
    for pattern in [
        r",?\s*(manhattan|bronx|brooklyn|queens|staten\s*island)\s*$",
        r",?\s*(mn|bx|bk|qn|si)\s*$",
        r",?\s*(new\s*york|ny)\s*$",
    ]:
        match = re.search(pattern, cleaned, re.IGNORECASE)
        if match:
            borough = re.sub(r"\s+", " ", match.group(1).upper())
            cleaned = cleaned[: match.start()].strip()
            break

    cleaned = re.sub(r",?\s*\d{5}(-\d{4})?\s*$", "", cleaned).strip()
    house_match = re.match(r"^(\d[\d\-/]*)\s+(.+)", cleaned)
    return {
        "houseNumber": house_match.group(1) if house_match else "",
        "street": house_match.group(2) if house_match else cleaned,
        "borough": borough,
        "raw": raw_input,
    }


def _round_to(value: float, decimals: int) -> float:
    factor = 10**decimals
    return round(value * factor) / factor


def _calc_max_units(floor_area: float, duf: float) -> int:
    if floor_area <= 0 or duf <= 0:
        return 0
    units = floor_area / duf
    decimal = units - int(units)
    return int(units) + 1 if decimal >= 0.75 else int(units)


def _calculate_scenario(program: str, lot_area: float, standard_far: float, uap_far: float, duf: float = 680.0) -> PropertyScenario:
    standard_fa = lot_area * standard_far
    uap_fa = lot_area * uap_far
    result = PropertyScenario(code=program, label=SCENARIO_LABELS[program], is_uap_eligible=uap_far > standard_far)

    if program == "none":
        result.max_res_floor_area = round(standard_fa)
        result.max_number_of_units = _calc_max_units(result.max_res_floor_area, duf)
        result.market_rate_units = result.max_number_of_units
        result.is_uap_eligible = False
        return result

    if program == "485x_only":
        result.max_res_floor_area = round(standard_fa)
        result.max_number_of_units = _calc_max_units(result.max_res_floor_area, duf)
        result.affordable_floor_area = int((result.max_res_floor_area * 0.2) + 0.9999)
        result.affordable_floor_area_485x = result.affordable_floor_area
        result.affordable_units_percentage = 0.2 if result.max_res_floor_area > 0 else 0
        result.affordable_units_total = int((result.max_number_of_units * 0.2) + 0.9999)
        result.market_rate_units = max(0, result.max_number_of_units - result.affordable_units_total)
        result.ami_breakdown = [{"ami": 80, "units": result.affordable_units_total}]
        result.is_uap_eligible = False
        return result

    if uap_far <= standard_far:
        result.available = False
        result.notes.append("Zone does not appear to provide a meaningful UAP residential FAR bonus.")
        return result

    if program == "uap_full_bonus":
        result.max_res_floor_area = round(uap_fa)
        result.max_number_of_units = _calc_max_units(result.max_res_floor_area, duf)
        result.affordable_floor_area = int((uap_fa - standard_fa) + 0.9999)
        result.affordable_floor_area_uap = result.affordable_floor_area
        if result.max_res_floor_area > 0:
            result.affordable_units_percentage = _round_to(result.affordable_floor_area / result.max_res_floor_area, 4)
        result.affordable_units_total = int((result.affordable_units_percentage * result.max_number_of_units) + 0.9999)
        result.market_rate_units = max(0, result.max_number_of_units - result.affordable_units_total)
        if result.affordable_floor_area >= 10000:
            units40 = int((result.affordable_units_total * 0.2) + 0.9999)
            result.ami_breakdown = [{"ami": 40, "units": units40}, {"ami": 60, "units": max(0, result.affordable_units_total - units40)}]
            result.triggers_40_ami = True
        else:
            result.ami_breakdown = [{"ami": 60, "units": result.affordable_units_total}]
        result.triggers_prevailing_wages = result.max_number_of_units >= 100
        return result

    if program == "avoid_prevailing_wages":
        max_uap_units = _calc_max_units(uap_fa, duf)
        result.max_number_of_units = min(99, max_uap_units)
        result.affordable_floor_area = round(result.max_number_of_units * 0.2 * duf)
        result.affordable_floor_area_uap = result.affordable_floor_area
        result.max_res_floor_area = round(standard_fa + result.affordable_floor_area)
        if result.max_res_floor_area > 0:
            result.affordable_units_percentage = _round_to(result.affordable_floor_area / result.max_res_floor_area, 4)
        result.affordable_units_total = round(result.affordable_units_percentage * result.max_number_of_units)
        result.market_rate_units = max(0, result.max_number_of_units - result.affordable_units_total)
        if result.affordable_floor_area >= 10000:
            units40 = int((result.affordable_units_total * 0.2) + 0.9999)
            result.ami_breakdown = [{"ami": 40, "units": units40}, {"ami": 60, "units": max(0, result.affordable_units_total - units40)}]
            result.triggers_40_ami = True
        else:
            result.ami_breakdown = [{"ami": 60, "units": result.affordable_units_total}]
        return result

    if program == "avoid_40_ami":
        max_uap_affordable = int((uap_fa - standard_fa) + 0.9999)
        result.affordable_floor_area = min(9999, max_uap_affordable)
        result.affordable_floor_area_uap = result.affordable_floor_area
        result.max_res_floor_area = round(standard_fa + result.affordable_floor_area)
        result.max_number_of_units = _calc_max_units(result.max_res_floor_area, duf)
        if result.max_res_floor_area > 0:
            result.affordable_units_percentage = _round_to(result.affordable_floor_area / result.max_res_floor_area, 4)
        result.affordable_units_total = int((result.affordable_units_percentage * result.max_number_of_units) + 0.9999)
        result.market_rate_units = max(0, result.max_number_of_units - result.affordable_units_total)
        result.ami_breakdown = [{"ami": 60, "units": result.affordable_units_total}]
        result.triggers_prevailing_wages = result.max_number_of_units >= 100
        return result

    if program == "ideal_match":
        max_uap_affordable = int((uap_fa - standard_fa) + 0.9999)
        result.affordable_floor_area = min(9999, max_uap_affordable)
        result.affordable_floor_area_uap = result.affordable_floor_area
        result.max_res_floor_area = round(standard_fa + result.affordable_floor_area)
        result.max_number_of_units = min(99, _calc_max_units(result.max_res_floor_area, duf))
        result.affordable_units_total = int((result.affordable_floor_area / duf) + 0.9999)
        if result.max_number_of_units > 0:
            result.affordable_units_percentage = _round_to(result.affordable_units_total / result.max_number_of_units, 4)
        result.market_rate_units = max(0, result.max_number_of_units - result.affordable_units_total)
        result.ami_breakdown = [{"ami": 60, "units": result.affordable_units_total}]
        return result

    return result


def _calculate_all_scenarios(lot_area: float, standard_far: float, uap_far: float, duf: float = 680.0) -> list[PropertyScenario]:
    return [
        _calculate_scenario("none", lot_area, standard_far, uap_far, duf),
        _calculate_scenario("485x_only", lot_area, standard_far, uap_far, duf),
        _calculate_scenario("uap_full_bonus", lot_area, standard_far, uap_far, duf),
        _calculate_scenario("avoid_prevailing_wages", lot_area, standard_far, uap_far, duf),
        _calculate_scenario("avoid_40_ami", lot_area, standard_far, uap_far, duf),
        _calculate_scenario("ideal_match", lot_area, standard_far, uap_far, duf),
    ]


class PropertyService:
    async def search_address(self, query: str) -> list[dict[str, Any]]:
        trimmed = str(query or "").strip()
        if not trimmed:
            return []

        async with httpx.AsyncClient(timeout=15.0, headers=_request_headers()) as client:
            if len(normalize_bbl(trimmed)) == 10:
                return await self._search_by_bbl(client, trimmed)
            return await self._search_by_address(client, trimmed)

    async def validate_lot(self, bbl: str) -> dict[str, Any]:
        borough, block, lot = parse_bbl_parts(bbl)
        result = await self.lookup_bbl(borough, block, lot)
        if not result.get("has_pluto"):
            raise LookupError(f"Lot {normalize_bbl(bbl)} not found in PLUTO")
        return {
            "bbl": normalize_bbl(bbl),
            "address": result.get("address", "") or "",
            "lotArea": float(result.get("lot_area", 0) or 0),
            "zone": result.get("zoning", "") or "",
        }

    async def get_block_lots(self, borough: int, block: int) -> dict[str, Any]:
        if borough < 1 or borough > 5:
            raise ValueError("borough must be 1-5")
        if block <= 0:
            raise ValueError("block must be positive")

        params = {
            "$where": f"borough='{BOROUGH_ABBREV.get(borough, 'BK')}' AND block='{block}'",
            "$select": "lot, address, lotarea, zonedist1",
            "$order": "lot ASC",
            "$limit": 200,
        }
        async with httpx.AsyncClient(timeout=15.0, headers=_request_headers()) as client:
            response = await client.get(PLUTO_ENDPOINT, params=params)
            response.raise_for_status()
            rows = response.json()

        return {
            "borough": borough,
            "block": block,
            "lots": [
                {
                    "lot": _safe_int(row.get("lot")),
                    "address": row.get("address", "") or "",
                    "lotArea": _safe_float(row.get("lotarea")),
                    "zone": row.get("zonedist1", "") or "",
                }
                for row in rows
            ],
        }

    async def lookup_bbl(self, borough: int, block: str, lot: str) -> dict[str, Any]:
        borough_name = BOROUGH_NAMES.get(borough, "Unknown")
        result: dict[str, Any] = {
            "success": False,
            "borough": borough_name,
            "block": block,
            "lot": lot,
            "has_pluto": False,
            "has_dof": False,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0, headers=_request_headers()) as client:
                pluto_params = {"$where": f"borocode='{borough}' AND block='{block}' AND lot='{lot}'", "$limit": 1}
                pluto_resp = await client.get(PLUTO_ENDPOINT, params=pluto_params)
                if pluto_resp.status_code == 200:
                    pluto_data = pluto_resp.json()
                    if pluto_data:
                        p = pluto_data[0]
                        result["success"] = True
                        result["has_pluto"] = True
                        result["address"] = p.get("address", "")
                        result["owner_name"] = p.get("ownername", "")
                        result["building_class"] = p.get("bldgclass", "")
                        result["zoning"] = p.get("zonedist1", "")
                        result["overlay1"] = p.get("overlay1") or None
                        result["overlay2"] = p.get("overlay2") or None
                        lat = p.get("latitude")
                        lon = p.get("longitude")
                        if lat is not None and lon is not None:
                            result["latitude"] = _safe_float(lat, None)
                            result["longitude"] = _safe_float(lon, None)
                        lot_area = _safe_float(p.get("lotarea"))
                        building_area = _safe_float(p.get("bldgarea"))
                        if not building_area and lot_area:
                            building_area = _safe_float(p.get("builtfar")) * lot_area
                        result["lot_area"] = lot_area
                        result["building_area"] = building_area
                        result["bldg_area"] = building_area
                        result["res_far"] = _safe_float(p.get("residfar"))
                        year_built = _safe_int(p.get("yearbuilt"))
                        result["year_built"] = year_built if year_built > 0 else None
                        result["units_total"] = _safe_int(p.get("unitstotal"))
                        result["assessed_total"] = _safe_float(p.get("assesstot"))
                        result["assessed_land"] = _safe_float(p.get("assessland"))
                        result["exempt_total"] = _safe_float(p.get("exempttot"))
                        lot_type_code = _safe_int(p.get("lottype"), 0)
                        result["lot_type_code"] = lot_type_code if lot_type_code > 0 else None

                dof_params = {"$where": f"boro='{borough}' AND block='{block}' AND lot='{lot}'", "$order": "year DESC", "$limit": 1}
                dof_resp = await client.get(DOF_VALUATION_ENDPOINT, params=dof_params)
                if dof_resp.status_code == 200:
                    dof_data = dof_resp.json()
                    if dof_data:
                        d = dof_data[0]
                        result["success"] = True
                        result["has_dof"] = True
                        result["dof_year"] = d.get("year", "")
                        result["dof_assessed"] = _safe_float(d.get("curacttot"))
                        result["dof_exempt"] = _safe_float(d.get("curactextot"))
                        result["dof_taxable"] = _safe_float(d.get("curtxbtot"))
                        result["dof_market"] = _safe_float(d.get("curmkttot"))
                        result["assessed_value"] = result["dof_assessed"]
                        result["market_value"] = result["dof_market"]
                        result["tax_class"] = d.get("curtaxclass", "")
        except httpx.TimeoutException:
            result["error"] = "Request timed out"
        except Exception as exc:
            result["error"] = str(exc)[:200]

        return result

    async def fetch_acris(self, borough: int, block: str, lot: str) -> AcrisSummary:
        """Fetch ACRIS deed/mortgage records for a single lot."""
        summary = AcrisSummary()
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=_request_headers()) as client:
                # Step 1: find document IDs from the legals table for this lot
                legals_params = {
                    "$where": (
                        f"borough='{borough}' AND block={int(block)} AND lot={int(lot)}"
                    ),
                    "$select": "document_id",
                    "$limit": 200,
                }
                legals_resp = await client.get(ACRIS_LEGALS_ENDPOINT, params=legals_params)
                legals_resp.raise_for_status()
                legals_rows = legals_resp.json()
                if not legals_rows:
                    return summary
                doc_ids = list({row["document_id"] for row in legals_rows if row.get("document_id")})
                if not doc_ids:
                    return summary

                # Step 2: fetch master records for those document IDs
                # Focus on deeds & mortgages only, most recent first
                id_list = ",".join(f"'{did}'" for did in doc_ids[:100])
                master_params = {
                    "$where": (
                        f"document_id in({id_list}) AND "
                        "doc_type in('DEED','DEED, RP TO CONDO','MTGE','AGMT','ASST','CNTR','LEAS','RPTT','CORRP')"
                    ),
                    "$order": "doc_date DESC",
                    "$limit": 50,
                }
                master_resp = await client.get(ACRIS_MASTER_ENDPOINT, params=master_params)
                master_resp.raise_for_status()
                master_rows = master_resp.json()
                if not master_rows:
                    return summary

                master_by_id = {row["document_id"]: row for row in master_rows}

                # Step 3: fetch parties for those document IDs
                master_id_list = ",".join(f"'{did}'" for did in master_by_id.keys())
                parties_params = {
                    "$where": f"document_id in({master_id_list})",
                    "$limit": 500,
                }
                parties_resp = await client.get(ACRIS_PARTIES_ENDPOINT, params=parties_params)
                parties_resp.raise_for_status()
                parties_rows = parties_resp.json()

                # Group parties by document_id and party_type
                parties_by_doc: dict[str, dict[str, list[str]]] = {}
                for p in parties_rows:
                    did = p.get("document_id", "")
                    ptype = str(p.get("party_type", "")).strip()
                    name = p.get("name", "")
                    if did and name:
                        parties_by_doc.setdefault(did, {}).setdefault(ptype, []).append(name)

                # Build documents
                total_mortgage = 0.0
                docs: list[AcrisDocument] = []
                for m in master_rows:
                    did = m.get("document_id", "")
                    parties = parties_by_doc.get(did, {})
                    # party_type "1" = grantor/seller/borrower, "2" = grantee/buyer/lender
                    party1_names = parties.get("1", [])
                    party2_names = parties.get("2", [])
                    amount = _safe_float(m.get("doc_amount"))
                    doc_type = m.get("doc_type", "")

                    docs.append(AcrisDocument(
                        document_id=did,
                        doc_type=doc_type,
                        doc_date=m.get("doc_date"),
                        recorded_filed=m.get("recorded_datetime"),
                        doc_amount=amount if amount > 0 else None,
                        party1="; ".join(party1_names[:3]),
                        party2="; ".join(party2_names[:3]),
                    ))

                    if doc_type in ("MTGE",) and amount > 0:
                        total_mortgage += amount

                summary.documents = docs[:20]  # cap at 20 most recent
                summary.total_mortgage_amount = total_mortgage if total_mortgage > 0 else None

                # Find most recent deed
                for doc in docs:
                    if doc.doc_type and "DEED" in doc.doc_type:
                        summary.last_deed_date = doc.doc_date
                        summary.last_deed_amount = doc.doc_amount
                        summary.last_deed_seller = doc.party1
                        summary.last_deed_buyer = doc.party2
                        break

        except httpx.TimeoutException:
            pass
        except Exception:
            pass

        return summary

    async def fetch_hpd_violations(self, borough: int, block: str, lot: str) -> HpdViolationSummary:
        """Fetch HPD violation summary for a single lot."""
        summary = HpdViolationSummary()
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=_request_headers()) as client:
                params = {
                    "$where": (
                        f"boroid='{borough}' AND block='{block}' AND lot='{lot}' "
                        "AND currentstatus='Open'"
                    ),
                    "$select": "class,inspectiondate,rentimpairing",
                    "$limit": 500,
                }
                resp = await client.get(HPD_VIOLATIONS_ENDPOINT, params=params)
                resp.raise_for_status()
                rows = resp.json()
                for row in rows:
                    cls = str(row.get("class", "")).upper()
                    if cls == "A":
                        summary.open_class_a += 1
                    elif cls == "B":
                        summary.open_class_b += 1
                    elif cls == "C":
                        summary.open_class_c += 1
                    if str(row.get("rentimpairing", "")).upper() == "YES":
                        summary.rent_impairing += 1
                summary.total_open = summary.open_class_a + summary.open_class_b + summary.open_class_c
                dates = [row.get("inspectiondate", "") for row in rows if row.get("inspectiondate")]
                if dates:
                    summary.most_recent_date = sorted(dates, reverse=True)[0][:10]
        except (httpx.TimeoutException, Exception):
            pass
        return summary

    async def fetch_dob_jobs(self, borough: int, block: str, lot: str) -> DobJobSummary:
        """Fetch active DOB job applications for a single lot."""
        summary = DobJobSummary()
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=_request_headers()) as client:
                params = {
                    "$where": (
                        f"borough='{borough}' AND block='{block.zfill(5)}' AND lot='{lot.zfill(4)}' "
                        "AND job_status NOT IN('X CANCELLED','R DISAPPROVED')"
                    ),
                    "$select": "job__,job_type,job_status,initial_cost,proposed_dwelling_units,"
                               "existing_dwelling_units,proposed_zoning_sqft",
                    "$order": "latest_action_date DESC",
                    "$limit": 20,
                }
                resp = await client.get(DOB_JOBS_ENDPOINT, params=params)
                resp.raise_for_status()
                rows = resp.json()
                for row in rows:
                    jtype = str(row.get("job_type", "")).strip()
                    jstatus = str(row.get("job_status", "")).strip()
                    rec = DobJobRecord(
                        job_number=str(row.get("job__", "")),
                        job_type=jtype,
                        job_status=jstatus,
                        initial_cost=_safe_float(row.get("initial_cost")) or None,
                        proposed_dwelling_units=_safe_int(row.get("proposed_dwelling_units")) or None,
                        existing_dwelling_units=_safe_int(row.get("existing_dwelling_units")) or None,
                        proposed_zoning_sqft=_safe_float(row.get("proposed_zoning_sqft")) or None,
                    )
                    summary.active_jobs.append(rec)
                    if jtype == "NB":
                        summary.has_active_new_building = True
                    if jtype in ("A1", "A2", "A3"):
                        summary.has_active_alteration = True
                summary.total_active = len(summary.active_jobs)
        except (httpx.TimeoutException, Exception):
            pass
        return summary

    async def fetch_ecb_violations(self, borough: int, block: str, lot: str) -> EcbViolationSummary:
        """Fetch ECB/OATH violation summary for a single lot."""
        summary = EcbViolationSummary()
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=_request_headers()) as client:
                params = {
                    "$where": (
                        f"boro='{borough}' AND block='{block}' AND lot='{lot}' "
                        "AND hearing_status != 'RESOLVE'"
                    ),
                    "$select": "penality_imposed,amount_paid,balance_due,violation_date",
                    "$limit": 200,
                }
                resp = await client.get(ECB_VIOLATIONS_ENDPOINT, params=params)
                resp.raise_for_status()
                rows = resp.json()
                dates = []
                for row in rows:
                    summary.open_violations += 1
                    summary.total_penalties += _safe_float(row.get("penality_imposed"))
                    summary.total_balance_due += _safe_float(row.get("balance_due"))
                    vdate = row.get("violation_date", "")
                    if vdate:
                        dates.append(vdate)
                if dates:
                    summary.most_recent_date = sorted(dates, reverse=True)[0][:10]
        except (httpx.TimeoutException, Exception):
            pass
        return summary

    async def fetch_comparable_sales(self, borough: int, block: str, lot: str) -> ComparableSalesSummary:
        """Fetch DOF rolling sales for the subject lot and block comps."""
        summary = ComparableSalesSummary()
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=_request_headers()) as client:
                # Subject lot sale
                params = {
                    "$where": f"borough='{borough}' AND block='{block}' AND lot='{lot}' AND sale_price > '0'",
                    "$order": "sale_date DESC",
                    "$limit": 1,
                }
                resp = await client.get(DOF_SALES_ENDPOINT, params=params)
                resp.raise_for_status()
                rows = resp.json()
                if rows:
                    r = rows[0]
                    summary.subject_sale = DofSaleRecord(
                        sale_price=_safe_float(r.get("sale_price")),
                        sale_date=(r.get("sale_date") or "")[:10],
                        building_class=r.get("building_class_at_time_of_sale", ""),
                        residential_units=_safe_int(r.get("residential_units")),
                        commercial_units=_safe_int(r.get("commercial_units")),
                        total_units=_safe_int(r.get("total_units")),
                        gross_square_feet=_safe_float(r.get("gross_square_feet")) or None,
                    )

                # Block comps (same block, exclude subject lot)
                comp_params = {
                    "$where": (
                        f"borough='{borough}' AND block='{block}' AND lot!='{lot}' "
                        "AND sale_price > '0'"
                    ),
                    "$order": "sale_date DESC",
                    "$limit": 10,
                }
                comp_resp = await client.get(DOF_SALES_ENDPOINT, params=comp_params)
                comp_resp.raise_for_status()
                comp_rows = comp_resp.json()
                for r in comp_rows:
                    summary.comparable_sales.append(DofSaleRecord(
                        sale_price=_safe_float(r.get("sale_price")),
                        sale_date=(r.get("sale_date") or "")[:10],
                        building_class=r.get("building_class_at_time_of_sale", ""),
                        residential_units=_safe_int(r.get("residential_units")),
                        commercial_units=_safe_int(r.get("commercial_units")),
                        total_units=_safe_int(r.get("total_units")),
                        gross_square_feet=_safe_float(r.get("gross_square_feet")) or None,
                    ))
                summary.total_found = (1 if summary.subject_sale else 0) + len(summary.comparable_sales)
        except (httpx.TimeoutException, Exception):
            pass
        return summary

    async def fetch_hpd_litigations(self, borough: int, block: str, lot: str) -> HpdLitigationSummary:
        """Fetch HPD litigation cases for a single lot."""
        summary = HpdLitigationSummary()
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=_request_headers()) as client:
                params = {
                    "$where": f"boroid='{borough}' AND block='{block}' AND lot='{lot}' AND casestatus='OPEN'",
                    "$select": "casetype,caseopendate",
                    "$limit": 50,
                }
                resp = await client.get(HPD_LITIGATIONS_ENDPOINT, params=params)
                resp.raise_for_status()
                rows = resp.json()
                types = set()
                dates = []
                for row in rows:
                    summary.open_cases += 1
                    ct = row.get("casetype", "")
                    if ct:
                        types.add(ct)
                    d = row.get("caseopendate", "")
                    if d:
                        dates.append(d)
                summary.case_types = sorted(types)
                if dates:
                    summary.most_recent_date = sorted(dates, reverse=True)[0][:10]
        except (httpx.TimeoutException, Exception):
            pass
        return summary

    async def fetch_fdny_vacates(self, borough: int, block: str, lot: str) -> FdnyVacateSummary:
        """Fetch FDNY vacate orders for a single lot."""
        summary = FdnyVacateSummary()
        bbl = f"{borough}{block.zfill(5)}{lot.zfill(4)}"
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=_request_headers()) as client:
                params = {
                    "$where": f"bbl='{bbl}'",
                    "$select": "vacate_type,number_of_vacated_units,last_disposition_date_time",
                    "$limit": 50,
                }
                resp = await client.get(FDNY_VACATE_ENDPOINT, params=params)
                resp.raise_for_status()
                rows = resp.json()
                for row in rows:
                    summary.total_vacate_orders += 1
                    vtype = str(row.get("vacate_type", "")).upper()
                    if "RESC" not in vtype:
                        summary.active_vacate_orders += 1
                    summary.vacated_units += _safe_int(row.get("number_of_vacated_units"))
        except (httpx.TimeoutException, Exception):
            pass
        return summary

    async def build_property_context(self, primary_bbl: str, adjacent_bbls: list[str] | None = None) -> PropertyContext:
        adjacent_bbls = adjacent_bbls or []
        primary_clean = normalize_bbl(primary_bbl)
        if len(primary_clean) != 10:
            raise ValueError("primary_bbl must be a 10-digit BBL")

        selected_bbls = [primary_clean]
        seen = {primary_clean}
        primary_borough, primary_block, primary_lot = parse_bbl_parts(primary_clean)

        for candidate in adjacent_bbls:
            cleaned = normalize_bbl(candidate)
            if len(cleaned) != 10:
                raise ValueError("All adjacent_bbls must be 10-digit BBL values.")
            borough, block, _lot = parse_bbl_parts(cleaned)
            if borough != primary_borough or block != primary_block:
                raise ValueError("Adjacent lots must be on the same borough and block as the primary lot.")
            if cleaned not in seen:
                selected_bbls.append(cleaned)
                seen.add(cleaned)

        results: list[dict[str, Any]] = []
        for bbl in selected_bbls:
            borough, block, lot = parse_bbl_parts(bbl)
            lot_result = await self.lookup_bbl(borough, block, lot)
            lot_result["bbl"] = bbl
            if not lot_result.get("has_pluto"):
                raise LookupError(f"Property data is unavailable in PLUTO for BBL {bbl}.")
            results.append(lot_result)

        lots_detail: list[PropertyLotRecord] = []
        for item in results:
            lot_type_code = item.get("lot_type_code")
            lots_detail.append(
                PropertyLotRecord(
                    bbl=item["bbl"],
                    borough=item.get("borough", ""),
                    block=str(item.get("block", "")),
                    lot=str(item.get("lot", "")),
                    address=item.get("address", "") or "",
                    zoning=item.get("zoning", "") or "",
                    overlay1=item.get("overlay1"),
                    overlay2=item.get("overlay2"),
                    lot_area=_safe_float(item.get("lot_area")),
                    building_area=_safe_float(item.get("building_area") or item.get("bldg_area")),
                    res_far=_safe_float(item.get("res_far")),
                    units_total=_safe_int(item.get("units_total")),
                    year_built=item.get("year_built"),
                    assessed_value=item.get("assessed_value"),
                    market_value=item.get("market_value"),
                    dof_taxable=item.get("dof_taxable"),
                    has_pluto=bool(item.get("has_pluto")),
                    has_dof=bool(item.get("has_dof")),
                    lot_type_code=lot_type_code,
                    lot_type=infer_lot_type(lot_type_code),
                    raw={k: v for k, v in item.items() if k != "bbl"},
                )
            )

        primary = lots_detail[0]
        combined_lot_area = sum(item.lot_area for item in lots_detail)

        # Fetch ACRIS records for the primary lot
        acris_summary = await self.fetch_acris(primary_borough, primary_block, primary_lot)
        if acris_summary.documents:
            lots_detail[0].has_acris = True

        # Fetch all additional data sources in parallel
        (
            hpd_violations,
            dob_jobs,
            ecb_violations,
            comparable_sales,
            hpd_litigations,
            fdny_vacates,
        ) = await asyncio.gather(
            self.fetch_hpd_violations(primary_borough, primary_block, primary_lot),
            self.fetch_dob_jobs(primary_borough, primary_block, primary_lot),
            self.fetch_ecb_violations(primary_borough, primary_block, primary_lot),
            self.fetch_comparable_sales(primary_borough, primary_block, primary_lot),
            self.fetch_hpd_litigations(primary_borough, primary_block, primary_lot),
            self.fetch_fdny_vacates(primary_borough, primary_block, primary_lot),
        )
        if hpd_violations.total_open:
            lots_detail[0].has_hpd = True
        if dob_jobs.total_active:
            lots_detail[0].has_dob = True
        if ecb_violations.open_violations:
            lots_detail[0].has_ecb = True
        if comparable_sales.total_found:
            lots_detail[0].has_sales = True
        if hpd_litigations.open_cases:
            lots_detail[0].has_litigation = True
        if fdny_vacates.total_vacate_orders:
            lots_detail[0].has_fdny = True
        combined_building_area = sum(item.building_area for item in lots_detail)
        combined_units_total = sum(item.units_total for item in lots_detail)
        aggregated_assessed = sum(item.assessed_value or 0 for item in lots_detail) or None
        aggregated_market = sum(item.market_value or 0 for item in lots_detail) or None
        aggregated_taxable = sum(item.dof_taxable or 0 for item in lots_detail) or None

        overlay = str(primary.overlay1 or primary.overlay2 or "").strip().upper()
        zoning_info = get_zoning_info(primary.zoning, street_type="narrow") or {}
        standard_far = zoning_info.get("standard")
        qah_far = zoning_info.get("uap") if zoning_info.get("uap") is not None else primary.res_far or None
        if standard_far is None and primary.res_far > 0:
            standard_far = primary.res_far
        if qah_far is None and primary.res_far > 0:
            qah_far = primary.res_far

        context = PropertyContext(
            primary_bbl=primary_clean,
            adjacent_bbls=[bbl for bbl in selected_bbls[1:]],
            selected_bbls=selected_bbls,
            address=primary.address,
            borough=primary.borough,
            block=primary.block,
            lots=[primary_lot] + [parse_bbl_parts(bbl)[2] for bbl in selected_bbls[1:]],
            zoning_district=primary.zoning,
            overlay=overlay,
            overlay_far=get_overlay_far(overlay),
            community_facility_far=zoning_info.get("cf_far"),
            standard_far=standard_far,
            qah_far=qah_far,
            standard_height_limit=zoning_info.get("height_limit_standard"),
            qah_height_limit=zoning_info.get("height_limit_uap"),
            lot_coverage_corner=zoning_info.get("lot_coverage_corner"),
            lot_coverage_interior=zoning_info.get("lot_coverage_interior"),
            street_type_assumption=str(zoning_info.get("street_type_assumption") or "narrow"),
            has_narrow_wide=bool(zoning_info.get("has_narrow_wide")),
            lot_type=primary.lot_type,
            lot_area=combined_lot_area,
            building_area=combined_building_area,
            units_total=combined_units_total,
            assessed_value=aggregated_assessed,
            market_value=aggregated_market,
            dof_taxable=aggregated_taxable,
            scenarios=_calculate_all_scenarios(combined_lot_area, _safe_float(standard_far), _safe_float(qah_far)),
            lots_detail=lots_detail,
            acris_summary=acris_summary if acris_summary.documents else None,
            hpd_violations=hpd_violations if hpd_violations.total_open else None,
            dob_jobs=dob_jobs if dob_jobs.total_active else None,
            ecb_violations=ecb_violations if ecb_violations.open_violations else None,
            comparable_sales=comparable_sales if comparable_sales.total_found else None,
            hpd_litigations=hpd_litigations if hpd_litigations.open_cases else None,
            fdny_vacates=fdny_vacates if fdny_vacates.total_vacate_orders else None,
            sources={
                "pluto_endpoint": PLUTO_ENDPOINT,
                "dof_endpoint": DOF_VALUATION_ENDPOINT,
                "acris_legals_endpoint": ACRIS_LEGALS_ENDPOINT,
                "acris_master_endpoint": ACRIS_MASTER_ENDPOINT,
                "hpd_violations_endpoint": HPD_VIOLATIONS_ENDPOINT,
                "dob_jobs_endpoint": DOB_JOBS_ENDPOINT,
                "ecb_violations_endpoint": ECB_VIOLATIONS_ENDPOINT,
                "dof_sales_endpoint": DOF_SALES_ENDPOINT,
                "hpd_litigations_endpoint": HPD_LITIGATIONS_ENDPOINT,
                "fdny_vacate_endpoint": FDNY_VACATE_ENDPOINT,
                "zoning_reference": "local_nyc_zoning_reference",
                "street_type_assumption": "narrow",
                "generated_at": _utc_now_iso(),
            },
            property_brief="",
        )
        context.property_brief = self.build_property_brief(context)
        return context

    def _build_acris_brief(self, context: PropertyContext) -> str:
        if not context.acris_summary or not context.acris_summary.documents:
            return ""
        a = context.acris_summary
        lines = ["ACRIS TRANSACTION HISTORY\n"]
        if a.last_deed_date:
            lines.append(
                f"Last deed: {a.last_deed_date[:10] if a.last_deed_date else 'N/A'}, "
                f"amount {f'${a.last_deed_amount:,.0f}' if a.last_deed_amount else 'N/A'}, "
                f"seller {a.last_deed_seller or 'N/A'}, buyer {a.last_deed_buyer or 'N/A'}.\n"
            )
        if a.total_mortgage_amount:
            lines.append(f"Total recorded mortgage amount: ${a.total_mortgage_amount:,.0f}.\n")
        lines.append(f"Total ACRIS documents found: {len(a.documents)}.\n")
        return "".join(lines)

    def _build_hpd_brief(self, context: PropertyContext) -> str:
        if not context.hpd_violations:
            return ""
        v = context.hpd_violations
        lines = [
            "HPD VIOLATIONS\n",
            f"Open violations: {v.total_open} (Class A: {v.open_class_a}, B: {v.open_class_b}, C: {v.open_class_c}).\n",
        ]
        if v.rent_impairing:
            lines.append(f"Rent-impairing violations: {v.rent_impairing}.\n")
        if v.most_recent_date:
            lines.append(f"Most recent inspection: {v.most_recent_date}.\n")
        return "".join(lines)

    def _build_dob_brief(self, context: PropertyContext) -> str:
        if not context.dob_jobs:
            return ""
        d = context.dob_jobs
        lines = [f"DOB JOB APPLICATIONS\nActive jobs: {d.total_active}."]
        if d.has_active_new_building:
            lines.append(" Includes active New Building application.")
        if d.has_active_alteration:
            lines.append(" Includes active Alteration application.")
        lines.append("\n")
        for j in d.active_jobs[:5]:
            cost_str = f"${j.initial_cost:,.0f}" if j.initial_cost else "N/A"
            lines.append(f"- Job {j.job_number}: type={j.job_type}, status={j.job_status}, cost={cost_str}")
            if j.proposed_dwelling_units:
                lines.append(f", proposed units={j.proposed_dwelling_units}")
            lines.append(".\n")
        return "".join(lines)

    def _build_ecb_brief(self, context: PropertyContext) -> str:
        if not context.ecb_violations:
            return ""
        e = context.ecb_violations
        lines = [
            "ECB/OATH VIOLATIONS\n",
            f"Open violations: {e.open_violations}. ",
            f"Total penalties: ${e.total_penalties:,.0f}. Balance due: ${e.total_balance_due:,.0f}.\n",
        ]
        if e.most_recent_date:
            lines.append(f"Most recent: {e.most_recent_date}.\n")
        return "".join(lines)

    def _build_sales_brief(self, context: PropertyContext) -> str:
        if not context.comparable_sales:
            return ""
        s = context.comparable_sales
        lines = ["DOF ROLLING SALES\n"]
        if s.subject_sale:
            price = f"${s.subject_sale.sale_price:,.0f}" if s.subject_sale.sale_price else "N/A"
            lines.append(f"Subject lot last sale: {s.subject_sale.sale_date or 'N/A'}, price {price}.\n")
        if s.comparable_sales:
            lines.append(f"Block comparables ({len(s.comparable_sales)} found):\n")
            for c in s.comparable_sales[:5]:
                price = f"${c.sale_price:,.0f}" if c.sale_price else "N/A"
                sqft = f"{c.gross_square_feet:,.0f} SF" if c.gross_square_feet else "N/A"
                lines.append(f"- {c.sale_date or 'N/A'}: {price}, {sqft}, {c.total_units} units.\n")
        return "".join(lines)

    def _build_litigation_brief(self, context: PropertyContext) -> str:
        if not context.hpd_litigations:
            return ""
        l = context.hpd_litigations
        types_str = ", ".join(l.case_types) if l.case_types else "N/A"
        return (
            "HPD LITIGATIONS\n"
            f"Open cases: {l.open_cases}. Types: {types_str}. "
            f"Most recent: {l.most_recent_date or 'N/A'}.\n"
        )

    def _build_fdny_brief(self, context: PropertyContext) -> str:
        if not context.fdny_vacates:
            return ""
        f = context.fdny_vacates
        return (
            "FDNY VACATE ORDERS\n"
            f"Total orders: {f.total_vacate_orders}. Active: {f.active_vacate_orders}. "
            f"Vacated units: {f.vacated_units}.\n"
        )

    def build_property_brief(self, context: PropertyContext) -> str:
        lot_lines = []
        for lot in context.lots_detail:
            lot_lines.append(
                f"- BBL {lot.bbl}: {lot.address or 'Unknown address'}, zone {lot.zoning or 'N/A'}, "
                f"lot area {lot.lot_area:,.0f} SF, building area {lot.building_area:,.0f} SF, "
                f"units {lot.units_total}, year built {lot.year_built or 'N/A'}, "
                f"market value {f'${lot.market_value:,.0f}' if lot.market_value else 'N/A'}, "
                f"taxable value {f'${lot.dof_taxable:,.0f}' if lot.dof_taxable else 'N/A'}."
            )

        scenario_lines = []
        for scenario in context.scenarios:
            notes_suffix = f" Notes: {'; '.join(scenario.notes)}." if scenario.notes else ""
            scenario_lines.append(
                f"- {scenario.label} [{scenario.code}]: "
                f"{scenario.max_res_floor_area:,} SF max res FA, "
                f"{scenario.max_number_of_units} total units, "
                f"{scenario.affordable_units_total} affordable units, "
                f"{scenario.market_rate_units} market-rate units, "
                f"{scenario.affordable_units_percentage * 100:.1f}% affordable share, "
                f"prevailing wages trigger={scenario.triggers_prevailing_wages}, "
                f"40% AMI trigger={scenario.triggers_40_ami}, "
                f"available={scenario.available}.{notes_suffix}"
            )

        return (
            "ACTIVE PROPERTY CONTEXT\n"
            f"Primary site: {context.address or 'Unknown address'} in {context.borough or 'Unknown borough'}.\n"
            f"Selected BBLs: {', '.join(context.selected_bbls)}.\n"
            f"Tax block: {context.block}. Lots: {', '.join(context.lots)}.\n"
            f"Zoning: {context.zoning_district or 'N/A'}.\n"
            f"Overlay: {context.overlay or 'None'} (overlay FAR {context.overlay_far if context.overlay_far is not None else 'N/A'}).\n"
            f"Residential FAR: standard {context.standard_far if context.standard_far is not None else 'N/A'}, "
            f"UAP/QAH {context.qah_far if context.qah_far is not None else 'N/A'}.\n"
            f"Community facility FAR: {context.community_facility_far if context.community_facility_far is not None else 'N/A'}.\n"
            f"Height limits: standard {context.standard_height_limit if context.standard_height_limit is not None else 'N/A'} ft, "
            f"UAP {context.qah_height_limit if context.qah_height_limit is not None else 'N/A'} ft.\n"
            f"Lot coverage: corner {context.lot_coverage_corner if context.lot_coverage_corner is not None else 'N/A'}%, "
            f"interior {context.lot_coverage_interior if context.lot_coverage_interior is not None else 'N/A'}%.\n"
            f"Lot type: {context.lot_type}. Street-type assumption for zoning tables: {context.street_type_assumption}.\n"
            f"Combined lot area: {context.lot_area:,.0f} SF. Combined building area: {context.building_area:,.0f} SF.\n"
            f"Existing total units: {context.units_total}.\n"
            f"Combined assessed value: {f'${context.assessed_value:,.0f}' if context.assessed_value else 'N/A'}.\n"
            f"Combined market value: {f'${context.market_value:,.0f}' if context.market_value else 'N/A'}.\n"
            f"Combined taxable value: {f'${context.dof_taxable:,.0f}' if context.dof_taxable else 'N/A'}.\n"
            + self._build_acris_brief(context)
            + self._build_hpd_brief(context)
            + self._build_dob_brief(context)
            + self._build_ecb_brief(context)
            + self._build_sales_brief(context)
            + self._build_litigation_brief(context)
            + self._build_fdny_brief(context)
            + "LOT DETAILS\n"
            + "\n".join(lot_lines)
            + "\nSCENARIO CANDIDATES\n"
            + "\n".join(scenario_lines)
            + "\nUse this as canonical live site context. If uploaded documents conflict with it, call out the conflict explicitly."
        )

    async def _fetch_pluto_data(self, client: httpx.AsyncClient, borough: int, block: int, lot: int) -> Optional[dict[str, Any]]:
        borough_abbrev = BOROUGH_ABBREV.get(borough, "BK")
        params = {"$where": f"borough='{borough_abbrev}' AND block='{block}' AND lot='{lot}'", "$limit": 1}
        response = await client.get(PLUTO_ENDPOINT, params=params)
        response.raise_for_status()
        rows = response.json()
        return rows[0] if rows else None

    async def _fetch_pluto_by_bbl_str(self, client: httpx.AsyncClient, bbl: str) -> Optional[dict[str, Any]]:
        borough, block, lot = parse_bbl_parts(bbl)
        return await self._fetch_pluto_data(client, borough, int(block), int(lot))

    async def _search_by_bbl(self, client: httpx.AsyncClient, bbl_input: str) -> list[dict[str, Any]]:
        pluto = await self._fetch_pluto_by_bbl_str(client, bbl_input)
        if not pluto:
            return []
        return [self._pluto_to_search_result(pluto)]

    async def _geocode(self, client: httpx.AsyncClient, address: str) -> list[dict[str, Any]]:
        response = await client.get(GEOSEARCH_ENDPOINT, params={"text": address}, timeout=5.0)
        response.raise_for_status()
        data = response.json()
        features = data.get("features", [])
        results: list[dict[str, Any]] = []
        for feature in features:
            props = feature.get("properties") or {}
            coords = (feature.get("geometry") or {}).get("coordinates", [0, 0])
            addendum = props.get("addendum") or {}
            pad = addendum.get("pad") or {}
            bbl = pad.get("bbl") or props.get("pad_bbl") or ""
            if not bbl:
                continue
            results.append(
                {
                    "label": props.get("label") or props.get("name") or "",
                    "bbl": bbl,
                    "borough": props.get("borough", ""),
                    "lat": coords[1] if len(coords) > 1 else 0,
                    "lng": coords[0] if len(coords) > 0 else 0,
                }
            )
        return results

    async def _search_pluto_direct(self, client: httpx.AsyncClient, address: str) -> list[dict[str, Any]]:
        parsed = _parse_address(address)
        where_clauses: list[str] = []

        if parsed["houseNumber"] and parsed["street"]:
            street = str(parsed["street"]).upper()
            for old, new in [("STREET", "ST"), ("AVENUE", "AVE"), ("BOULEVARD", "BLVD"), ("DRIVE", "DR"), ("PLACE", "PL"), ("ROAD", "RD")]:
                street = re.sub(rf"\b{old}\b", new, street)
            street = _escape_socrata_value(street.strip())
            house = _escape_socrata_value(str(parsed["houseNumber"]))
            where_clauses.append(f"upper(address) LIKE '%{house} {street}%'")
        elif parsed["street"]:
            street = _escape_socrata_value(str(parsed["street"]).upper())
            where_clauses.append(f"upper(address) LIKE '%{street}%'")

        if parsed["borough"]:
            code = BORO_ALIASES.get(str(parsed["borough"]))
            if code:
                where_clauses.append(f"borocode='{code}'")

        if not where_clauses:
            return []

        response = await client.get(
            PLUTO_ENDPOINT,
            params={"$where": " AND ".join(where_clauses), "$limit": 10, "$order": "address ASC"},
            timeout=8.0,
        )
        response.raise_for_status()
        return [self._pluto_to_search_result(row) for row in response.json()]

    async def _search_by_address(self, client: httpx.AsyncClient, address: str) -> list[dict[str, Any]]:
        try:
            geo_results = await self._geocode(client, address)
        except Exception:
            geo_results = []

        if geo_results:
            results: list[dict[str, Any]] = []
            seen: set[str] = set()
            for geo in geo_results[:8]:
                bbl = str(geo.get("bbl") or "")
                if not bbl or bbl in seen:
                    continue
                seen.add(bbl)
                try:
                    pluto = await self._fetch_pluto_by_bbl_str(client, bbl)
                except Exception:
                    pluto = None
                if not pluto:
                    continue
                result = self._pluto_to_search_result(pluto)
                if not result.get("lat") and geo.get("lat"):
                    result["lat"] = geo["lat"]
                if not result.get("lng") and geo.get("lng"):
                    result["lng"] = geo["lng"]
                results.append(result)
            if results:
                return results

        try:
            return await self._search_pluto_direct(client, address)
        except Exception:
            return []

    def _pluto_to_search_result(self, pluto: dict[str, Any]) -> dict[str, Any]:
        bc = pluto.get("borocode") or pluto.get("borough", "1")
        boro_map = {"MN": "1", "BX": "2", "BK": "3", "QN": "4", "SI": "5"}
        if bc in boro_map:
            bc = boro_map[bc]
        block = str(pluto.get("block", "0")).zfill(5)
        lot = str(pluto.get("lot", "0")).zfill(4)
        bbl = f"{bc}{block}{lot}"
        borough_name = BOROUGH_NAMES.get(_safe_int(bc, 0), "Unknown")
        overlay = str(pluto.get("overlay1") or pluto.get("overlay2") or "").strip().upper()
        return {
            "bbl": bbl,
            "address": pluto.get("address", "Unknown"),
            "borough": borough_name,
            "zone": pluto.get("zonedist1", "") or "",
            "overlay": overlay,
            "lotArea": _safe_float(pluto.get("lotarea")),
            "builtFar": _safe_float(pluto.get("builtfar")),
            "numFloors": _safe_float(pluto.get("numfloors")),
            "yearBuilt": _safe_int(pluto.get("yearbuilt")),
            "bldgClass": pluto.get("bldgclass", "") or "",
            "lat": _safe_float(pluto.get("latitude")),
            "lng": _safe_float(pluto.get("longitude")),
        }


property_service = PropertyService()

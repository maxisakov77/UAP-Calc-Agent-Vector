"""
Live NYC property lookup and normalized property-context builder.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from property_models import PropertyContext, PropertyLotRecord, PropertyScenario
from zoning_reference import get_overlay_far, get_zoning_info, infer_lot_type


PLUTO_ENDPOINT = "https://data.cityofnewyork.us/resource/64uk-42ks.json"
DOF_VALUATION_ENDPOINT = "https://data.cityofnewyork.us/resource/8y4t-faws.json"
GEOSEARCH_ENDPOINT = "https://geosearch.planninglabs.nyc/v2/search"

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
            sources={
                "pluto_endpoint": PLUTO_ENDPOINT,
                "dof_endpoint": DOF_VALUATION_ENDPOINT,
                "zoning_reference": "local_nyc_zoning_reference",
                "street_type_assumption": "narrow",
                "generated_at": _utc_now_iso(),
            },
            property_brief="",
        )
        context.property_brief = self.build_property_brief(context)
        return context

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
            "LOT DETAILS\n"
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

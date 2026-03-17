"""
Domain-specific knowledge for NYC UAP underwriting spreadsheets.

This module provides a structured glossary that teaches the LLM what each
section, label, and common abbreviation means in a typical UAP underwriting
template.  It is injected into the extraction prompt so the model can
map source-document values to cells even when the labels are cryptic.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Canonical section / label glossary
# ---------------------------------------------------------------------------
# Each entry maps a category name to a list of (label_pattern, meaning) pairs.
# label_pattern is a short phrase the LLM should try to match against cell
# labels in the spreadsheet; meaning explains what value belongs there and
# where to find it in typical source documents.
# ---------------------------------------------------------------------------

UNDERWRITING_GLOSSARY: dict[str, list[tuple[str, str]]] = {
    # ------------------------------------------------------------------
    # PROPERTY / SITE INFORMATION
    # ------------------------------------------------------------------
    "Property Information": [
        ("Address", "The street address of the property (e.g. '123 Main St')."),
        ("Borough", "NYC borough: Manhattan, Bronx, Brooklyn, Queens, or Staten Island."),
        ("BBL", "10-digit Borough-Block-Lot identifier (e.g. 1005670012)."),
        ("Block", "NYC tax block number."),
        ("Lot", "NYC tax lot number."),
        ("Zoning", "NYC zoning district code (e.g. R7A, C4-4A)."),
        ("Overlay", "Commercial overlay if any (e.g. C2-4)."),
        ("Lot Area", "Total lot area in square feet (SF). Found in PLUTO or survey."),
        ("Lot Type", "Corner lot or interior lot (affects lot coverage)."),
        ("Street Width", "Narrow or wide street classification (affects height/FAR in some zones)."),
        ("FAR", "Floor Area Ratio — the ratio of buildable floor area to lot area."),
        ("Standard FAR", "As-of-right residential FAR for the zoning district."),
        ("UAP FAR", "Residential FAR with Universal Affordability Preference bonus."),
        ("Max Buildable SF", "Lot Area × FAR = maximum buildable residential square footage."),
        ("Building Height", "Maximum permitted building height in feet."),
        ("Lot Coverage", "Maximum percentage of the lot the building footprint can cover."),
        ("Year Built", "The year the existing building was constructed."),
        ("Building Area", "Gross building area of the existing structure in SF."),
        ("Existing Units", "Current number of dwelling units in the existing building."),
        ("Community Facility FAR", "FAR permitted for community facility use."),
    ],

    # ------------------------------------------------------------------
    # UNIT MIX / PROGRAM
    # ------------------------------------------------------------------
    "Unit Mix": [
        ("Total Units", "Total number of residential dwelling units in the project."),
        ("Market Rate Units", "Units rented/sold at market rate (no income restrictions)."),
        ("Affordable Units", "Units restricted to households at or below a specified AMI."),
        ("Affordable %", "Percentage of total units (or floor area) that are affordable."),
        ("Studio", "Studio/efficiency apartments (typically 350-500 SF)."),
        ("1BR", "One-bedroom apartments (typically 550-700 SF)."),
        ("2BR", "Two-bedroom apartments (typically 750-1000 SF)."),
        ("3BR", "Three-bedroom apartments (typically 1000-1300 SF)."),
        ("Unit SF", "Square footage per unit type."),
        ("Avg Unit Size", "Average dwelling unit size in SF. Sometimes labeled 'DU Factor' or 'DUF' (commonly 680 SF)."),
        ("AMI", "Area Median Income — the income benchmark for affordable housing programs."),
        ("30% AMI", "Units restricted to households earning ≤30% of AMI (extremely low income)."),
        ("40% AMI", "Units restricted to households earning ≤40% of AMI (very low income)."),
        ("50% AMI", "Units restricted to households earning ≤50% of AMI (low income)."),
        ("60% AMI", "Units restricted to households earning ≤60% of AMI (low income)."),
        ("80% AMI", "Units restricted to households earning ≤80% of AMI (moderate income)."),
        ("100% AMI", "Units restricted to households earning ≤100% of AMI."),
        ("120% AMI", "Units restricted to households earning ≤120% of AMI (middle income)."),
        ("130% AMI", "Units restricted to households earning ≤130% of AMI."),
        ("Super", "Superintendent's unit (usually 1, not counted as affordable or market)."),
    ],

    # ------------------------------------------------------------------
    # REVENUE / INCOME
    # ------------------------------------------------------------------
    "Revenue": [
        ("Rent Roll", "Detailed listing of each unit's rent — the primary income source document."),
        ("GPR", "Gross Potential Rent — total annual rent if all units are occupied at scheduled rents."),
        ("Gross Potential Rent", "Same as GPR. Sum of all unit rents × 12 months."),
        ("Market Rent", "Monthly or annual rent for market-rate units."),
        ("Affordable Rent", "Monthly or annual rent for income-restricted units, set by AMI band."),
        ("Vacancy", "Vacancy rate or vacancy loss — typically 3-7% for stabilized properties."),
        ("Vacancy Loss", "Dollar amount of lost rent due to vacancy = GPR × vacancy rate."),
        ("Collection Loss", "Estimated uncollectable rent (bad debt), usually 1-2% of GPR."),
        ("EGI", "Effective Gross Income = GPR − vacancy loss − collection loss + other income."),
        ("Effective Gross Income", "Same as EGI."),
        ("Other Income", "Non-rent income: laundry, parking, storage, antenna, late fees, etc."),
        ("Laundry Income", "Revenue from coin-operated or card laundry facilities."),
        ("Parking Income", "Revenue from parking spaces or garage."),
        ("Storage Income", "Revenue from storage units/lockers."),
        ("Commercial Income", "Rent from ground-floor retail or commercial tenants."),
        ("Retail Rent", "Same as commercial income — rent from retail/commercial spaces."),
        ("Rent Per SF", "Rent expressed per square foot (annual or monthly)."),
        ("Rent Stabilized", "Indicates the unit/building is subject to NYC rent stabilization."),
        ("Legal Rent", "The legal regulated rent for a rent-stabilized unit."),
        ("Preferential Rent", "A rent below the legal regulated rent offered to a tenant."),
    ],

    # ------------------------------------------------------------------
    # OPERATING EXPENSES
    # ------------------------------------------------------------------
    "Operating Expenses": [
        ("Total OpEx", "Total annual operating expenses."),
        ("Operating Expenses", "Same as Total OpEx."),
        ("Real Estate Taxes", "Annual property tax. Sourced from DOF tax bills or RPIE filing."),
        ("Property Tax", "Same as Real Estate Taxes."),
        ("Tax Rate", "Effective tax rate (taxes / assessed value)."),
        ("Assessed Value", "NYC assessed value for tax purposes (DOF)."),
        ("Market Value", "DOF full market value estimate."),
        ("Insurance", "Annual property insurance premium."),
        ("Payroll", "Wages for building staff (super, porters, doormen, handymen)."),
        ("Management Fee", "Property management fee — often 3-6% of EGI."),
        ("Repairs & Maintenance", "Ongoing repair costs, not capital improvements."),
        ("R&M", "Abbreviation for Repairs & Maintenance."),
        ("Utilities", "Building-paid utilities — water/sewer, electric, gas, oil/fuel."),
        ("Water & Sewer", "NYC DEP water and sewer charges."),
        ("Electric", "Common-area or building-wide electricity cost."),
        ("Gas", "Natural gas / heating fuel cost (if paid by landlord)."),
        ("Fuel", "Heating fuel — oil, gas. Often labeled 'Fuel/Oil' or 'Oil/Gas'."),
        ("Oil", "Heating oil expense."),
        ("Elevator", "Elevator maintenance/service contract."),
        ("Legal", "Legal fees for tenant issues, filings, compliance."),
        ("Accounting", "Accounting, auditing, and tax preparation fees."),
        ("Administrative", "General admin costs — office supplies, phone, postage."),
        ("Decorating", "Turnover cost — painting, touch-ups between tenants."),
        ("Exterminating", "Pest control services."),
        ("Cleaning", "Common-area cleaning / janitorial."),
        ("Security", "Security services or systems."),
        ("Trash Removal", "Garbage and recycling collection if privately contracted."),
        ("Snow Removal", "Snow plowing / de-icing, common in NYC."),
        ("Reserves", "Replacement reserves — set-aside for future capital needs (typically $250-$500/unit/year)."),
        ("Replacement Reserves", "Same as Reserves."),
        ("Per Unit Expense", "Operating expenses expressed per unit per year."),
        ("Expense Ratio", "Total OpEx / EGI — measures operating efficiency."),
    ],

    # ------------------------------------------------------------------
    # NET OPERATING INCOME & VALUATION
    # ------------------------------------------------------------------
    "NOI & Valuation": [
        ("NOI", "Net Operating Income = EGI − Total Operating Expenses."),
        ("Net Operating Income", "Same as NOI."),
        ("Cap Rate", "Capitalization Rate — NOI / Property Value. Used for valuation."),
        ("Valuation", "Estimated property value, often NOI / Cap Rate."),
        ("Appraised Value", "Value determined by a licensed appraiser."),
        ("Price Per Unit", "Purchase price or value divided by total units (aka PPU)."),
        ("Price Per SF", "Purchase price or value divided by total square footage."),
        ("GRM", "Gross Rent Multiplier = Purchase Price / Annual Gross Rent."),
    ],

    # ------------------------------------------------------------------
    # ACQUISITION / SOURCES & USES
    # ------------------------------------------------------------------
    "Acquisition & Financing": [
        ("Purchase Price", "The acquisition cost or contract price for the property."),
        ("Acquisition Cost", "Total cost to acquire — purchase price + closing costs + transfer taxes."),
        ("Closing Costs", "Buyer's closing costs — title, attorney, mortgage recording tax, etc."),
        ("Transfer Tax", "NYC and NYS real property transfer taxes (RPT)."),
        ("Transfer Tax Rate", "Combined NYC+NYS transfer tax rate (typically 1.425% - 2.625% depending on price)."),
        ("Hard Costs", "Construction costs — direct building costs per SF."),
        ("Soft Costs", "Non-construction development costs — architecture, engineering, permits, fees."),
        ("Total Development Cost", "Hard costs + soft costs + land cost + financing costs."),
        ("TDC", "Abbreviation for Total Development Cost."),
        ("Cost Per SF", "Total development cost / gross buildable SF."),
        ("Cost Per Unit", "Total development cost / total units."),
        ("Equity", "Investor equity / cash contribution."),
        ("Equity Required", "Total equity needed = Total Cost − Total Debt."),
        ("LTV", "Loan-to-Value ratio = Loan Amount / Property Value."),
        ("LTC", "Loan-to-Cost ratio = Loan Amount / Total Cost."),
    ],

    # ------------------------------------------------------------------
    # DEBT SERVICE / FINANCING
    # ------------------------------------------------------------------
    "Debt Service": [
        ("Mortgage Amount", "Total loan principal / mortgage balance."),
        ("Loan Amount", "Same as Mortgage Amount."),
        ("Interest Rate", "Annual interest rate on the mortgage."),
        ("Amortization", "Amortization period in years (e.g. 30 years)."),
        ("Term", "Loan term in years (may differ from amortization)."),
        ("Annual Debt Service", "Total annual mortgage payments (principal + interest)."),
        ("ADS", "Abbreviation for Annual Debt Service."),
        ("Monthly Debt Service", "Monthly mortgage payment (P&I)."),
        ("DSCR", "Debt Service Coverage Ratio = NOI / Annual Debt Service. Lenders typically want ≥1.20."),
        ("Debt Service Coverage", "Same as DSCR."),
        ("IO Period", "Interest-only period — months or years before amortization begins."),
        ("Prepayment", "Prepayment penalty structure (yield maintenance, defeasance, step-down)."),
        ("Construction Loan", "Short-term loan for the construction period."),
        ("Permanent Loan", "Long-term mortgage that replaces the construction loan."),
        ("Mezzanine", "Subordinate / mezzanine debt layered between senior debt and equity."),
    ],

    # ------------------------------------------------------------------
    # RETURNS / INVESTMENT ANALYSIS
    # ------------------------------------------------------------------
    "Returns": [
        ("Cash Flow", "After-debt cash flow = NOI − Debt Service."),
        ("BTCF", "Before-Tax Cash Flow = NOI − Debt Service (same as Cash Flow)."),
        ("ATCF", "After-Tax Cash Flow = BTCF − income taxes on real estate income."),
        ("Cash-on-Cash", "Cash-on-Cash Return = Annual Cash Flow / Equity Invested."),
        ("CoC", "Abbreviation for Cash-on-Cash return."),
        ("IRR", "Internal Rate of Return — annualized return considering all cash flows and time value of money."),
        ("Equity Multiple", "Total distributions / total equity invested (e.g. 2.0× = double your money)."),
        ("EM", "Abbreviation for Equity Multiple."),
        ("Hold Period", "Planned investment holding period in years before sale/refinance."),
        ("Exit Cap Rate", "Assumed cap rate at sale/disposition (usually higher than going-in cap)."),
        ("Reversion Value", "Estimated sale price at exit = Forward NOI / Exit Cap Rate."),
        ("Profit", "Total profit from the investment."),
        ("ROI", "Return on Investment."),
        ("Yield", "Annual yield or return percentage."),
    ],

    # ------------------------------------------------------------------
    # TAX INCENTIVES & PROGRAMS
    # ------------------------------------------------------------------
    "Tax Programs": [
        ("UAP", "Universal Affordability Preference — NYC zoning program that grants bonus FAR in exchange for permanently affordable housing."),
        ("485-x", "NYC property tax exemption program (successor to 421-a). Requires 20% affordable at 80% AMI to qualify."),
        ("421-a", "Former NYC property tax exemption for new residential construction (expired, replaced by 485-x)."),
        ("Tax Abatement", "Reduction in property taxes — usually from 485-x, 421-a, J-51, or ICAP."),
        ("ICAP", "Industrial and Commercial Abatement Program."),
        ("J-51", "NYC tax exemption/abatement for residential rehabilitation."),
        ("Prevailing Wage", "Projects with 100+ units under UAP must pay prevailing construction wages."),
        ("40% AMI Trigger", "If UAP bonus affordable floor area ≥ 10,000 SF, 20% of affordable units must be at 40% AMI."),
        ("Abatement Period", "Duration of the tax abatement (e.g. 25 years for 485-x)."),
        ("Phase-In", "Gradual increase in taxes during abatement burn-off."),
        ("PILOT", "Payment In Lieu Of Taxes — alternative tax structure for certain programs."),
    ],

    # ------------------------------------------------------------------
    # CONSTRUCTION / DEVELOPMENT
    # ------------------------------------------------------------------
    "Development": [
        ("GSF", "Gross Square Feet — total building area including walls, corridors."),
        ("NSF", "Net Square Feet — usable/rentable area (typically 80-85% of GSF)."),
        ("RSF", "Rentable Square Feet — same as NSF in most contexts."),
        ("Efficiency", "Net-to-gross ratio (NSF/GSF). Typically 80-85% for residential."),
        ("Stories", "Number of floors / stories in the building."),
        ("Floors", "Same as Stories."),
        ("Floor Plate", "Typical floor area per story."),
        ("Cellar", "Below-grade space — counts partially toward zoning floor area."),
        ("Mechanical", "Mechanical/utility space — may be deductible from zoning floor area."),
        ("Parking Spaces", "Number of off-street parking spaces (may be required by zoning)."),
        ("Construction Type", "Building construction type (e.g. 'Type IA', wood-frame, concrete, steel)."),
        ("Timeline", "Development timeline — predevelopment, construction, lease-up, stabilization."),
        ("Lease-Up", "Period from first occupancy to stabilized occupancy (typically 85-95%)."),
        ("Stabilization", "Point at which the property reaches target occupancy (usually 93-95%)."),
    ],

    # ------------------------------------------------------------------
    # COMMON ABBREVIATIONS IN UNDERWRITING TEMPLATES
    # ------------------------------------------------------------------
    "Abbreviations": [
        ("SF", "Square Feet."),
        ("PSF", "Per Square Foot (e.g. $50 PSF)."),
        ("P/U", "Per Unit."),
        ("PPU", "Price Per Unit."),
        ("DU", "Dwelling Unit."),
        ("DUF", "Dwelling Unit Factor (avg SF per unit, commonly 680 SF in NYC)."),
        ("GBA", "Gross Building Area."),
        ("NRA", "Net Rentable Area."),
        ("T-12", "Trailing 12 months — actual income/expense data for the past year."),
        ("T-3", "Trailing 3 months (annualized)."),
        ("YTD", "Year-To-Date."),
        ("Pro Forma", "Projected/forecasted financial performance (vs actual historical)."),
        ("Stabilized", "At full expected occupancy and market rents (usually 93-95% occupied)."),
        ("In-Place", "Current actual rents and occupancy (vs pro forma projections)."),
        ("RPIE", "Real Property Income and Expense — annual filing required by NYC DOF."),
        ("DOF", "NYC Department of Finance."),
        ("HPD", "NYC Department of Housing Preservation and Development."),
        ("HDC", "NYC Housing Development Corporation."),
    ],
}


def build_domain_context_prompt() -> str:
    """
    Build a compact text block that can be injected into the extraction
    system message, giving the LLM domain expertise about UAP underwriting
    terminology.
    """
    lines: list[str] = [
        "DOMAIN KNOWLEDGE — NYC UAP UNDERWRITING TERMINOLOGY",
        "Use this glossary to understand what each cell label means, even if",
        "the spreadsheet uses abbreviations or shorthand.\n",
    ]
    for section, entries in UNDERWRITING_GLOSSARY.items():
        lines.append(f"## {section}")
        for label, meaning in entries:
            lines.append(f"  • {label}: {meaning}")
        lines.append("")
    return "\n".join(lines)

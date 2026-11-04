"""
LeadGen Excel Exporter

Generates an Excel workbook for each search run.

Sheets:
    1. Leads
    2. Contacts
    3. Run Summary

Only leads pushed to Airtable are exported.
"""

from pathlib import Path
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import (
    Font,
    PatternFill,
    Border,
    Side,
    Alignment
)
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo


# ============================================================
# HELPERS
# ============================================================

def safe_list(value):

    if isinstance(value, list):
        return value

    if value:
        return [value]

    return []


def join_values(value):

    return ", ".join(
        str(item)
        for item in safe_list(value)
        if item is not None
    )


def get_qualification_status(result):

    qualification = result.get(
        "qualification",
        {}
    )

    qualified = qualification.get("qualified")

    if qualified is True:
        return "Qualified"

    if qualified is False:
        return "Not Qualified"

    return "Pending"


def get_contact_sources(sources):

    if not isinstance(sources, dict):
        return ""

    return "\n".join(
        f"{contact}: {source}"
        for contact, source in sources.items()
    )


def style_sheet(ws):

    header_fill = PatternFill(
        "solid",
        fgColor="202A44"
    )

    header_font = Font(
        bold=True,
        color="FFFFFF",
        size=11
    )

    thin_gray = Side(
        style="thin",
        color="D9DEE8"
    )

    for cell in ws[1]:

        cell.fill = header_fill
        cell.font = header_font

        cell.alignment = Alignment(
            horizontal="center",
            vertical="center"
        )

        cell.border = Border(
            bottom=thin_gray
        )

    ws.freeze_panes = "A2"

    # Excel Table objects provide their own AutoFilter; do not add a
    # second overlapping worksheet-level AutoFilter here.

    ws.row_dimensions[1].height = 28

    for column in ws.columns:

        max_length = 0

        column_letter = get_column_letter(
            column[0].column
        )

        for cell in column:

            cell.alignment = Alignment(
                vertical="top",
                wrap_text=True
            )

            if cell.value is not None:

                max_length = max(
                    max_length,
                    len(str(cell.value))
                )

        ws.column_dimensions[
            column_letter
        ].width = min(
            max(max_length + 3, 14),
            45
        )


def add_table(ws, name):

    if ws.max_row < 2:
        return

    table = Table(
        displayName=name,
        ref=ws.dimensions
    )

    style = TableStyleInfo(
        name="TableStyleMedium2",
        showFirstColumn=False,
        showLastColumn=False,
        showRowStripes=True,
        showColumnStripes=False
    )

    table.tableStyleInfo = style

    ws.add_table(table)


def add_hyperlink(cell):

    if cell.value and isinstance(cell.value, str):

        if cell.value.startswith(
            ("http://", "https://")
        ):

            cell.hyperlink = cell.value
            cell.style = "Hyperlink"


# ============================================================
# LEADS SHEET
# ============================================================

def build_leads_sheet(workbook, results):

    ws = workbook.active

    ws.title = "Leads"

    headers = [

        "Brand Name",
        "Website",
        "Instagram",
        "Instagram Followers",
        "Facebook Page",
        "Active Ads",
        "Longest Ad Duration (Days)",
        "ANN Priority Score",
        "ANN Probability",
        "Qualification Status",
        "Processing Status",
        "Search Keywords",
        "Missing Features",
        "Processing Errors",

    ]

    ws.append(headers)

    for item in results:

        lead = item.get(
            "lead",
            {}
        )

        result = item.get(
            "pipeline_result",
            {}
        )

        ads = lead.get("ads", []) or []

        active_ads = [
            ad for ad in ads
            if ad.get("is_active") is True
        ]

        durations = [
            ad.get("days_shown")
            for ad in ads
            if isinstance(
                ad.get("days_shown"),
                (int, float)
            )
        ]

        longest_duration = (
            max(durations)
            if durations
            else None
        )

        instagram = lead.get(
            "instagram_handle"
        )

        instagram_url = (
            f"https://www.instagram.com/{instagram}/"
            if instagram
            else None
        )

        ws.append([

            lead.get("brand_name"),

            lead.get("website"),

            instagram_url,

            lead.get("instagram_followers"),

            lead.get("facebook_url"),

            len(active_ads),

            longest_duration,

            result.get("priority_score"),

            result.get("priority_probability"),

            get_qualification_status(result),

            result.get("status"),

            join_values(
                lead.get("matched_keywords")
            ),

            join_values(
                result.get("missing_features")
            ),

            join_values(
                result.get("errors")
            ),

        ])

        row = ws.max_row

        for column in (2, 3, 5):

            add_hyperlink(
                ws.cell(
                    row=row,
                    column=column
                )
            )

    style_sheet(ws)

    add_table(
        ws,
        "LeadsTable"
    )


# ============================================================
# CONTACTS SHEET
# ============================================================

def build_contacts_sheet(workbook, results):

    ws = workbook.create_sheet(
        "Contacts"
    )

    headers = [

        "Brand Name",
        "Website",
        "Business Phones",
        "Business Emails",
        "Phone Sources",
        "Email Sources",
        "Pages Checked",
        "Pages Checked Count",
        "Enrichment Errors",

    ]

    ws.append(headers)

    for item in results:

        lead = item.get(
            "lead",
            {}
        )

        result = item.get(
            "pipeline_result",
            {}
        )

        enrichment = result.get(
            "enrichment",
            {}
        )

        contacts = enrichment.get(
            "contacts",
            {}
        )

        phones = contacts.get(
            "business_phones",
            []
        )

        emails = contacts.get(
            "business_emails",
            []
        )

        phone_sources = contacts.get(
            "phone_sources",
            {}
        )

        email_sources = contacts.get(
            "email_sources",
            {}
        )

        pages_checked = contacts.get(
            "pages_checked",
            []
        )

        errors = contacts.get(
            "errors",
            []
        )

        website = (
            contacts.get("canonical_website")
            or lead.get("website")
        )

        ws.append([

            lead.get("brand_name"),

            website,

            join_values(phones),

            join_values(emails),

            get_contact_sources(phone_sources),

            get_contact_sources(email_sources),

            join_values(pages_checked),

            contacts.get(
                "pages_checked_count",
                0
            ),

            join_values(errors),

        ])

        add_hyperlink(
            ws.cell(
                row=ws.max_row,
                column=2
            )
        )

    style_sheet(ws)

    add_table(
        ws,
        "ContactsTable"
    )


# ============================================================
# RUN SUMMARY
# ============================================================

def build_summary_sheet(
    workbook,
    results,
    search_id,
    search_keywords
):

    ws = workbook.create_sheet(
        "Run Summary"
    )

    status_counts = {}

    scores = []

    qualified_count = 0
    pending_count = 0
    not_qualified_count = 0

    phone_count = 0
    email_count = 0

    for item in results:

        result = item.get(
            "pipeline_result",
            {}
        )

        status = result.get(
            "status",
            "unknown"
        )

        status_counts[status] = (
            status_counts.get(status, 0) + 1
        )

        score = result.get(
            "priority_score"
        )

        if isinstance(score, (int, float)):

            scores.append(score)

        qualification_status = (
            get_qualification_status(result)
        )

        if qualification_status == "Qualified":

            qualified_count += 1

        elif qualification_status == "Pending":

            pending_count += 1

        else:

            not_qualified_count += 1

        contacts = (
            result.get("enrichment", {})
            .get("contacts", {})
        )

        if contacts.get("business_phones"):
            phone_count += 1

        if contacts.get("business_emails"):
            email_count += 1

    average_score = (
        sum(scores) / len(scores)
        if scores
        else None
    )

    summary = [

        ["Metric", "Value"],

        ["Search ID", search_id],

        ["Search Keywords", search_keywords],

        [
            "Run Date",
            datetime.now().astimezone().isoformat(
                timespec="seconds"
            )
        ],

        [
            "Leads Pushed to Airtable",
            len(results)
        ],

        [
            "ANN Scored Leads",
            len(scores)
        ],

        [
            "Average ANN Priority Score",
            average_score
        ],

        [
            "Leads with Phone Numbers",
            phone_count
        ],

        [
            "Leads with Emails",
            email_count
        ],

        [
            "Qualified Leads",
            qualified_count
        ],

        [
            "Pending Qualification",
            pending_count
        ],

        [
            "Not Qualified",
            not_qualified_count
        ],

    ]

    for row in summary:
        ws.append(row)

    ws.append([])

    ws.append([
        "Processing Status",
        "Count"
    ])

    for status, count in sorted(
        status_counts.items()
    ):

        ws.append([
            status,
            count
        ])

    style_sheet(ws)

    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 65


# ============================================================
# EXPORT FUNCTION
# ============================================================

def export_to_excel(
    results,
    search_id,
    search_keywords,
    output_directory
):

    output_directory = Path(
        output_directory
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True
    )

    workbook = Workbook()

    build_leads_sheet(
        workbook,
        results
    )

    build_contacts_sheet(
        workbook,
        results
    )

    build_summary_sheet(
        workbook,
        results,
        search_id,
        search_keywords
    )

    output_path = (
        output_directory
        / f"leads_{search_id}.xlsx"
    )

    workbook.save(output_path)

    print(
        f"[ok] Excel export saved: {output_path}"
    )

    return output_path
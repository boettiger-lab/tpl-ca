"""Write the STAC collection for the cleaned grants table.

Counts, dates and category values are read from the parquet, so a quarterly
refresh only needs a rerun.

Usage: python make_stac.py ca-grant-opportunities.parquet stac-collection.json
"""
import json
import sys
from datetime import date

import pyarrow.parquet as pq

BUCKET = "https://s3-west.nrp-nautilus.io/public-tpl"
PARQUET = f"{BUCKET}/ca-grant-opportunities.parquet"
LIST_TIP = " A grant can have several values; filter with `list_contains(col, '<value>')`."


def day(d):
    return f"{d.day} {d:%B %Y}"


def main(src, out):
    rows = pq.read_table(src).to_pylist()
    values = lambda col: sorted({v for r in rows for v in (r[col] or [])})
    listed = lambda d, col: {"type": "list<string>",
                             "description": d + LIST_TIP + " Values: " + ", ".join(values(col)) + ".",
                             "values": values(col)}
    text = lambda d: {"type": "string", "description": d}

    reviewed = sorted(r['last_updated_reviewed'] for r in rows if r['last_updated_reviewed'])
    deadlines = sorted(r['deadline'] for r in rows if r['deadline'])
    n_open = sum(bool(r['current_opp']) for r in rows)
    when = day(reviewed[0]) if reviewed[0] == reviewed[-1] else f"{day(reviewed[0])} to {day(reviewed[-1])}"
    today = f"{date.today().isoformat()}T00:00:00Z"

    columns = [
        ("grant_name", text("Name of the grant program. One row per program; unique.")),
        ("relevant_tpl_teams", listed("Trust for Public Land California teams for which the grant is relevant. P4P = Parks for People; Protect = land protection.", "relevant_tpl_teams")),
        ("current_opp", {"type": "boolean", "description": "True when the grant had an open solicitation as of the last review date."}),
        ("deadline", {"type": "timestamp", "description": "Application deadline of the current or most recent round, as entered in the tracker. A time of 00:00 means only a date was given. Empty for rolling or not-yet-announced deadlines; check grant_cycle_info for those."}),
        ("grant_cycle_info", text("Free-text status of the grant cycle: which round is offered, when awards are made, and links to the solicitation.")),
        ("administering_agency", {"type": "list<string>", "description": "Agency or agencies that administer the grant. Filter with `list_contains(administering_agency, '<name>')`, or match loosely with `array_to_string(administering_agency, '; ') ILIKE '%fire%'`."}),
        ("website", text("Program web page.")),
        ("eligibility", listed("Types of applicant eligible to apply.", "eligibility")),
        ("program_summary", text("Short description of the program's purpose.")),
        ("project_types", listed("Kinds of project the grant funds.", "project_types")),
        ("funding_priorities", listed("Thematic priorities of the grant.", "funding_priorities")),
        ("eligible_uses", text("Free-text description of what the funds can be used for.")),
        ("geographic_focus", text("Free-text geographic eligibility, e.g. 'California', 'Nationwide', a county or a conservancy jurisdiction.")),
        ("total_funds_available", {"type": "int64", "description": "Total funding available in US dollars, when total_funds_available_note states exactly one amount. Empty when it gives several amounts, is uncertain or gives none. The amount may cover one round, one year or the program's lifetime, so a sum across grants is not a meaningful total. When reporting this number, also quote total_funds_available_note, which keeps conditions such as the funding source and set-asides for disadvantaged communities."}),
        ("total_funds_available_note", text("Total funding available, as written by staff: amounts, fiscal years, funding sources and how the money is split (e.g. 'Allocated $48M from Prop 4 funds. 40% for vulnerable/DAC populations; 10% for SDAC.').")),
        ("grant_award_min", {"type": "int64", "description": "Smallest award in US dollars, from grant_award_note. Empty when no minimum is given. When grant_award_note lists several project types, this is the smallest amount across them."}),
        ("grant_award_max", {"type": "int64", "description": "Largest award in US dollars, from grant_award_note. Empty when no maximum is given. When grant_award_note lists several project types, this is the largest amount across them. Example: grants that can award at least $1M: `WHERE grant_award_max >= 1000000`."}),
        ("grant_award_note", text("Typical or allowed award size, as written by staff, including how it varies by project type.")),
        ("grant_period", text("Length of the grant term, as free text.")),
        ("application_process", text("How to apply: steps, solicitation documents and links.")),
        ("match_required", text("Whether matching funds are required and how much, as free text.")),
        ("notes", text("Trust for Public Land staff notes on eligibility, fit and caveats.")),
        ("contact_info", text("Program contact names, emails and phone numbers as published by the administering agency.")),
        ("tpl_history", text("Trust for Public Land's history with the grant: past applications and awards.")),
        ("relevant_plans", text("Plans a project must align with to be competitive, such as regional conservation or climate plans.")),
        ("funding_source", text("Where the program's money comes from, e.g. 'Prop 4', 'California Climate Investments', federal appropriations.")),
        ("historic_funding", text("Past funding rounds and awards, as free text with links.")),
        ("last_updated_reviewed", {"type": "date", "description": "Date Trust for Public Land staff last reviewed the row."}),
    ]

    description = f"""A list of the {len(rows)} grant programs that Trust for Public Land California is eligible for, covering land conservation, parks, restoration, wildfire and climate resilience. Each row is one grant program, with its administering agency, eligibility, project types, funding priorities, deadline, award size, match requirement, and Trust for Public Land's history with it. The list is updated quarterly; this version was last reviewed {when}, when {n_open} grants were open.

This is a table with no geometry. Most columns are free text as entered by staff. Dollar amounts are also given as numbers where the text states them clearly (total_funds_available, grant_award_min, grant_award_max), each next to a note column with the full original wording. Columns with several values per grant (teams, agencies, eligibility, project types, funding priorities) are lists.

**Example: open grants that fund acquisitions, soonest deadline first:**

```sql
SELECT grant_name, administering_agency, deadline, grant_award_min, grant_award_max, grant_award_note
FROM read_parquet('{PARQUET}')
WHERE current_opp AND list_contains(project_types, 'Acquisition')
ORDER BY deadline NULLS LAST;
```

**Source.** Trust for Public Land California team.

**Processing.** The table was exported from SharePoint and lightly cleaned before publishing; the content is otherwise as entered by staff:
- SharePoint formatting was converted to plain text, with links kept as 'text (url)'.
- Column names were lowercased with underscores (e.g. 'Grant Name' became grant_name).
- Deadlines and review dates were converted to dates, and 'Current Opp' to true/false.
- Multi-value fields (teams, agencies, eligibility, project types, funding priorities) became lists, and spelling variants of the same category were merged (e.g. 'Acquistion' became 'Acquisition').
- Dollar amounts were read from the funding text into number columns: total_funds_available when the text states exactly one amount, and grant_award_min / grant_award_max from the award range. The original wording is kept in total_funds_available_note and grant_award_note.
- Internal links to Trust for Public Land documents were removed.

**Terms.** May only be used in the Trust for Public Land California app."""

    collection = {
        "type": "Collection",
        "id": "ca-grant-opportunities",
        "stac_version": "1.0.0",
        "stac_extensions": [
            "https://stac-extensions.github.io/table/v1.2.0/schema.json",
            "https://stac-extensions.github.io/scientific/v1.0.0/schema.json",
        ],
        "title": "California Grant Opportunities for Conservation and Parks (Trust for Public Land)",
        "description": description,
        "license": "proprietary",
        "sci:citation": "Trust for Public Land California team. California Grant Opportunities. Updated quarterly.",
        "keywords": ["grants", "funding", "California", "conservation", "parks", "Trust for Public Land"],
        # no geometry; STAC requires a spatial extent, so this is the catalog's whole-world placeholder
        "extent": {
            "spatial": {"bbox": [[-180, -90, 180, 90]]},
            "temporal": {"interval": [[f"{deadlines[0]:%Y-%m-%d}T00:00:00Z", f"{deadlines[-1]:%Y-%m-%d}T00:00:00Z"]]},
        },
        "providers": [
            {"name": "The Trust for Public Land", "roles": ["producer", "licensor"], "url": "https://www.tpl.org/"},
            {"name": "National Research Platform (NRP)", "roles": ["host"], "url": "https://nationalresearchplatform.org/"},
        ],
        "created": today,
        "updated": today,
        "links": [
            {"rel": "root", "href": "https://s3-west.nrp-nautilus.io/public-data/stac/catalog.json", "type": "application/json", "title": "NRP Public Data Catalog"},
            {"rel": "parent", "href": f"{BUCKET}/stac-collection.json", "type": "application/json"},
            {"rel": "self", "href": f"{BUCKET}/ca-grant-opportunities/stac-collection.json", "type": "application/json"},
            {"rel": "license", "href": f"{BUCKET}/ca-grant-opportunities/LICENSE.md", "type": "text/markdown", "title": "Terms of use"},
        ],
        "assets": {
            "ca-grant-opportunities-parquet": {
                "href": PARQUET,
                "type": "application/x-parquet",
                "title": "California grant opportunities (one row per grant program)",
                "roles": ["data"],
                "created": today,
                "table:columns": [dict(name=n, **c) for n, c in columns],
            }
        },
    }
    json.dump(collection, open(out, "w"), indent=2)
    print(f"{len(rows)} grants, {n_open} open -> {out}")


if __name__ == '__main__':
    main(*sys.argv[1:3])

# California grant opportunities

The TPL California grants tracker, published as a table the app can query. One row per grant program TPL California is eligible for. The tracker is updated quarterly.

Published to `s3://public-tpl/`:

| file | from |
|---|---|
| `ca-grant-opportunities.parquet` | `clean.py` |
| `ca-grant-opportunities/stac-collection.json` | `make_stac.py` |
| `ca-grant-opportunities/LICENSE.md` | `LICENSE.md` in this folder |

The collection is linked as a child of `public-tpl/stac-collection.json` and loaded by the app through `layers-input.json`.

## Quarterly refresh

1. Export the tracker from SharePoint as CSV (`California Grant Opportunities.csv`). Do not commit it: it carries internal SharePoint links.
2. Build the table and its metadata:
   ```bash
   uv run --with pyarrow python clean.py "California Grant Opportunities.csv" ca-grant-opportunities.parquet
   uv run --with pyarrow python make_stac.py ca-grant-opportunities.parquet stac-collection.json
   ```
3. Upload:
   ```bash
   rclone copyto ca-grant-opportunities.parquet nrp:public-tpl/ca-grant-opportunities.parquet
   rclone copyto stac-collection.json nrp:public-tpl/ca-grant-opportunities/stac-collection.json
   ```

`make_stac.py` reads the grant count, open count, review dates and category values from the table, so the description stays current.

## What `clean.py` does

- Converts SharePoint HTML to plain text, keeping links as `text (url)`.
- Lowercases column names with underscores.
- Parses deadlines and review dates, and `Current Opp` to true/false.
- Turns the multi-value fields into lists and merges spelling variants (the `FIX` table). Add new variants there if the tracker grows some.
- Reads dollar amounts into `total_funds_available`, `grant_award_min` and `grant_award_max` (see `amounts.py`). The original wording is kept in `total_funds_available_note` and `grant_award_note`. A total is only filled when the text states exactly one amount.
- Drops `TPL Grant Summary`, whose links only work inside TPL.

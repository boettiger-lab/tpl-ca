"""Clean the SharePoint export of the grants tracker into a parquet table.

Usage: python clean.py "California Grant Opportunities.csv" ca-grant-opportunities.parquet
"""
import csv
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent))
from amounts import award_range, total_funds

# multi-value fields; SharePoint exports them as JSON arrays
LIST = ['Relevant TPL Teams', 'Administering Agency', 'Eligibility', 'Project Types', 'Funding Priorities']

# internal SharePoint links with share tokens; they only work inside TPL
DROP = {'TPL Grant Summary'}

# spelling variants of the same category in the multi-value fields
FIX = {
    'Acquistion': 'Acquisition',
    'Tribe (Federally-recognized or California listed))': 'Tribe (Federally-recognized or California listed)',
    'Local Government': 'Local Agency/Government',
    'US Fish & Wildlife Service': 'US Fish and Wildlife Service',
    'National Fish and Wildlife Foundation': 'National Fish and Wildlife Foundation (NFWF)',
}


def strip_html(s):
    if not s:
        return None
    s = s.replace('&#58;', ':')  # SharePoint escapes colons, including inside hrefs

    def link(m):
        href = html.unescape(m.group(1)).strip()
        text = html.unescape(re.sub(r'<[^>]+>', '', m.group(2))).strip()
        if not text or text.rstrip('/') == href.rstrip('/'):
            return href
        return f"{text} ({href})"

    s = re.sub(r'<a\b[^>]*?href="([^"]*)"[^>]*>(.*?)</a>', link, s, flags=re.S | re.I)
    s = re.sub(r'<br\s*/?>|</div>|</p>|</li>', '\n', s, flags=re.I)
    s = re.sub(r'<li[^>]*>', '- ', s, flags=re.I)
    s = re.sub(r'<[^>]+>', '', s)
    s = html.unescape(s).replace('\xa0', ' ').replace('​', '')
    lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in s.split('\n')]
    return '\n'.join(line for line in lines if line) or None


def as_list(s):
    if not s.strip():
        return None
    items = [FIX.get(x.strip(), x.strip()) for x in json.loads(s)]
    return list(dict.fromkeys(i for i in items if i)) or None


def as_timestamp(s):
    return datetime.strptime(s.strip(), '%m/%d/%Y %H:%M') if s.strip() else None


def as_date(s):
    return datetime.strptime(s.strip(), '%m/%d/%Y').date() if s.strip() else None


def column_name(c):
    return re.sub(r'[^a-z0-9]+', '_', c.lower()).strip('_')


def main(src, out_parquet):
    rows = list(csv.DictReader(open(src, encoding='utf-8-sig')))
    out = {}
    for c in rows[0]:
        if c in DROP:
            continue
        n = column_name(c)
        values = [r[c] for r in rows]
        if c in LIST:
            out[n] = pa.array([as_list(v) for v in values], pa.list_(pa.string()))
        elif c == 'Current Opp':
            out[n] = pa.array([v.strip() == 'Yes' for v in values], pa.bool_())
        elif c == 'Deadline':
            out[n] = pa.array([as_timestamp(v) for v in values], pa.timestamp('s'))
        elif c == 'Last Updated/Reviewed':
            out[n] = pa.array([as_date(v) for v in values], pa.date32())
        elif c == 'Total Funds Available':
            # the number where the text states one amount, next to the original wording
            out[n] = pa.array([total_funds(v) for v in values], pa.int64())
            out[n + '_note'] = pa.array([strip_html(v.strip()) for v in values], pa.string())
        elif c == 'Grant Award Range':
            award = [award_range(v) for v in values]
            out['grant_award_min'] = pa.array([a[0] for a in award], pa.int64())
            out['grant_award_max'] = pa.array([a[1] for a in award], pa.int64())
            out['grant_award_note'] = pa.array([strip_html(v.strip()) for v in values], pa.string())
        else:
            out[n] = pa.array([strip_html(v.strip()) for v in values], pa.string())
    table = pa.table(out)
    pq.write_table(table, out_parquet, compression='zstd')
    print(f"{table.num_rows} grants, {table.num_columns} columns -> {out_parquet}")


if __name__ == '__main__':
    main(*sys.argv[1:3])

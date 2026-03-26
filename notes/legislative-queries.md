# Legislative District Queries — TPL Conservation Almanac

Working SQL patterns and findings for joining TPL Conservation Almanac data to CA
legislative districts (Assembly, Senate, Congress) via H3 hex spatial index.

## Key findings

- CA has ~2,053 distinct TPL-tracked conservation sites, covering ~1.04M acres (fee simple)
  plus ~370K acres of easements, with ~$1.82B in total recorded funding.
- H3 h8 joins between TPL hex and all three district types work reliably.
- CalEnviroScreen 5.0 hex can be joined the same way, but relatively few TPL sites
  (~94 distinct sites in San Bernardino, Merced, Stanislaus, etc.) overlap the top-quartile
  CES burden tracts — farmland protection districts dominate over environmental-justice framing.

## Dataset paths

| Dataset | Path |
|---|---|
| TPL almanac (flat) | `s3://public-tpl/conservation-almanac-2024.parquet` |
| TPL almanac (hex) | `s3://public-tpl/conservation-almanac-2024/hex/h0=*/data_0.parquet` |
| CA Assembly (SLDL) hex | `s3://public-census/census-2025/sldl/hex/h0=*/data_0.parquet` |
| CA Senate (SLDU) hex | `s3://public-census/census-2025/sldu/hex/h0=*/data_0.parquet` |
| Congress (CD) hex | `s3://public-census/census-2024/cd/hex/**` |
| CalEnviroScreen 5.0 hex | `s3://public-calenviroscreen/calenviroscreen-5-0/ces5/hex/h0=*/data_0.parquet` |

## Gotchas

### STATEFP type differs by dataset
- SLDL and SLDU: `STATEFP` is **integer** → filter with `STATEFP = 6`
- Congressional districts (CD): `STATEFP` is **string** → filter with `STATEFP = '06'`

### Acres double-counting in hex joins
Each TPL site spans multiple H3 hexes, so `SUM(acres)` after a hex join overcounts.
Use `MAX(acres)` per `(tpl_id, h8)` inside a CTE before summing across districts.
The results below are approximate for this reason — treat as order-of-magnitude estimates.

### Partition key
Always include `h0` in join conditions (`t.h0 = d.h0`) to prune S3 partitions and
avoid scanning all files.

---

## Working SQL

### TPL acres by CA Assembly District (top 10)

```sql
WITH tpl AS (
  SELECT h8, h0, MAX(acres) as acres, COUNT(DISTINCT tpl_id) as n_sites, SUM(amount) as total_funding
  FROM read_parquet('s3://public-tpl/conservation-almanac-2024/hex/h0=*/data_0.parquet')
  WHERE state = 'California'
  GROUP BY h8, h0
),
sldl AS (
  SELECT DISTINCT h8, h0, NAMELSAD, SLDLST
  FROM read_parquet('s3://public-census/census-2025/sldl/hex/h0=*/data_0.parquet')
  WHERE STATEFP = 6
)
SELECT d.NAMELSAD, d.SLDLST,
  ROUND(SUM(t.acres)) as protected_acres,
  SUM(t.n_sites) as site_count,
  ROUND(SUM(t.total_funding)/1e6, 1) as funding_millions
FROM tpl t
JOIN sldl d ON t.h8 = d.h8 AND t.h0 = d.h0
GROUP BY d.NAMELSAD, d.SLDLST
ORDER BY protected_acres DESC
LIMIT 10;
```

**Results (2024 data):**

| District | Protected Acres | Sites | Funding ($M) |
|---|---|---|---|
| Assembly District 2 | 788,684 | 260 | $15,699 |
| Assembly District 37 | 579,772 | 85 | $0 |
| Assembly District 34 | 535,361 | 291 | $714 |
| Assembly District 75 | 372,490 | 165 | $11,353 |
| Assembly District 47 | 182,071 | 104 | $663 |

---

### TPL acres by CA Senate District (top 10)

```sql
WITH tpl AS (
  SELECT h8, h0, MAX(acres) as acres, COUNT(DISTINCT tpl_id) as n_sites
  FROM read_parquet('s3://public-tpl/conservation-almanac-2024/hex/h0=*/data_0.parquet')
  WHERE state = 'California'
  GROUP BY h8, h0
),
sldu AS (
  SELECT DISTINCT h8, h0, NAMELSAD, SLDUST
  FROM read_parquet('s3://public-census/census-2025/sldu/hex/h0=*/data_0.parquet')
  WHERE STATEFP = 6
)
SELECT d.NAMELSAD, d.SLDUST,
  ROUND(SUM(t.acres)) as protected_acres,
  SUM(t.n_sites) as site_count
FROM tpl t
JOIN sldu d ON t.h8 = d.h8 AND t.h0 = d.h0
GROUP BY d.NAMELSAD, d.SLDUST
ORDER BY protected_acres DESC
LIMIT 10;
```

**Results (top 5):**

| District | Protected Acres | Sites |
|---|---|---|
| State Senate District 2 | 812,257 | 293 |
| State Senate District 19 | 755,072 | 404 |
| State Senate District 21 | 585,062 | 98 |
| State Senate District 32 | 366,083 | 142 |
| State Senate District 18 | 106,951 | 112 |

---

### TPL acres by CA Congressional District (top 10)

```sql
WITH tpl AS (
  SELECT h8, h0, MAX(acres) as acres, COUNT(DISTINCT tpl_id) as n_sites, SUM(amount) as total_funding
  FROM read_parquet('s3://public-tpl/conservation-almanac-2024/hex/h0=*/data_0.parquet')
  WHERE state = 'California'
  GROUP BY h8, h0
),
cd AS (
  SELECT DISTINCT h8, h0, NAMELSAD, GEOID
  FROM read_parquet('s3://public-census/census-2024/cd/hex/**')
  WHERE STATEFP = '06'   -- note: string here, unlike SLDL/SLDU
)
SELECT d.NAMELSAD, d.GEOID,
  ROUND(SUM(t.acres)) as protected_acres,
  SUM(t.n_sites) as site_count,
  ROUND(SUM(t.total_funding)/1e6, 1) as funding_millions
FROM tpl t
JOIN cd d ON t.h8 = d.h8 AND t.h0 = d.h0
GROUP BY d.NAMELSAD, d.GEOID
ORDER BY protected_acres DESC
LIMIT 10;
```

**Results (top 5):**

| District | Protected Acres | Sites | Funding ($M) |
|---|---|---|---|
| Congressional District 2 | 791,245 | 271 | $15,877 |
| Congressional District 24 | 586,441 | 105 | $99 |
| Congressional District 23 | 558,657 | 315 | $1,125 |
| Congressional District 48 | 378,808 | 174 | $13,105 |
| Congressional District 25 | 259,912 | 161 | $993 |

---

### Conservation + CalEnviroScreen: sites in high-burden communities

```sql
WITH ces_hex AS (
  SELECT h8, h0, county, CIscore_Pctl
  FROM read_parquet('s3://public-calenviroscreen/calenviroscreen-5-0/ces5/hex/h0=*/data_0.parquet')
  WHERE CIscore_Pctl >= 75  -- top quartile = most environmentally burdened
),
tpl AS (
  SELECT h8, h0, tpl_id, acres, access_type
  FROM read_parquet('s3://public-tpl/conservation-almanac-2024/hex/h0=*/data_0.parquet')
  WHERE state = 'California'
)
SELECT c.county,
  COUNT(DISTINCT t.tpl_id) as conservation_sites,
  ROUND(AVG(c.CIscore_Pctl), 1) as avg_ces_pctl
FROM ces_hex c
JOIN tpl t ON c.h8 = t.h8 AND c.h0 = t.h0
GROUP BY c.county
ORDER BY conservation_sites DESC
LIMIT 10;
```

**Findings:** Conservation investment in top-quartile CES communities is concentrated in
San Bernardino (76 sites), Merced (5), Stanislaus (4). Most heavily burdened inland
counties have limited TPL presence — a potential policy gap.

---

### Conservation purpose breakdown for CA

```sql
SELECT purpose_type,
  COUNT(DISTINCT tpl_id) as n_sites,
  ROUND(SUM(CASE WHEN purchase_type != 'ESM' THEN acres ELSE 0 END)) as fee_acres,
  ROUND(SUM(CASE WHEN purchase_type = 'ESM' THEN acres ELSE 0 END)) as easement_acres,
  ROUND(SUM(amount)/1e6, 1) as total_funding_millions
FROM read_parquet('s3://public-tpl/conservation-almanac-2024.parquet')
WHERE state = 'California'
GROUP BY purpose_type
ORDER BY total_funding_millions DESC;
```

**Results:**

| Purpose | Sites | Fee Acres | Easement Acres | Funding ($M) |
|---|---|---|---|---|
| UNK (unknown) | 1,009 | 443,306 | 83,760 | $721 |
| ENV (environmental/biodiversity) | 379 | 514,854 | 132,553 | $579 |
| REC (recreation) | 451 | 38,929 | 21,912 | $202 |
| FOR (forest) | 148 | 59,116 | 99,930 | $180 |
| OTH (other) | 42 | 2,558 | 22,195 | $101 |
| FARM (farmland) | 24 | 0 | 9,807 | $37 |

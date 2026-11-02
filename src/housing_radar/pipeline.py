"""Immutable release snapshots preserve source revisions and historical anomalies.

`published_at` records the user's announced release date. `captured_at` records
when these particular bytes were collected; archived URLs may serve later updates.
"""

from __future__ import annotations

import calendar
import csv
import hashlib
import json
import logging
import math
import shutil
import sqlite3
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

from openpyxl import load_workbook

LOGGER = logging.getLogger(__name__)
SCHEMA_VERSION = 1
MAX_SOURCE_BYTES = 12 * 1024 * 1024
MAX_EXPANDED_BYTES = 80 * 1024 * 1024
MAX_ZIP_ENTRIES = 200
MAX_OBSERVATION_MONTHS = 2000
REGIONS = (
    ("NSW", "New South Wales"), ("VIC", "Victoria"), ("QLD", "Queensland"),
    ("SA", "South Australia"), ("WA", "Western Australia"), ("TAS", "Tasmania"),
    ("NT", "Northern Territory"), ("ACT", "Australian Capital Territory"), ("AUS", "Australia"),
)
DWELLING_TYPES = ("Houses", "Dwellings excluding houses", "Total (Type of Building)")
SERIES_IDS = (
    ("A418511A", "A418596X", "A418675W", "A418757A", "A418839F", "A418920R", "A419010W", "A419079V", "A418427K"),
    ("A421353R", "A421445X", "A421536F", "A421628R", "A421720F", "A421807W", "A421889L", "A421971X", "A421262J"),
    ("A422166A", "A422266K", "A422366V", "A422466C", "A422566L", "A422666W", "A422766F", "A422863J", "A422064L"),
)
SERIES = {series_id: {"series_id": series_id, "region": region, "region_name": name, "dwelling_type": kind,
                     "description": f"Total number of dwelling units ; {kind} ; {name} ;"}
          for kind, ids in zip(DWELLING_TYPES, SERIES_IDS) for series_id, (region, name) in zip(ids, REGIONS)}

SCHEMA = """
CREATE TABLE pipeline_runs (
    run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
    operation TEXT NOT NULL CHECK(operation IN ('ingest','report')),
    release_period TEXT, edition INTEGER, status TEXT NOT NULL CHECK(status IN ('running','success','failed')),
    snapshot_id INTEGER, replayed INTEGER, error TEXT
);
CREATE TABLE source_artifacts (
    run_id TEXT PRIMARY KEY REFERENCES pipeline_runs(run_id), sha256 TEXT NOT NULL,
    source_url TEXT NOT NULL, raw_path TEXT NOT NULL, byte_size INTEGER NOT NULL, captured_at TEXT NOT NULL
);
CREATE TABLE snapshots (
    snapshot_id INTEGER PRIMARY KEY, release_period TEXT NOT NULL, edition INTEGER NOT NULL CHECK(edition>0),
    published_at TEXT NOT NULL, source_sha256 TEXT NOT NULL, source_url TEXT NOT NULL, captured_at TEXT NOT NULL,
    row_count INTEGER NOT NULL, first_month TEXT NOT NULL, last_month TEXT NOT NULL,
    run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id), UNIQUE(release_period,edition)
);
CREATE TABLE series (
    series_id TEXT PRIMARY KEY, region TEXT NOT NULL, region_name TEXT NOT NULL,
    dwelling_type TEXT NOT NULL, description TEXT NOT NULL, UNIQUE(region,dwelling_type)
);
CREATE TABLE observations (
    snapshot_id INTEGER NOT NULL REFERENCES snapshots(snapshot_id), series_id TEXT NOT NULL REFERENCES series(series_id),
    month TEXT NOT NULL, value INTEGER NOT NULL CHECK(typeof(value)='integer' AND value>=0),
    PRIMARY KEY(snapshot_id,series_id,month)
);
CREATE INDEX idx_observations_month ON observations(snapshot_id,month,series_id);
CREATE TABLE quality_findings (
    finding_id INTEGER PRIMARY KEY, snapshot_id INTEGER NOT NULL REFERENCES snapshots(snapshot_id),
    rule TEXT NOT NULL, month TEXT NOT NULL, region TEXT NOT NULL, dwelling_type TEXT NOT NULL,
    expected INTEGER NOT NULL, actual INTEGER NOT NULL, delta INTEGER NOT NULL
);
CREATE INDEX idx_findings_snapshot ON quality_findings(snapshot_id,month);
CREATE VIEW current_observations AS
SELECT o.snapshot_id,o.series_id,o.month,o.value,s.region,s.region_name,s.dwelling_type,
       v.release_period,v.edition,v.published_at,v.captured_at
FROM observations o JOIN series s USING(series_id) JOIN snapshots v USING(snapshot_id)
WHERE o.snapshot_id=(SELECT snapshot_id FROM snapshots ORDER BY release_period DESC,edition DESC LIMIT 1);
CREATE VIEW monthly_metrics AS
WITH windows AS (
    SELECT c.*,
      COUNT(*) OVER(PARTITION BY series_id ORDER BY month ROWS BETWEEN 11 PRECEDING AND CURRENT ROW) AS window_count,
      MIN(month) OVER(PARTITION BY series_id ORDER BY month ROWS BETWEEN 11 PRECEDING AND CURRENT ROW) AS window_start,
      SUM(value) OVER(PARTITION BY series_id ORDER BY month ROWS BETWEEN 11 PRECEDING AND CURRENT ROW) AS window_total
    FROM current_observations c
)
SELECT w.snapshot_id,w.series_id,w.month,w.region,w.region_name,w.dwelling_type,w.value,
       p.value AS prior_year_value,
       CASE WHEN p.value>0 THEN 100.0*(w.value-p.value)/p.value END AS yoy_pct,
       CASE WHEN w.window_count=12 AND w.window_start=DATE(w.month,'-11 months') THEN w.window_total END AS trailing_12_month_total,
       w.release_period,w.edition
FROM windows w LEFT JOIN current_observations p
  ON p.series_id=w.series_id AND p.month=DATE(w.month,'-12 months');
CREATE VIEW release_changes AS
WITH preceding AS (
    SELECT snapshot_id,release_period,edition,
           LAG(snapshot_id) OVER(ORDER BY release_period,edition) AS previous_snapshot_id
    FROM snapshots
)
SELECT n.snapshot_id,n.release_period,n.edition,n.previous_snapshot_id,
       o.series_id,o.month,s.region,s.dwelling_type,o.value,p.value AS previous_value,
       CASE WHEN p.value IS NOT NULL THEN o.value-p.value END AS change_value,
       CASE WHEN n.previous_snapshot_id IS NULL THEN 'baseline'
            WHEN p.value IS NULL THEN 'new_observation'
            WHEN o.value<>p.value THEN 'changed' ELSE 'unchanged' END AS change_type
FROM preceding n JOIN observations o ON o.snapshot_id=n.snapshot_id JOIN series s USING(series_id)
LEFT JOIN observations p ON p.snapshot_id=n.previous_snapshot_id AND p.series_id=o.series_id AND p.month=o.month
UNION ALL
SELECT n.snapshot_id,n.release_period,n.edition,n.previous_snapshot_id,
       p.series_id,p.month,s.region,s.dwelling_type,NULL AS value,p.value AS previous_value,
       NULL AS change_value,'removed_observation' AS change_type
FROM preceding n JOIN observations p ON p.snapshot_id=n.previous_snapshot_id JOIN series s USING(series_id)
LEFT JOIN observations o ON o.snapshot_id=n.snapshot_id AND o.series_id=p.series_id AND o.month=p.month
WHERE o.series_id IS NULL;
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _next_month(value: date) -> date:
    return date(value.year+(value.month==12),value.month%12+1,1)


def _period(value: str) -> date:
    try:
        result = date.fromisoformat(value+"-01")
    except (TypeError,ValueError) as exc:
        raise ValueError("release_period must be YYYY-MM") from exc
    if result.strftime("%Y-%m") != value:
        raise ValueError("release_period must be YYYY-MM")
    return result


def _release_metadata(release_period: str, published_at: str, edition: int) -> dict:
    release = _period(release_period)
    try:
        publication = date.fromisoformat(published_at)
    except (TypeError,ValueError) as exc:
        raise ValueError("published_at must be the announced release date YYYY-MM-DD") from exc
    if publication.isoformat() != published_at or publication < release.replace(day=calendar.monthrange(release.year,release.month)[1]):
        raise ValueError("published_at must be an ISO date on or after the release month's end")
    if type(edition) is not int or edition<1:
        raise ValueError("edition must be a positive integer")
    return {"release_period":release_period,"published_at":published_at,"edition":edition}


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path,timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=30000")
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version not in (0,SCHEMA_VERSION):
        connection.close()
        raise RuntimeError(f"Unsupported warehouse schema version {version}")
    if version == 0:
        connection.executescript("BEGIN;\n"+SCHEMA+f"\nPRAGMA user_version={SCHEMA_VERSION};\nCOMMIT;")
    return connection


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):
            digest.update(chunk)
    return digest.hexdigest()


def _excel_month(value: object, label: str) -> date:
    if not isinstance(value,(date,datetime)):
        raise ValueError(f"{label} must be an Excel date on the first day of the month")
    if isinstance(value,datetime):
        if value.time()!=datetime.min.time() or value.tzinfo is not None:
            raise ValueError(f"{label} must be a date without time or timezone")
        value = value.date()
    if value.day!=1:
        raise ValueError(f"{label} must be the first day of the month")
    return value


def _integer(value: object, label: str) -> int:
    # A conservative integer bound also keeps twelve-month SQLite sums in range.
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or int(value)!=value or not 0<=value<=2**31-1:
        raise ValueError(f"{label} must be a finite nonnegative integer within the source count domain")
    return int(value)


def _parse_workbook(path: Path, release_period: str) -> dict:
    if path.stat().st_size>MAX_SOURCE_BYTES:
        raise ValueError("Workbook exceeds the compressed size limit")
    try:
        with zipfile.ZipFile(path) as archive:
            items=archive.infolist()
            if len(items)>MAX_ZIP_ENTRIES or sum(item.file_size for item in items)>MAX_EXPANDED_BYTES:
                raise ValueError("Workbook exceeds ZIP entry/inflation limits")
            if any(item.flag_bits&1 for item in items):
                raise ValueError("Encrypted workbooks are not supported")
    except zipfile.BadZipFile as exc:
        raise ValueError("Source is not a valid XLSX ZIP workbook") from exc
    workbook=load_workbook(path,read_only=True,data_only=False,keep_links=False)
    try:
        if "Data1" not in workbook.sheetnames:
            raise ValueError("ABS Table 09 Data1 sheet is missing")
        sheet=workbook["Data1"]
        if sheet.max_column!=28 or not 11<=sheet.max_row<=MAX_OBSERVATION_MONTHS+10:
            raise ValueError("Data1 must contain exactly 27 series and a bounded monthly history")
        rows=sheet.iter_rows(values_only=True)
        header=[next(rows) for _ in range(10)]
        expected_labels=("Unit","Series Type","Data Type","Frequency","Collection Month","Series Start","Series End","No. Obs","Series ID")
        if tuple(row[0] for row in header[1:])!=expected_labels:
            raise ValueError("ABS metadata row labels changed")
        ids=list(header[9][1:])
        if len(set(ids))!=27 or set(ids)!=set(SERIES):
            raise ValueError("ABS series IDs changed, duplicated, or missing")
        release=_period(release_period)
        starts=[]
        declared_counts=[]
        for column,series_id in enumerate(ids,start=1):
            definition=SERIES[series_id]
            description=header[0][column]
            tokens=[part.strip() for part in description.split(";") if part.strip()] if isinstance(description,str) else []
            if tokens!=["Total number of dwelling units",definition["dwelling_type"],definition["region_name"]]:
                raise ValueError(f"Series ID/description mapping changed for {series_id}")
            if tuple(header[row][column] for row in (1,2,3,4))!=("Number","Original","FLOW","Month"):
                raise ValueError(f"Unexpected units/type/frequency for {series_id}")
            if type(header[5][column]) is not int or header[5][column]!=1:
                raise ValueError(f"Unexpected Collection Month for {series_id}")
            starts.append(_excel_month(header[6][column],f"{series_id} Series Start"))
            if _excel_month(header[7][column],f"{series_id} Series End")!=release:
                raise ValueError(f"Series End does not equal release_period for {series_id}")
            declared_counts.append(_integer(header[8][column],f"{series_id} No. Obs"))
        if len(set(starts))!=1 or len(set(declared_counts))!=1:
            raise ValueError("Series must share the same start and observation count")
        observations=[]
        findings=[]
        expected_month=starts[0]
        months=[]
        for row_number,row in enumerate(rows,start=11):
            month=_excel_month(row[0],f"Row {row_number} date")
            if month!=expected_month:
                raise ValueError(f"Months must be unique and contiguous; expected {expected_month}, got {month}")
            if month>release:
                raise ValueError("Observation month exceeds release_period")
            values={series_id:_integer(row[column],f"{series_id}/{month}") for column,series_id in enumerate(ids,start=1)}
            observations.extend((series_id,month.isoformat(),value) for series_id,value in values.items())
            for index,(region,_) in enumerate(REGIONS):
                expected=values[SERIES_IDS[0][index]]+values[SERIES_IDS[1][index]]
                actual=values[SERIES_IDS[2][index]]
                if expected!=actual:
                    findings.append(("houses_plus_other_equals_total",month.isoformat(),region,DWELLING_TYPES[2],expected,actual,actual-expected))
            for kind,kind_ids in zip(DWELLING_TYPES,SERIES_IDS):
                expected=sum(values[item] for item in kind_ids[:8])
                actual=values[kind_ids[8]]
                if expected!=actual:
                    findings.append(("states_sum_to_australia",month.isoformat(),"AUS",kind,expected,actual,actual-expected))
            months.append(month)
            expected_month=_next_month(month)
        if not months or months[-1]!=release or len(months)!=declared_counts[0]:
            raise ValueError("Monthly history does not match Series Start/End/No. Obs and release_period")
        return {"observations":observations,"quality_findings":findings,"first_month":months[0].isoformat(),
                "last_month":months[-1].isoformat(),"row_count":len(observations),"month_count":len(months)}
    finally:
        workbook.close()


def _store_snapshot(connection: sqlite3.Connection, parsed: dict, metadata: dict, run_id: str) -> int:
    """All inserts here execute inside the caller's transaction."""
    for definition in SERIES.values():
        connection.execute("INSERT OR IGNORE INTO series VALUES(:series_id,:region,:region_name,:dwelling_type,:description)",definition)
    cursor=connection.execute("""INSERT INTO snapshots(release_period,edition,published_at,source_sha256,source_url,captured_at,row_count,first_month,last_month,run_id)
                                VALUES(?,?,?,?,?,?,?,?,?,?)""",[metadata["release_period"],metadata["edition"],metadata["published_at"],metadata["sha256"],
                                    metadata["source_url"],metadata["captured_at"],parsed["row_count"],parsed["first_month"],parsed["last_month"],run_id])
    snapshot_id=cursor.lastrowid
    connection.executemany("INSERT INTO observations VALUES(?,?,?,?)",((snapshot_id,*row) for row in parsed["observations"]))
    connection.executemany("INSERT INTO quality_findings(snapshot_id,rule,month,region,dwelling_type,expected,actual,delta) VALUES(?,?,?,?,?,?,?,?)",
                           ((snapshot_id,*finding) for finding in parsed["quality_findings"]))
    return snapshot_id


def _report_data(connection: sqlite3.Connection, run_id: str, replayed: bool=False) -> dict:
    latest=connection.execute("SELECT * FROM snapshots ORDER BY release_period DESC,edition DESC LIMIT 1").fetchone()
    if latest is None:
        raise ValueError("Warehouse has no validated snapshot to report")
    latest_id=latest["snapshot_id"]
    metrics=[dict(row) for row in connection.execute("SELECT * FROM monthly_metrics WHERE month=? ORDER BY region,dwelling_type",(latest["last_month"],))]
    findings=connection.execute("SELECT COUNT(*) FROM quality_findings WHERE snapshot_id=?",(latest_id,)).fetchone()[0]
    recent_findings=connection.execute("SELECT COUNT(*) FROM quality_findings WHERE snapshot_id=? AND month>=DATE(?,'-11 months')",(latest_id,latest["last_month"])).fetchone()[0]
    return {"run_id":run_id,"status":"success","replayed":replayed,"snapshot_id":latest_id,
            "current_release_period":latest["release_period"],"current_edition":latest["edition"],
            "announced_release_date":latest["published_at"],"captured_at":latest["captured_at"],
            "source_sha256":latest["source_sha256"],"current_rows":latest["row_count"],"series_count":27,
            "first_month":latest["first_month"],"last_month":latest["last_month"],"latest_month_metrics":metrics,
            "quality_findings_count":findings,"quality_findings_latest_12_months":recent_findings,
            "revision_summary":{row[0]:row[1] for row in connection.execute("SELECT change_type,COUNT(*) FROM release_changes WHERE snapshot_id=? GROUP BY change_type ORDER BY change_type",(latest_id,))},
            "snapshots":[dict(row) for row in connection.execute("SELECT snapshot_id,release_period,edition,published_at,captured_at,row_count,source_sha256 FROM snapshots ORDER BY release_period,edition")],
            "caveats":["Original monthly approvals are unadjusted counts, not completed homes or seasonally adjusted activity.",
                       "Announced release date is not an as-known-at timestamp; captured archived bytes may include subsequent updates.",
                       "Arithmetic reconciliation findings preserve publisher values and require source interpretation; no values are repaired.",
                       "Year-on-year percentages are NULL when prior-year data is absent or its value is zero."]}


def _export(connection: sqlite3.Connection, directory: Path, report: dict) -> None:
    generation=directory/report["run_id"]
    generation.mkdir(parents=True,exist_ok=True)
    queries={
        "monthly_metrics.csv":("SELECT * FROM monthly_metrics ORDER BY month,series_id",()),
        "release_changes.csv":("SELECT * FROM release_changes WHERE snapshot_id=? ORDER BY month,series_id",(report["snapshot_id"],)),
        "quality_findings.csv":("SELECT rule,month,region,dwelling_type,expected,actual,delta FROM quality_findings WHERE snapshot_id=? ORDER BY month,rule,region,dwelling_type",(report["snapshot_id"],)),
    }
    for filename,(query,parameters) in queries.items():
        cursor=connection.execute(query,parameters)
        with (generation/filename).open("w",encoding="utf-8",newline="") as stream:
            writer=csv.writer(stream)
            writer.writerow([column[0] for column in cursor.description])
            writer.writerows(cursor)
    (generation/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    pointer={"run_id":report["run_id"],"directory":report["run_id"],"report":f"{report['run_id']}/report.json"}
    temporary=directory/f".latest-{report['run_id']}.tmp"
    temporary.write_text(json.dumps(pointer,indent=2)+"\n",encoding="utf-8")
    temporary.replace(directory/"latest.json")


def run_pipeline(data_dir: str|Path, *, file_path: str|Path, release_period: str, published_at: str,
                 edition: int=1, source_url: str|None=None) -> dict:
    """Validate and preserve a complete release. Same edition never overwrites bytes."""
    root=Path(data_dir).resolve()
    root.mkdir(parents=True,exist_ok=True)
    connection=_connect(root/"warehouse.sqlite")
    run_id=uuid.uuid4().hex
    committed=False
    try:
        connection.execute("INSERT INTO pipeline_runs(run_id,started_at,operation,release_period,edition,status) VALUES(?,?,'ingest',?,?,'running')",
                           (run_id,_now(),str(release_period),edition if type(edition) is int else None))
        connection.commit()
        metadata=_release_metadata(release_period,published_at,edition)
        source=Path(file_path).resolve()
        if source.stat().st_size>MAX_SOURCE_BYTES:
            raise ValueError("Workbook exceeds the compressed size limit")
        raw_directory=root/"raw"/run_id
        raw_directory.mkdir(parents=True)
        raw=raw_directory/"8731009.xlsx"
        shutil.copyfile(source,raw)
        metadata.update(sha256=_sha256(raw),source_url=source_url or source.as_uri(),captured_at=_now())
        manifest={**metadata,"run_id":run_id,"raw_path":str(raw),"byte_size":raw.stat().st_size}
        (raw_directory/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        connection.execute("INSERT INTO source_artifacts VALUES(?,?,?,?,?,?)",(run_id,metadata["sha256"],metadata["source_url"],str(raw),raw.stat().st_size,metadata["captured_at"]))
        connection.commit()
        LOGGER.info("Validating ABS release %s edition %s",release_period,edition)
        parsed=_parse_workbook(raw,release_period)
        connection.execute("BEGIN IMMEDIATE")
        try:
            previous=connection.execute("SELECT * FROM snapshots WHERE release_period=? AND edition=?",(release_period,edition)).fetchone()
            replayed=previous is not None
            if previous:
                if previous["source_sha256"]!=metadata["sha256"]:
                    raise ValueError("Immutable release edition already exists with different bytes; use an explicit new edition")
                if previous["published_at"]!=published_at:
                    raise ValueError("Announced release date conflicts with the immutable snapshot metadata")
                snapshot_id=previous["snapshot_id"]
            else:
                snapshot_id=_store_snapshot(connection,parsed,metadata,run_id)
            connection.execute("UPDATE pipeline_runs SET snapshot_id=?,replayed=? WHERE run_id=?",(snapshot_id,int(replayed),run_id))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        committed=True
        connection.execute("BEGIN")
        report=_report_data(connection,run_id,replayed)
        _export(connection,root/"exports",report)
        connection.commit()
        connection.execute("UPDATE pipeline_runs SET status='success',finished_at=? WHERE run_id=?",(_now(),run_id))
        connection.commit()
        LOGGER.info("Stored %s observations; report has %s reconciliation findings",parsed["row_count"],report["quality_findings_count"])
        return report
    except Exception as exc:
        connection.rollback()
        message=("Snapshot committed; report failed: " if committed else "")+str(exc)
        connection.execute("UPDATE pipeline_runs SET status='failed',finished_at=?,error=? WHERE run_id=?",(_now(),message[:2000],run_id))
        connection.commit()
        raise
    finally:
        connection.close()


def export_report(data_dir: str|Path) -> dict:
    """Regenerate exports with a separate audited report operation."""
    root=Path(data_dir).resolve()
    if not (root/"warehouse.sqlite").exists():
        raise ValueError("Warehouse does not exist; ingest a validated release first")
    connection=_connect(root/"warehouse.sqlite")
    run_id=uuid.uuid4().hex
    try:
        connection.execute("INSERT INTO pipeline_runs(run_id,started_at,operation,status) VALUES(?,?,'report','running')",(run_id,_now()))
        connection.commit()
        connection.execute("BEGIN")
        report=_report_data(connection,run_id)
        _export(connection,root/"exports",report)
        connection.commit()
        connection.execute("UPDATE pipeline_runs SET status='success',finished_at=?,snapshot_id=? WHERE run_id=?",(_now(),report["snapshot_id"],run_id))
        connection.commit()
        return report
    except Exception as exc:
        connection.rollback()
        connection.execute("UPDATE pipeline_runs SET status='failed',finished_at=?,error=? WHERE run_id=?",(_now(),str(exc)[:2000],run_id))
        connection.commit()
        raise
    finally:
        connection.close()


def fetch_release(data_dir: str|Path, *, release_period: str, published_at: str, edition: int=1) -> dict:
    """Bounded download from an explicit ABS archive URL; never substitute latest."""
    _release_metadata(release_period,published_at,edition)
    release=_period(release_period)
    slug=f"{calendar.month_abbr[release.month].lower()}-{release.year}"
    url=f"https://www.abs.gov.au/statistics/industry/building-and-construction/building-approvals-australia/{slug}/8731009.xlsx"
    directory=Path(data_dir).resolve()/"downloads"
    directory.mkdir(parents=True,exist_ok=True)
    destination=directory/f"8731009-{release_period}-{uuid.uuid4().hex[:8]}.xlsx"
    request=urllib.request.Request(url,headers={"User-Agent":"HousingRadar/1.0 public-data-etl"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request,timeout=45) as response,destination.open("wb") as output:
                expected=response.headers.get("Content-Length")
                received=0
                while chunk:=response.read(1024*1024):
                    received+=len(chunk)
                    if received>MAX_SOURCE_BYTES:
                        raise ValueError("Source exceeds bounded download size")
                    output.write(chunk)
                if expected is not None and received!=int(expected):
                    raise RuntimeError("Incomplete source download: Content-Length mismatch")
            break
        except urllib.error.HTTPError as exc:
            if attempt==2 or (exc.code!=429 and exc.code<500):
                raise RuntimeError(f"ABS archive HTTP {exc.code}: {url}") from exc
            time.sleep(2**attempt)
        except (urllib.error.URLError,TimeoutError) as exc:
            if attempt==2:
                raise RuntimeError(f"ABS archive unavailable: {url}: {exc}") from exc
            time.sleep(2**attempt)
    return run_pipeline(data_dir,file_path=destination,release_period=release_period,published_at=published_at,edition=edition,source_url=url)

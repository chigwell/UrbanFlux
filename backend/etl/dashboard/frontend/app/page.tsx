"use client";

import Link from "next/link";
import dynamic from "next/dynamic";
import {
  Database,
  Download,
  FileText,
  RefreshCcw,
  Search,
  Square,
  TriangleAlert,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { Pagination } from "@/components/Pagination";
import {
  BoroughBoundary,
  BoroughBoundaryResponse,
  BoroughData,
  DownloadJob,
  PageResult,
  Source,
  Stats,
  apiGet,
  apiPost,
  formatDate,
} from "@/lib/api";
import proj4 from "proj4";

const PAGE_SIZE = 25;

const BoroughLeafletMap = dynamic(() => import("@/components/BoroughLeafletMap"), {
  ssr: false,
});

if (!proj4.defs("EPSG:27700")) {
  proj4.defs(
    "EPSG:27700",
    "+proj=tmerc +lat_0=49 +lon_0=-2 +k=0.9996012717 +x_0=400000 +y_0=-100000 +ellps=airy +datum=OSGB36 +units=m +no_defs",
  );
}

type BoroughPolygon = {
  boroughName: string;
  rings: [number, number][][];
  color: string;
};

function toLatLng(point: [number, number]): [number, number] | null {
  const [x, y] = point;
  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    return null;
  }

  const maybeLonLat = x >= -180 && x <= 180 && y >= -90 && y <= 90;
  if (maybeLonLat) {
    return [y, x];
  }

  try {
    const converted = proj4("EPSG:27700", "EPSG:4326", [x, y]);
    if (!Array.isArray(converted) || converted.length < 2) {
      return null;
    }
    const [longitude, latitude] = converted;
    if (!Number.isFinite(longitude) || !Number.isFinite(latitude)) return null;
    return [latitude, longitude];
  } catch {
    return null;
  }
}

export default function DashboardPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [sources, setSources] = useState<PageResult<Source> | null>(null);
  const [boroughBoundaries, setBoroughBoundaries] = useState<BoroughBoundary[] | null>(null);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [startingDownloads, setStartingDownloads] = useState(false);
  const [stoppingDownloads, setStoppingDownloads] = useState(false);
  const [downloadJob, setDownloadJob] = useState<DownloadJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [boundaryError, setBoundaryError] = useState<string | null>(null);
  const [selectedBoroughName, setSelectedBoroughName] = useState<string | null>(null);
  const [boroughData, setBoroughData] = useState<BoroughData | null>(null);
  const [boroughDataLoading, setBoroughDataLoading] = useState(false);
  const [boroughDataError, setBoroughDataError] = useState<string | null>(null);
  const notDownloadedCount = (stats?.pending_count || 0) + (stats?.error_count || 0);

  const load = useCallback(async (nextPage = page, nextSearch = appliedSearch) => {
    setLoading(true);
    setError(null);
    try {
      const query = new URLSearchParams({
        page: String(nextPage),
        page_size: String(PAGE_SIZE),
      });
      if (nextSearch) query.set("search", nextSearch);
      const [statsData, sourcesData, jobData] = await Promise.all([
        apiGet<Stats>("/api/stats"),
        apiGet<PageResult<Source>>(`/api/sources?${query.toString()}`),
        apiGet<DownloadJob>("/api/download-jobs/active"),
      ]);
      setStats(statsData);
      setSources(sourcesData);
      setDownloadJob(jobData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
    } finally {
      setLoading(false);
    }
  }, [appliedSearch, page]);

  const loadBoundaries = useCallback(async () => {
    try {
      setBoundaryError(null);
      const boundaryData = await apiGet<BoroughBoundaryResponse>("/api/borough-boundaries");
      setBoroughBoundaries(boundaryData.items);
    } catch (boundaryErr) {
      setBoroughBoundaries([]);
      setBoundaryError(
        boundaryErr instanceof Error ? boundaryErr.message : "Failed to load borough boundaries",
      );
    }
  }, []);

  useEffect(() => {
    void load(page, appliedSearch);
  }, [page, appliedSearch, load]);

  useEffect(() => {
    void loadBoundaries();
  }, [loadBoundaries]);

  useEffect(() => {
    if (!downloadJob?.is_running) return undefined;

    const intervalId = window.setInterval(async () => {
      try {
        const [jobData, statsData] = await Promise.all([
          apiGet<DownloadJob>("/api/download-jobs/active"),
          apiGet<Stats>("/api/stats"),
        ]);
        setDownloadJob(jobData);
        setStats(statsData);
        if (!jobData.is_running) {
          await load(page, appliedSearch);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to refresh download progress");
      }
    }, 1500);

    return () => window.clearInterval(intervalId);
  }, [appliedSearch, downloadJob?.is_running, load, page]);

  async function runSync() {
    setSyncing(true);
    setError(null);
    try {
      await apiPost("/api/sync", { mode: "api", download_files: false });
      setPage(1);
      await load(1, appliedSearch);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  }

  async function downloadPendingCsvs() {
    setStartingDownloads(true);
    setError(null);
    try {
      const job = await apiPost<DownloadJob>("/api/download-jobs/pending", {
        retry_errors: true,
      });
      setDownloadJob(job);
      const statsData = await apiGet<Stats>("/api/stats");
      setStats(statsData);
      if (!job.is_running) {
        await load(page, appliedSearch);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start CSV downloads");
    } finally {
      setStartingDownloads(false);
    }
  }

  async function stopDownloads() {
    setStoppingDownloads(true);
    setError(null);
    try {
      const job = await apiPost<DownloadJob>("/api/download-jobs/active/stop");
      setDownloadJob(job);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to stop CSV downloads");
    } finally {
      setStoppingDownloads(false);
    }
  }

  function applySearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPage(1);
    setAppliedSearch(search.trim());
  }

  const selectBorough = useCallback(async (boroughName: string) => {
    setSelectedBoroughName(boroughName);
    setBoroughDataLoading(true);
    setBoroughDataError(null);
    try {
      const query = new URLSearchParams({
        borough_name: boroughName,
        rows_per_file: "10",
        max_files: "30",
      });
      const data = await apiGet<BoroughData>(`/api/borough-data?${query.toString()}`);
      setBoroughData(data);
    } catch (err) {
      setBoroughData(null);
      setBoroughDataError(err instanceof Error ? err.message : "Failed to load borough data");
    } finally {
      setBoroughDataLoading(false);
    }
  }, []);

  return (
    <main className="app-shell">
      <header className="topbar">
        <Link className="brand" href="/">
          <span className="brand-mark">
            <Database size={20} />
          </span>
          <span>London Datastore CSV Dashboard</span>
        </Link>
        <div className="actions">
          <Link className="button" href="/transformations">
            Transformations
          </Link>
          <button
            className="button"
            type="button"
            onClick={runSync}
            disabled={syncing || downloadJob?.is_running}
          >
            <RefreshCcw size={17} />
            {syncing ? "Syncing" : "Sync catalogue"}
          </button>
          <button
            className="button primary"
            type="button"
            onClick={downloadPendingCsvs}
            disabled={
              syncing ||
              startingDownloads ||
              downloadJob?.is_running ||
              notDownloadedCount === 0
            }
          >
            <Download size={17} />
            {downloadJob?.is_running
              ? "Downloading"
              : startingDownloads
                ? "Starting"
                : "Download unsaved CSVs"}
          </button>
          {downloadJob?.is_running ? (
            <button
              className="button danger"
              type="button"
              onClick={stopDownloads}
              disabled={stoppingDownloads}
            >
              <Square size={16} />
              {stoppingDownloads ? "Stopping" : "Stop"}
            </button>
          ) : null}
        </div>
      </header>

      <div className="container">
        <div className="section-heading">
          <div>
            <h1>CSV Dataset Sources</h1>
            <p>
              {stats?.last_sync
                ? `Last sync: ${stats.last_sync.status} on ${formatDate(stats.last_sync.finished_at || stats.last_sync.started_at)}`
                : "No sync run recorded yet."}
            </p>
          </div>
        </div>

        {error ? <div className="alert error">{error}</div> : null}

        <section className="stats-grid" aria-label="Catalogue summary">
          <Stat label="Sources" value={stats?.sources_count} icon={<Database size={16} />} />
          <Stat label="CSV files" value={stats?.csv_files_count} icon={<FileText size={16} />} />
          <Stat label="Pending" value={stats?.pending_count} icon={<RefreshCcw size={16} />} />
          <Stat label="Downloaded" value={stats?.success_count} icon={<FileText size={16} />} />
          <Stat label="Errors" value={stats?.error_count} icon={<TriangleAlert size={16} />} />
        </section>

        <DownloadProgress job={downloadJob} />

        <div className="toolbar">
          <form className="search" onSubmit={applySearch}>
            <Search size={17} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search title, publisher, or source code"
            />
          </form>
          <span className="muted">
            {sources ? `${sources.total.toLocaleString()} sources` : loading ? "Loading" : ""}
          </span>
        </div>

        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Dataset</th>
                <th>Publisher</th>
                <th>CSV files</th>
                <th>Updated</th>
                <th>Local status</th>
              </tr>
            </thead>
            <tbody>
              {sources?.items.map((source) => (
                <tr key={source.id}>
                  <td>
                    <Link className="title-link" href={`/sources/${source.id}`}>
                      {source.title}
                    </Link>
                    <div className="muted">{source.source_code || source.uuid}</div>
                  </td>
                  <td>{source.organisation_name || "-"}</td>
                  <td>{source.csv_count}</td>
                  <td>{formatDate(source.updated_at_source)}</td>
                  <td>
                    {source.success_count} saved, {source.pending_count} pending,{" "}
                    {source.error_count} errors
                  </td>
                </tr>
              ))}
              {!loading && sources?.items.length === 0 ? (
                <tr>
                  <td colSpan={5}>No sources found.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        {sources ? (
          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={sources.total}
            onPageChange={setPage}
          />
        ) : null}

        <BoroughBoundaryMap
          boundaries={boroughBoundaries}
          error={boundaryError}
          selectedBoroughName={selectedBoroughName}
          boroughData={boroughData}
          dataLoading={boroughDataLoading}
          dataError={boroughDataError}
          onSelectBorough={selectBorough}
        />
      </div>
    </main>
  );
}

function DownloadProgress({ job }: { job: DownloadJob | null }) {
  if (!job || job.status === "idle") return null;

  const progress = Math.min(100, Math.max(0, job.progress_percent));
  const statusLabel =
    job.status === "running"
      ? "Downloading CSV files"
      : job.status === "success"
        ? "Download complete"
        : job.status === "completed_with_errors"
          ? "Completed with errors"
          : job.status === "canceled"
            ? "Stopped"
            : "Download job failed";

  return (
    <section className="progress-panel" aria-label="CSV download progress">
      <div className="progress-header">
        <div>
          <strong>{statusLabel}</strong>
          <span className="muted">
            {job.completed.toLocaleString()} of {job.total.toLocaleString()} files processed
          </span>
        </div>
        <span className="progress-percent">{progress.toFixed(progress % 1 === 0 ? 0 : 1)}%</span>
      </div>
      <div className="progress-track" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
        <div className="progress-fill" style={{ width: `${progress}%` }} />
      </div>
      <div className="progress-meta">
        <span>{job.success_count.toLocaleString()} saved</span>
        <span>{job.error_count.toLocaleString()} errors</span>
        {job.current_file_title ? <span>Now: {job.current_file_title}</span> : null}
        {job.message ? <span>{job.message}</span> : null}
      </div>
    </section>
  );
}

function Stat({
  label,
  value,
  icon,
}: {
  label: string;
  value: number | undefined;
  icon: React.ReactNode;
}) {
  return (
    <div className="stat-card">
      <div className="stat-label">
        {icon}
        {label}
      </div>
      <div className="stat-value">{value === undefined ? "-" : value.toLocaleString()}</div>
    </div>
  );
}

function BoroughBoundaryMap({
  boundaries,
  error,
  selectedBoroughName,
  boroughData,
  dataLoading,
  dataError,
  onSelectBorough,
}: {
  boundaries: BoroughBoundary[] | null;
  error: string | null;
  selectedBoroughName: string | null;
  boroughData: BoroughData | null;
  dataLoading: boolean;
  dataError: string | null;
  onSelectBorough: (boroughName: string) => void;
}) {
  if (error) {
    return (
      <section className="section-heading">
        <div>
          <h2>London borough borders</h2>
          <div className="alert error">{error}</div>
        </div>
      </section>
    );
  }

  if (boundaries === null) {
    return (
      <section className="section-heading">
        <div>
          <h2>London borough borders</h2>
          <p>Loading boundaries…</p>
        </div>
      </section>
    );
  }

  if (boundaries.length === 0) {
    return (
      <section className="section-heading">
        <div>
          <h2>London borough borders</h2>
          <p className="muted">No borough boundary records were found in the database.</p>
        </div>
      </section>
    );
  }

  const polygons: BoroughPolygon[] = [];
  const allLatLng: [number, number][] = [];
  const palette = [
    "#065f46",
    "#0369a1",
    "#b45309",
    "#7c3aed",
    "#be123c",
    "#0f766e",
    "#475569",
    "#0d9488",
    "#ca8a04",
    "#9333ea",
  ];

  boundaries.forEach((boundary, boundaryIndex) => {
    const normalizedRings = Array.isArray(boundary.border_coordinates)
      ? boundary.border_coordinates
          .filter((ring) => Array.isArray(ring) && ring.length >= 4)
          .map((ring) => {
            const latLngRing = ring
              .map((point) => toLatLng([point[0], point[1]]))
              .filter((point): point is [number, number] => point !== null);
            if (latLngRing.length >= 4) {
              return latLngRing;
            }
            return null;
          })
          .filter((ring): ring is [number, number][] => ring !== null)
      : [];
    if (normalizedRings.length > 0) {
      polygons.push({
        boroughName: boundary.borough_name,
        rings: normalizedRings,
        color: palette[boundaryIndex % palette.length],
      });
      allLatLng.push(...normalizedRings.flat());
    }
  });

  if (polygons.length === 0) {
    return (
      <section className="section-heading">
        <div>
          <h2>London borough borders</h2>
          <p className="muted">No valid boundary coordinate data was found.</p>
        </div>
      </section>
    );
  }

  let minLatitude = Number.POSITIVE_INFINITY;
  let maxLatitude = Number.NEGATIVE_INFINITY;
  let minLongitude = Number.POSITIVE_INFINITY;
  let maxLongitude = Number.NEGATIVE_INFINITY;

  allLatLng.forEach(([latitude, longitude]) => {
    minLatitude = Math.min(minLatitude, latitude);
    maxLatitude = Math.max(maxLatitude, latitude);
    minLongitude = Math.min(minLongitude, longitude);
    maxLongitude = Math.max(maxLongitude, longitude);
  });

  const bounds: [[number, number], [number, number]] = [
    [minLatitude, minLongitude],
    [maxLatitude, maxLongitude],
  ];

  return (
    <section className="borough-boundaries">
      <div className="section-heading">
        <div>
          <h2>London borough borders</h2>
          <p>{`Loaded ${polygons.length} borough boundaries`}</p>
        </div>
      </div>

      <div className="borough-map-shell">
        <BoroughLeafletMap
          polygons={polygons}
          bounds={bounds}
          selectedBoroughName={selectedBoroughName}
          onBoroughClick={onSelectBorough}
        />
      </div>

      <BoroughDataPanel
        selectedBoroughName={selectedBoroughName}
        data={boroughData}
        loading={dataLoading}
        error={dataError}
      />

      <p className="muted">
        London borough borders are rendered from the OpenStreetMap base layer with boundaries from the
        official London shapefile.
      </p>
    </section>
  );
}

function BoroughDataPanel({
  selectedBoroughName,
  data,
  loading,
  error,
}: {
  selectedBoroughName: string | null;
  data: BoroughData | null;
  loading: boolean;
  error: string | null;
}) {
  if (!selectedBoroughName) {
    return (
      <div className="borough-data-panel empty">
        Click a borough on the map to show transformed CSV rows identified for that borough.
      </div>
    );
  }

  if (loading) {
    return <div className="borough-data-panel empty">Loading data for {selectedBoroughName}…</div>;
  }

  if (error) {
    return <div className="borough-data-panel error">{error}</div>;
  }

  if (!data || data.total_rows === 0) {
    return (
      <div className="borough-data-panel empty">
        No transformed CSV rows are currently identified for {selectedBoroughName}.
      </div>
    );
  }

  return (
    <div className="borough-data-panel">
      <div className="borough-data-header">
        <div>
          <h3>{data.borough_name}</h3>
          <p className="muted">
            {data.total_rows.toLocaleString()} rows across {data.total_files.toLocaleString()} CSV
            files and {data.total_datasets.toLocaleString()} datasets. Showing up to{" "}
            {data.rows_per_file} rows per file.
          </p>
        </div>
        <Link className="button small" href="/transformations">
          Open transformations
        </Link>
      </div>

      <div className="borough-data-list">
        {data.datasets.map((dataset) => (
          <section className="borough-dataset-card" key={dataset.source_id}>
            <h4>{dataset.source_title || `Dataset ${dataset.source_id}`}</h4>
            {dataset.files.map((file) => (
              <div className="borough-file-card" key={file.csv_file_id}>
                <div className="borough-file-heading">
                  <strong>{file.csv_title || file.csv_file_name || `CSV ${file.csv_file_id}`}</strong>
                  <span className="muted">
                    {file.total_rows.toLocaleString()} matching rows
                    {file.total_rows > file.rows.length
                      ? `, showing ${file.rows.length.toLocaleString()}`
                      : ""}
                  </span>
                </div>
                <div className="borough-row-list">
                  {file.rows.map((row) => (
                    <div className="borough-row-card" key={`${row.csv_file_id}-${row.row_number}`}>
                      <div className="borough-row-meta">
                        <span>Row {row.row_number}</span>
                        <span>
                          {row.date_start || "No start date"} to {row.date_end || "No end date"}
                        </span>
                        <span className={`status-pill status-${row.status}`}>{row.status}</span>
                      </div>
                      <dl>
                        {Object.entries(row.source_row_json).map(([key, value]) => (
                          <div key={key}>
                            <dt>{key}</dt>
                            <dd>{String(value ?? "")}</dd>
                          </div>
                        ))}
                      </dl>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </section>
        ))}
      </div>
    </div>
  );
}

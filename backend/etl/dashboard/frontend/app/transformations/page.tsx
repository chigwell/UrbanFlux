"use client";

import Link from "next/link";
import {
  Database,
  FileText,
  Play,
  RefreshCcw,
  Search,
  Square,
  TriangleAlert,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { Pagination } from "@/components/Pagination";
import {
  API_BASE_URL,
  BoroughResponse,
  CsvRowTransformation,
  PageResult,
  TransformationJob,
  TransformationPlan,
  TransformationStats,
  apiGet,
  apiPost,
  formatDate,
} from "@/lib/api";

const PAGE_SIZE = 25;
const ROW_PAGE_SIZE = 50;

type PlanStatusFilter = "all" | "success" | "error" | "running";
type RowStatusFilter = "all" | "success" | "partial" | "error";
type DetailStatusFilter = "all" | string;

export default function TransformationsPage() {
  const [stats, setStats] = useState<TransformationStats | null>(null);
  const [job, setJob] = useState<TransformationJob | null>(null);
  const [plans, setPlans] = useState<PageResult<TransformationPlan> | null>(null);
  const [rows, setRows] = useState<PageResult<CsvRowTransformation> | null>(null);
  const [boroughs, setBoroughs] = useState<BoroughResponse | null>(null);
  const [page, setPage] = useState(1);
  const [rowPage, setRowPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<PlanStatusFilter>("all");
  const [maxConfidenceFilter, setMaxConfidenceFilter] = useState("");
  const [warningsOnly, setWarningsOnly] = useState(false);
  const [changedCsvOnly, setChangedCsvOnly] = useState(false);
  const [oldSchemaOnly, setOldSchemaOnly] = useState(false);
  const [rowStatusFilter, setRowStatusFilter] = useState<RowStatusFilter>("all");
  const [dateStatusFilter, setDateStatusFilter] = useState<DetailStatusFilter>("all");
  const [boroughStatusFilter, setBoroughStatusFilter] = useState<DetailStatusFilter>("all");
  const [boroughNameFilter, setBoroughNameFilter] = useState("");
  const [dateFromFilter, setDateFromFilter] = useState("");
  const [dateToFilter, setDateToFilter] = useState("");
  const [rowCsvFileId, setRowCsvFileId] = useState("");
  const [limit, setLimit] = useState("");
  const [sampleRows, setSampleRows] = useState(8);
  const [maxAttempts, setMaxAttempts] = useState(3);
  const [retryPlanErrors, setRetryPlanErrors] = useState(false);
  const [retryOutdatedSuccesses, setRetryOutdatedSuccesses] = useState(false);
  const [retryRowOutputs, setRetryRowOutputs] = useState(false);
  const [applyExistingSuccesses, setApplyExistingSuccesses] = useState(true);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [activeCsvAction, setActiveCsvAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (
    nextPage = page,
    nextStatus = statusFilter,
    nextRowPage = rowPage,
    nextRowStatus = rowStatusFilter,
    nextDateStatus = dateStatusFilter,
    nextBoroughStatus = boroughStatusFilter,
    nextBoroughName = boroughNameFilter,
    nextDateFrom = dateFromFilter,
    nextDateTo = dateToFilter,
    nextRowCsvFileId = rowCsvFileId,
  ) => {
    setLoading(true);
    setError(null);
    try {
      const query = new URLSearchParams({
        page: String(nextPage),
        page_size: String(PAGE_SIZE),
      });
      if (nextStatus !== "all") query.set("status", nextStatus);
      if (maxConfidenceFilter.trim()) query.set("max_confidence", maxConfidenceFilter.trim());
      if (warningsOnly) query.set("has_warnings", "true");
      if (changedCsvOnly) query.set("csv_changed", "true");
      if (oldSchemaOnly) query.set("old_schema", "true");
      const rowQuery = new URLSearchParams({
        page: String(nextRowPage),
        page_size: String(ROW_PAGE_SIZE),
      });
      if (nextRowStatus !== "all") rowQuery.set("status", nextRowStatus);
      if (nextDateStatus !== "all") rowQuery.set("date_status", nextDateStatus);
      if (nextBoroughStatus !== "all") rowQuery.set("borough_status", nextBoroughStatus);
      if (nextBoroughName.trim()) rowQuery.set("borough_name", nextBoroughName.trim());
      if (nextDateFrom.trim()) rowQuery.set("date_from", nextDateFrom.trim());
      if (nextDateTo.trim()) rowQuery.set("date_to", nextDateTo.trim());
      if (nextRowCsvFileId.trim()) rowQuery.set("csv_file_id", nextRowCsvFileId.trim());

      const [statsData, jobData, plansData, rowsData, boroughData] = await Promise.all([
        apiGet<TransformationStats>("/api/transformation-stats"),
        apiGet<TransformationJob>("/api/transformation-jobs/active"),
        apiGet<PageResult<TransformationPlan>>(`/api/transformation-plans?${query.toString()}`),
        apiGet<PageResult<CsvRowTransformation>>(`/api/row-transformations?${rowQuery.toString()}`),
        boroughs ? Promise.resolve(boroughs) : apiGet<BoroughResponse>("/api/boroughs"),
      ]);
      setStats(statsData);
      setJob(jobData);
      setPlans(plansData);
      setRows(rowsData);
      setBoroughs(boroughData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load transformations");
    } finally {
      setLoading(false);
    }
  }, [boroughNameFilter, boroughs, boroughStatusFilter, changedCsvOnly, dateFromFilter, dateStatusFilter, dateToFilter, maxConfidenceFilter, oldSchemaOnly, page, rowCsvFileId, rowPage, rowStatusFilter, statusFilter, warningsOnly]);

  useEffect(() => {
    void load(page, statusFilter, rowPage, rowStatusFilter, dateStatusFilter, boroughStatusFilter, boroughNameFilter, dateFromFilter, dateToFilter, rowCsvFileId);
  }, [boroughNameFilter, boroughStatusFilter, changedCsvOnly, dateFromFilter, dateStatusFilter, dateToFilter, load, maxConfidenceFilter, oldSchemaOnly, page, rowCsvFileId, rowPage, rowStatusFilter, statusFilter, warningsOnly]);

  useEffect(() => {
    if (!job?.is_running) return undefined;

    const intervalId = window.setInterval(async () => {
      try {
        const [statsData, jobData] = await Promise.all([
          apiGet<TransformationStats>("/api/transformation-stats"),
          apiGet<TransformationJob>("/api/transformation-jobs/active"),
        ]);
        setStats(statsData);
        setJob(jobData);
        if (!jobData.is_running) {
          await load(page, statusFilter, rowPage, rowStatusFilter, dateStatusFilter, boroughStatusFilter, boroughNameFilter, dateFromFilter, dateToFilter, rowCsvFileId);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to refresh transformation status");
      }
    }, 1500);

    return () => window.clearInterval(intervalId);
  }, [boroughNameFilter, boroughStatusFilter, dateFromFilter, dateStatusFilter, dateToFilter, job?.is_running, load, page, rowCsvFileId, rowPage, rowStatusFilter, statusFilter]);

  async function startTransformations() {
    setStarting(true);
    setError(null);
    try {
      const parsedLimit = limit.trim() ? Number(limit) : null;
      const nextJob = await apiPost<TransformationJob>("/api/transformation-jobs/pending", {
        limit: parsedLimit && parsedLimit > 0 ? parsedLimit : null,
        retry_plan_errors: retryPlanErrors,
        retry_outdated_successes: retryOutdatedSuccesses,
        retry_row_outputs: retryRowOutputs,
        sample_rows: sampleRows,
        max_attempts: maxAttempts,
        apply_existing_successes: applyExistingSuccesses,
      });
      setJob(nextJob);
      const statsData = await apiGet<TransformationStats>("/api/transformation-stats");
      setStats(statsData);
      if (!nextJob.is_running) {
        await load(page, statusFilter, rowPage, rowStatusFilter, dateStatusFilter, boroughStatusFilter, boroughNameFilter, dateFromFilter, dateToFilter, rowCsvFileId);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start transformations");
    } finally {
      setStarting(false);
    }
  }

  async function stopTransformations() {
    setStopping(true);
    setError(null);
    try {
      const nextJob = await apiPost<TransformationJob>("/api/transformation-jobs/active/stop");
      setJob(nextJob);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to stop transformations");
    } finally {
      setStopping(false);
    }
  }

  async function replanCsv(csvFileId: number) {
    setActiveCsvAction(`replan-${csvFileId}`);
    setError(null);
    try {
      await apiPost(`/api/csv-files/${csvFileId}/transformation-plan/replan`, {
        sample_rows: sampleRows,
        max_attempts: maxAttempts,
      });
      await load(page, statusFilter, rowPage, rowStatusFilter, dateStatusFilter, boroughStatusFilter, boroughNameFilter, dateFromFilter, dateToFilter, rowCsvFileId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to replan CSV transformation");
    } finally {
      setActiveCsvAction(null);
    }
  }

  async function reapplyCsvRows(csvFileId: number) {
    setActiveCsvAction(`apply-${csvFileId}`);
    setError(null);
    try {
      await apiPost(`/api/csv-files/${csvFileId}/row-transformations/apply`);
      await load(page, statusFilter, rowPage, rowStatusFilter, dateStatusFilter, boroughStatusFilter, boroughNameFilter, dateFromFilter, dateToFilter, rowCsvFileId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to apply CSV row transformations");
    } finally {
      setActiveCsvAction(null);
    }
  }

  function applyStatus(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPage(1);
    void load(1, statusFilter, rowPage, rowStatusFilter, dateStatusFilter, boroughStatusFilter, boroughNameFilter, dateFromFilter, dateToFilter, rowCsvFileId);
  }

  function applyRowFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRowPage(1);
    void load(page, statusFilter, 1, rowStatusFilter, dateStatusFilter, boroughStatusFilter, boroughNameFilter, dateFromFilter, dateToFilter, rowCsvFileId);
  }

  function rowExportUrl() {
    const query = new URLSearchParams({ limit: "50000" });
    if (rowStatusFilter !== "all") query.set("status", rowStatusFilter);
    if (dateStatusFilter !== "all") query.set("date_status", dateStatusFilter);
    if (boroughStatusFilter !== "all") query.set("borough_status", boroughStatusFilter);
    if (boroughNameFilter.trim()) query.set("borough_name", boroughNameFilter.trim());
    if (dateFromFilter.trim()) query.set("date_from", dateFromFilter.trim());
    if (dateToFilter.trim()) query.set("date_to", dateToFilter.trim());
    if (rowCsvFileId.trim()) query.set("csv_file_id", rowCsvFileId.trim());
    return `${API_BASE_URL}/api/row-transformations/export.csv?${query.toString()}`;
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <Link className="brand" href="/">
          <span className="brand-mark">
            <Database size={20} />
          </span>
          <span>London CSV Transformations</span>
        </Link>
        <div className="actions">
          <Link className="button" href="/">
            Dashboard
          </Link>
          <button
            className="button"
            type="button"
            onClick={() => load(page, statusFilter, rowPage, rowStatusFilter, dateStatusFilter, boroughStatusFilter, boroughNameFilter, dateFromFilter, dateToFilter, rowCsvFileId)}
          >
            <RefreshCcw size={17} />
            Refresh
          </button>
        </div>
      </header>

      <div className="container">
        <section className="section-heading">
          <div>
            <h1>Transformation control</h1>
            <p>
              Plan borough/date extraction from downloaded CSVs, apply saved rules to rows, and
              inspect failures without using the terminal.
            </p>
          </div>
          <div className="actions">
            <button
              className="button primary"
              type="button"
              onClick={startTransformations}
              disabled={starting || job?.is_running}
            >
              <Play size={17} />
              {job?.is_running ? "Running" : "Start"}
            </button>
            <button
              className="button danger"
              type="button"
              onClick={stopTransformations}
              disabled={!job?.is_running || stopping}
            >
              <Square size={17} />
              {stopping ? "Stopping" : "Stop"}
            </button>
          </div>
        </section>

        {error ? (
          <div className="alert error">
            <TriangleAlert size={18} />
            {error}
          </div>
        ) : null}

        <section className="stats-grid transformation-stats-grid">
          <StatCard label="Downloaded CSVs" value={stats?.downloaded_csv_files} />
          <StatCard label="Plans created" value={stats?.planned_csv_files} />
          <StatCard label="Files with rows" value={stats?.row_transformed_csv_files} />
          <StatCard label="Mapped rows" value={stats?.row_status?.success} />
          <StatCard label="Row errors" value={stats?.row_status?.error} />
          <StatCard label="Pending plans" value={stats?.pending_plans} />
          <StatCard label="Old schema plans" value={stats?.outdated_successful_plans} />
          <StatCard label="Pending row apply" value={stats?.pending_row_applications} />
        </section>

        <section className="control-panel">
          <div className="job-card">
            <div className="job-card-header">
              <div>
                <h2>Current job</h2>
                <p className="muted">{job?.message || "No transformation job has started."}</p>
              </div>
              <StatusPill status={job?.status || "idle"} />
            </div>
            <div className="progress-track">
              <div
                className="progress-fill"
                style={{ width: `${job?.progress_percent || 0}%` }}
              />
            </div>
            <div className="job-meta-grid">
              <span>Progress: {job?.completed || 0} / {job?.total || 0}</span>
              <span>Step: {job?.current_step || "-"}</span>
              <span>Current file: {job?.current_file_id || "-"}</span>
              <span>Started: {formatDate(job?.started_at)}</span>
              <span>Planned: {job?.planned_count || 0}</span>
              <span>Applied: {job?.applied_count || 0}</span>
              <span>Success: {job?.success_count || 0}</span>
              <span>Errors: {job?.error_count || 0}</span>
            </div>
            {job?.current_file_title ? (
              <p className="current-file">
                <FileText size={16} />
                {job.current_file_title}
              </p>
            ) : null}
          </div>

          <form className="options-card" onSubmit={(event) => event.preventDefault()}>
            <h2>Run options</h2>
            <label className="field">
              <span>Limit files</span>
              <input
                min="1"
                className="small-input"
                type="number"
                value={limit}
                onChange={(event) => setLimit(event.target.value)}
                placeholder="All pending"
              />
            </label>
            <label className="field">
              <span>Sample rows for LLM planning</span>
              <input
                min="1"
                max="50"
                className="small-input"
                type="number"
                value={sampleRows}
                onChange={(event) => setSampleRows(Number(event.target.value))}
              />
            </label>
            <label className="field">
              <span>LLM attempts per file</span>
              <input
                min="1"
                max="10"
                className="small-input"
                type="number"
                value={maxAttempts}
                onChange={(event) => setMaxAttempts(Number(event.target.value))}
              />
            </label>
            <label className="checkbox-field">
              <input
                type="checkbox"
                checked={retryPlanErrors}
                onChange={(event) => setRetryPlanErrors(event.target.checked)}
              />
              Retry files with failed plans
            </label>
            <label className="checkbox-field">
              <input
                type="checkbox"
                checked={retryOutdatedSuccesses}
                onChange={(event) => setRetryOutdatedSuccesses(event.target.checked)}
              />
              Retry successful plans with old rule schema
              {stats?.current_rule_schema_version ? ` (current v${stats.current_rule_schema_version})` : ""}
            </label>
            <label className="checkbox-field">
              <input
                type="checkbox"
                checked={retryRowOutputs}
                onChange={(event) => setRetryRowOutputs(event.target.checked)}
              />
              Rebuild existing row outputs
            </label>
            <label className="checkbox-field">
              <input
                type="checkbox"
                checked={applyExistingSuccesses}
                onChange={(event) => setApplyExistingSuccesses(event.target.checked)}
              />
              Apply rows for existing successful plans
            </label>
          </form>
        </section>

        <section className="table-section">
          <div className="section-heading compact">
            <div>
              <h2>Transformation plans</h2>
              <p>Paginated detail for every downloaded CSV that has been planned or failed.</p>
            </div>
            <form className="actions" onSubmit={applyStatus}>
              <label className="select-field">
                <Search size={16} />
                <select
                  value={statusFilter}
                  onChange={(event) => {
                    setPage(1);
                    setStatusFilter(event.target.value as StatusFilter);
                  }}
                >
                  <option value="all">All statuses</option>
                  <option value="success">Success</option>
                  <option value="error">Errors</option>
                  <option value="running">Running</option>
                </select>
              </label>
              <input
                className="small-input compact-input"
                min="0"
                max="1"
                step="0.01"
                type="number"
                value={maxConfidenceFilter}
                onChange={(event) => {
                  setPage(1);
                  setMaxConfidenceFilter(event.target.value);
                }}
                placeholder="Max confidence"
                title="Show plans where date or borough confidence is at or below this value"
              />
              <label className="checkbox-field inline-checkbox">
                <input
                  type="checkbox"
                  checked={warningsOnly}
                  onChange={(event) => {
                    setPage(1);
                    setWarningsOnly(event.target.checked);
                  }}
                />
                Warnings only
              </label>
              <label className="checkbox-field inline-checkbox">
                <input
                  type="checkbox"
                  checked={changedCsvOnly}
                  onChange={(event) => {
                    setPage(1);
                    setChangedCsvOnly(event.target.checked);
                  }}
                />
                CSV changed
              </label>
              <label className="checkbox-field inline-checkbox">
                <input
                  type="checkbox"
                  checked={oldSchemaOnly}
                  onChange={(event) => {
                    setPage(1);
                    setOldSchemaOnly(event.target.checked);
                  }}
                />
                Old schema
              </label>
            </form>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>CSV</th>
                  <th>Dataset</th>
                  <th>Status</th>
                  <th>Date rule</th>
                  <th>Borough rule</th>
                  <th>Rows</th>
                  <th>Attempts</th>
                  <th>Updated</th>
                  <th>Summary / error</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {plans?.items.map((plan) => (
                  <tr key={plan.id}>
                    <td>
                      <strong>#{plan.csv_file_id}</strong>
                      <div className="muted truncate">{plan.csv_title || "-"}</div>
                      {plan.csv_content_changed ? <div className="warning-text">CSV changed, replan needed</div> : null}
                      {stats && plan.rule_schema_version < stats.current_rule_schema_version ? (
                        <div className="warning-text">Old rule schema, replan needed</div>
                      ) : null}
                    </td>
                    <td className="truncate">{plan.source_title || "-"}</td>
                    <td><StatusPill status={plan.status} /></td>
                    <td>
                      <RuleSummary status={plan.date_range_status} rule={plan.date_range_rule_json} />
                    </td>
                    <td>
                      <RuleSummary status={plan.borough_status} rule={plan.borough_rule_json} />
                    </td>
                    <td>
                      <RowCountSummary plan={plan} />
                    </td>
                    <td>{plan.attempts}</td>
                    <td>{formatDate(plan.updated_at_local || plan.updated_at)}</td>
                    <td className={plan.status === "error" ? "error-text" : ""}>
                      {plan.error_message || plan.transformation_summary || "-"}
                      {plan.warning_count ? (
                        <div className="warning-text">
                          {plan.warning_count} warning{plan.warning_count === 1 ? "" : "s"}
                          {warningPreview(plan) ? `: ${warningPreview(plan)}` : ""}
                        </div>
                      ) : null}
                    </td>
                    <td>
                      <div className="row-actions">
                        <button
                          className="button small"
                          type="button"
                          onClick={() => replanCsv(plan.csv_file_id)}
                          disabled={Boolean(activeCsvAction) || job?.is_running}
                        >
                          {activeCsvAction === `replan-${plan.csv_file_id}` ? "Replanning" : "Replan"}
                        </button>
                        <button
                          className="button small"
                          type="button"
                          onClick={() => reapplyCsvRows(plan.csv_file_id)}
                          disabled={
                            Boolean(activeCsvAction) ||
                            job?.is_running ||
                            plan.status !== "success" ||
                            Boolean(plan.csv_content_changed) ||
                            Boolean(stats && plan.rule_schema_version < stats.current_rule_schema_version)
                          }
                        >
                          {activeCsvAction === `apply-${plan.csv_file_id}` ? "Applying" : "Apply rows"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {!loading && plans?.items.length === 0 ? (
                  <tr>
                    <td colSpan={10} className="empty-cell">
                      No transformation plans found for this filter.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <Pagination
            page={page}
            pageSize={PAGE_SIZE}
            total={plans?.total}
            onPageChange={setPage}
          />
        </section>

        <section className="table-section">
          <div className="section-heading compact">
            <div>
              <h2>Applied row mappings</h2>
              <p>Paginated row-level output: date range, borough match, source row and errors.</p>
            </div>
            <form className="actions" onSubmit={applyRowFilters}>
              <label className="select-field">
                <Search size={16} />
                <select
                  value={rowStatusFilter}
                  onChange={(event) => {
                    setRowPage(1);
                    setRowStatusFilter(event.target.value as RowStatusFilter);
                  }}
                >
                  <option value="all">All rows</option>
                  <option value="success">Mapped</option>
                  <option value="partial">Partial</option>
                  <option value="error">Errors</option>
                </select>
              </label>
              <label className="select-field">
                <Search size={16} />
                <select
                  value={dateStatusFilter}
                  onChange={(event) => {
                    setRowPage(1);
                    setDateStatusFilter(event.target.value);
                  }}
                >
                  <option value="all">All date statuses</option>
                  <option value="success">Date mapped</option>
                  <option value="not_identifiable">Date not identifiable</option>
                  <option value="unsupported">Date unsupported</option>
                  <option value="error">Date errors</option>
                </select>
              </label>
              <label className="select-field">
                <Search size={16} />
                <select
                  value={boroughStatusFilter}
                  onChange={(event) => {
                    setRowPage(1);
                    setBoroughStatusFilter(event.target.value);
                  }}
                >
                  <option value="all">All borough statuses</option>
                  <option value="success">Borough mapped</option>
                  <option value="not_identifiable">Borough not identifiable</option>
                  <option value="not_london_borough">Not London borough</option>
                  <option value="unsupported">Borough unsupported</option>
                  <option value="error">Borough errors</option>
                </select>
              </label>
              <input
                className="small-input compact-input"
                inputMode="numeric"
                value={rowCsvFileId}
                onChange={(event) => setRowCsvFileId(event.target.value)}
                placeholder="CSV file id"
              />
              <input
                className="small-input borough-input"
                list="borough-filter-options"
                value={boroughNameFilter}
                onChange={(event) => setBoroughNameFilter(event.target.value)}
                placeholder="Borough name"
              />
              <datalist id="borough-filter-options">
                {boroughs?.items.map((borough) => (
                  <option key={borough.borough_name} value={borough.borough_name} />
                ))}
              </datalist>
              <input
                className="small-input date-input"
                type="date"
                value={dateFromFilter}
                onChange={(event) => setDateFromFilter(event.target.value)}
                title="Date from"
              />
              <input
                className="small-input date-input"
                type="date"
                value={dateToFilter}
                onChange={(event) => setDateToFilter(event.target.value)}
                title="Date to"
              />
              <button className="button" type="submit">
                Apply
              </button>
              <a className="button" href={rowExportUrl()}>
                Export CSV
              </a>
            </form>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>CSV / row</th>
                  <th>Dataset</th>
                  <th>Status</th>
                  <th>Date range</th>
                  <th>Borough</th>
                  <th>Source row</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {rows?.items.map((row) => (
                  <tr key={`${row.csv_file_id}-${row.row_number}`}>
                    <td>
                      <strong>#{row.csv_file_id}</strong> row {row.row_number}
                      <div className="muted truncate">{row.csv_title || "-"}</div>
                    </td>
                    <td className="truncate">{row.source_title || "-"}</td>
                    <td>
                      <StatusPill status={row.status} />
                      <div className="muted">
                        date: {row.date_status}, borough: {row.borough_status}
                      </div>
                    </td>
                    <td>
                      {row.date_start || "-"}
                      {row.date_end && row.date_end !== row.date_start ? ` to ${row.date_end}` : ""}
                    </td>
                    <td>{row.borough_name || "-"}</td>
                    <td>
                      <code className="row-json">{compactJson(row.source_row_json)}</code>
                    </td>
                    <td className={row.status === "error" ? "error-text" : ""}>
                      {row.error_message || "-"}
                    </td>
                  </tr>
                ))}
                {!loading && rows?.items.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="empty-cell">
                      No row transformations found for this filter.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <Pagination
            page={rowPage}
            pageSize={ROW_PAGE_SIZE}
            total={rows?.total}
            onPageChange={setRowPage}
          />
        </section>
      </div>
    </main>
  );
}

function StatCard({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value ?? "-"}</div>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  return <span className={`status-pill status-${status}`}>{status.replaceAll("_", " ")}</span>;
}

function RuleSummary({ status, rule }: { status: string | null; rule: unknown }) {
  const output =
    rule && typeof rule === "object" && "output" in rule
      ? (rule as { output?: unknown }).output
      : null;
  const outputObject = output && typeof output === "object" ? output as Record<string, unknown> : {};
  const confidence =
    rule && typeof rule === "object" && "confidence" in rule && typeof (rule as { confidence?: unknown }).confidence === "number"
      ? (rule as { confidence: number }).confidence
      : null;
  const columns =
    rule && typeof rule === "object" && "columns" in rule && Array.isArray((rule as { columns?: unknown }).columns)
      ? ((rule as { columns: unknown[] }).columns).map((column) => String(column)).filter(Boolean)
      : [];
  const outputColumns = [
    "date_column",
    "start_date_column",
    "end_date_column",
    "year_column",
    "month_column",
    "quarter_column",
    "borough_column",
  ]
    .map((key) => outputObject[key])
    .filter((value): value is string => typeof value === "string" && value.length > 0);
  const visibleColumns = Array.from(new Set([...columns, ...outputColumns]));
  const yearStartMonth =
    typeof outputObject.year_range_start_month === "number"
      ? outputObject.year_range_start_month
      : null;
  return (
    <span>
      {status || "-"}
      {confidence !== null ? <span className="muted"> ({Math.round(confidence * 100)}%)</span> : null}
      {visibleColumns.length ? <span className="muted"> via {visibleColumns.join(", ")}</span> : null}
      {yearStartMonth ? <span className="muted">, year starts month {yearStartMonth}</span> : null}
    </span>
  );
}

function RowCountSummary({ plan }: { plan: TransformationPlan }) {
  if (!plan.row_total_count) {
    return <span className="muted">not applied</span>;
  }
  return (
    <span className="row-count-summary">
      <span className="success-text">{plan.row_success_count} ok</span>
      <span>{plan.row_partial_count} partial</span>
      <span className={plan.row_error_count ? "error-text" : ""}>{plan.row_error_count} errors</span>
    </span>
  );
}

function warningPreview(plan: TransformationPlan): string {
  const response = plan.response_json;
  if (!response || typeof response !== "object" || !("warnings" in response)) {
    return "";
  }
  const warnings = (response as { warnings?: unknown }).warnings;
  if (!Array.isArray(warnings) || warnings.length === 0) {
    return "";
  }
  const firstWarning = String(warnings[0] || "");
  return firstWarning.length > 140 ? `${firstWarning.slice(0, 140)}...` : firstWarning;
}

function compactJson(value: unknown): string {
  try {
    const serialized = JSON.stringify(value);
    if (!serialized) return "-";
    return serialized.length > 180 ? `${serialized.slice(0, 180)}...` : serialized;
  } catch {
    return "-";
  }
}

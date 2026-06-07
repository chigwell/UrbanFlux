"use client";

import Link from "next/link";
import { ArrowLeft, Database, Download, ExternalLink } from "lucide-react";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Pagination } from "@/components/Pagination";
import { StatusBadge } from "@/components/StatusBadge";
import { CsvFile, CsvPreview, apiGet, apiPost, formatBytes } from "@/lib/api";

const PAGE_SIZE = 50;

export default function CsvPreviewPage() {
  const params = useParams<{ id: string }>();
  const fileId = params.id;
  const [file, setFile] = useState<CsvFile | null>(null);
  const [preview, setPreview] = useState<CsvPreview | null>(null);
  const [page, setPage] = useState(1);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const fileData = await apiGet<CsvFile>(`/api/csv-files/${fileId}`);
      setFile(fileData);
      if (fileData.status === 1) {
        const previewData = await apiGet<CsvPreview>(
          `/api/csv-files/${fileId}/preview?page=${page}&page_size=${PAGE_SIZE}`,
        );
        setPreview(previewData);
      } else {
        setPreview(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load CSV file");
    }
  }, [fileId, page]);

  useEffect(() => {
    void load();
  }, [load]);

  async function downloadFile() {
    setDownloading(true);
    setError(null);
    try {
      await apiPost(`/api/csv-files/${fileId}/download`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setDownloading(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <Link className="brand" href="/">
          <span className="brand-mark">
            <Database size={20} />
          </span>
          <span>London Datastore CSV Dashboard</span>
        </Link>
        <Link className="button" href={file?.source_id ? `/sources/${file.source_id}` : "/"}>
          <ArrowLeft size={17} />
          Source
        </Link>
      </header>

      <div className="container">
        {error ? <div className="alert error">{error}</div> : null}

        {file ? (
          <>
            <div className="section-heading">
              <div>
                <h1>{file.title}</h1>
                <p>{file.source_title || file.file_name || "CSV resource"}</p>
              </div>
              <div className="actions">
                <a
                  className="button"
                  href={file.csv_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  <ExternalLink size={17} />
                  Remote CSV
                </a>
                {file.status !== 1 ? (
                  <button
                    className="button primary"
                    type="button"
                    disabled={downloading}
                    onClick={downloadFile}
                  >
                    <Download size={17} />
                    {downloading ? "Saving" : "Save locally"}
                  </button>
                ) : null}
              </div>
            </div>

            <section className="stats-grid" aria-label="File summary">
              <FileStat label="Status" value={<StatusBadge status={file.status} />} />
              <FileStat label="Remote size" value={formatBytes(file.source_file_size_bytes)} />
              <FileStat label="Local size" value={formatBytes(file.file_size_bytes)} />
              <FileStat label="Filename" value={file.file_name || "-"} />
              <FileStat label="Path" value={file.local_path || "-"} />
            </section>

            {file.status !== 1 ? (
              <div className="alert">Save the CSV locally before previewing rows.</div>
            ) : null}

            {preview ? (
              <>
                <div className="toolbar">
                  <span className="muted">
                    {preview.total_rows === null
                      ? `${preview.rows.length} rows on this page`
                      : `${preview.total_rows.toLocaleString()} rows`}
                  </span>
                </div>
                <div className="table-wrap csv-table">
                  <table>
                    <thead>
                      <tr>
                        {preview.columns.map((column) => (
                          <th key={column}>{column}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.rows.map((row, index) => (
                        <tr key={index}>
                          {preview.columns.map((column) => (
                            <td key={column}>{row[column]}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Pagination
                  page={page}
                  pageSize={PAGE_SIZE}
                  total={preview.total_rows}
                  hasMore={preview.has_more}
                  onPageChange={setPage}
                />
              </>
            ) : null}
          </>
        ) : (
          <div className="alert">Loading CSV file.</div>
        )}
      </div>
    </main>
  );
}

function FileStat({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value" style={{ fontSize: 16, lineHeight: 1.35 }}>
        {value}
      </div>
    </div>
  );
}

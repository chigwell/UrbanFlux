"use client";

import Link from "next/link";
import { ArrowLeft, Database, Download, ExternalLink, FileText } from "lucide-react";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Pagination } from "@/components/Pagination";
import { StatusBadge } from "@/components/StatusBadge";
import {
  CsvFile,
  PageResult,
  Source,
  apiGet,
  apiPost,
  formatBytes,
  formatDate,
} from "@/lib/api";

const PAGE_SIZE = 20;

export default function SourceDetailPage() {
  const params = useParams<{ id: string }>();
  const sourceId = params.id;
  const [source, setSource] = useState<Source | null>(null);
  const [files, setFiles] = useState<PageResult<CsvFile> | null>(null);
  const [page, setPage] = useState(1);
  const [downloadingId, setDownloadingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [sourceData, fileData] = await Promise.all([
        apiGet<Source>(`/api/sources/${sourceId}`),
        apiGet<PageResult<CsvFile>>(
          `/api/sources/${sourceId}/csv-files?page=${page}&page_size=${PAGE_SIZE}`,
        ),
      ]);
      setSource(sourceData);
      setFiles(fileData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load source");
    }
  }, [page, sourceId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function downloadFile(fileId: number) {
    setDownloadingId(fileId);
    setError(null);
    try {
      await apiPost(`/api/csv-files/${fileId}/download`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setDownloadingId(null);
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
        <Link className="button" href="/">
          <ArrowLeft size={17} />
          Sources
        </Link>
      </header>

      <div className="container">
        {error ? <div className="alert error">{error}</div> : null}

        {source ? (
          <>
            <div className="section-heading">
              <div>
                <h1>{source.title}</h1>
                <p>{source.organisation_name || "Unknown publisher"}</p>
              </div>
              <a
                className="button"
                href={source.dataset_url}
                target="_blank"
                rel="noreferrer"
              >
                <ExternalLink size={17} />
                Source
              </a>
            </div>

            <section className="detail-grid">
              <div className="panel">
                <h2>Description</h2>
                <div className="description">{source.description || "No description saved."}</div>
              </div>

              <aside className="panel">
                <h2>Metadata</h2>
                <dl className="meta-list">
                  <Meta label="Dataset ID" value={source.uuid} />
                  <Meta label="Source code" value={source.source_code || "-"} />
                  <Meta label="Licence" value={source.licence_name || "-"} />
                  <Meta label="Created at source" value={formatDate(source.created_at_source)} />
                  <Meta label="Updated at source" value={formatDate(source.updated_at_source)} />
                  <Meta label="CSV files" value={String(source.csv_count)} />
                </dl>
              </aside>
            </section>

            <section className="panel" style={{ marginTop: 18 }}>
              <h2>Tags and Categories</h2>
              <div className="chips">
                {[...source.categories, ...source.tags].map((item) => (
                  <span className="chip" key={item}>
                    {item}
                  </span>
                ))}
                {source.categories.length + source.tags.length === 0 ? (
                  <span className="muted">No tags saved.</span>
                ) : null}
              </div>
            </section>

            <section style={{ marginTop: 24 }}>
              <div className="section-heading">
                <div>
                  <h2>CSV Files</h2>
                  <p>{files ? `${files.total.toLocaleString()} resources` : "Loading resources"}</p>
                </div>
              </div>

              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>File</th>
                      <th>Size</th>
                      <th>Status</th>
                      <th>Saved path</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {files?.items.map((file) => (
                      <tr key={file.id}>
                        <td>
                          <div className="title-link">{file.title}</div>
                          <div className="muted">{file.file_name || file.resource_uuid}</div>
                        </td>
                        <td>{formatBytes(file.source_file_size_bytes || file.file_size_bytes)}</td>
                        <td>
                          <StatusBadge status={file.status} />
                          {file.error_message ? (
                            <div className="muted">{file.error_message}</div>
                          ) : null}
                        </td>
                        <td>{file.local_path || "-"}</td>
                        <td>
                          <div className="actions">
                            {file.status === 1 ? (
                              <Link className="button" href={`/csv/${file.id}`}>
                                <FileText size={17} />
                                Preview
                              </Link>
                            ) : (
                              <button
                                className="button"
                                type="button"
                                disabled={downloadingId === file.id}
                                onClick={() => downloadFile(file.id)}
                              >
                                <Download size={17} />
                                {downloadingId === file.id ? "Saving" : "Save"}
                              </button>
                            )}
                            <a
                              className="icon-button"
                              title="Open remote CSV"
                              href={file.csv_url}
                              target="_blank"
                              rel="noreferrer"
                            >
                              <ExternalLink size={17} />
                            </a>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {files ? (
                <Pagination
                  page={page}
                  pageSize={PAGE_SIZE}
                  total={files.total}
                  onPageChange={setPage}
                />
              ) : null}
            </section>

            <section className="panel" style={{ marginTop: 24 }}>
              <h2>Raw Metadata</h2>
              <pre className="raw-json">{JSON.stringify(source.raw_metadata, null, 2)}</pre>
            </section>
          </>
        ) : (
          <div className="alert">Loading source.</div>
        )}
      </div>
    </main>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="meta-item">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

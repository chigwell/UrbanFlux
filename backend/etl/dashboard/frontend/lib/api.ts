export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
  "http://localhost:8000";

export type PageResult<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
};

export type SyncRun = {
  id: number;
  mode: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  pages_scanned: number;
  datasets_seen: number;
  sources_upserted: number;
  csv_files_seen: number;
  csv_files_downloaded: number;
  errors_count: number;
  message: string | null;
};

export type Stats = {
  sources_count: number;
  csv_files_count: number;
  pending_count: number;
  success_count: number;
  error_count: number;
  last_sync: SyncRun | null;
};

export type BoroughBoundary = {
  id: number;
  borough_name: string;
  borough_code: string | null;
  source_url: string | null;
  source_file_name: string | null;
  coordinate_system: string | null;
  geometry_type: string | null;
  border_coordinates: [number, number][][];
  source_file_hash: string | null;
  ingested_at: string;
  updated_at_local: string;
};

export type BoroughBoundaryResponse = {
  items: BoroughBoundary[];
  total: number;
};

export type Borough = {
  borough_name: string;
  borough_code: string | null;
};

export type BoroughResponse = {
  items: Borough[];
  total: number;
};

export type DownloadJob = {
  job_id: string | null;
  status: "idle" | "running" | "success" | "completed_with_errors" | "canceled" | "error";
  total: number;
  completed: number;
  success_count: number;
  error_count: number;
  current_file_id: number | null;
  current_file_title: string | null;
  started_at: string | null;
  finished_at: string | null;
  message: string | null;
  progress_percent: number;
  is_running: boolean;
};

export type TransformationStats = {
  current_rule_schema_version: number;
  downloaded_csv_files: number;
  planned_csv_files: number;
  plan_status: Record<string, number>;
  row_transformed_csv_files: number;
  row_status: Record<string, number>;
  row_transformations: number;
  pending_plans: number;
  outdated_successful_plans: number;
  pending_row_applications: number;
};

export type TransformationJob = {
  job_id: string | null;
  status: "idle" | "running" | "success" | "completed_with_errors" | "canceled" | "error";
  total: number;
  completed: number;
  planned_count: number;
  applied_count: number;
  success_count: number;
  error_count: number;
  current_file_id: number | null;
  current_file_title: string | null;
  current_step: string | null;
  started_at: string | null;
  finished_at: string | null;
  message: string | null;
  stats: TransformationStats | null;
  progress_percent: number;
  is_running: boolean;
};

export type TransformationPlan = {
  id: number;
  csv_file_id: number;
  csv_title: string | null;
  source_title: string | null;
  status: string;
  attempts: number;
  rule_schema_version: number;
  csv_content_hash: string | null;
  csv_current_content_hash: string | null;
  csv_content_changed: number;
  model: string | null;
  llm_endpoint: string | null;
  header_json: string[];
  sample_rows_json: Record<string, unknown>[];
  prompt_messages_json: { role: string; content: string }[];
  response_json: unknown;
  date_range_status: string | null;
  date_range_rule_json: TransformationRule | null;
  borough_status: string | null;
  borough_rule_json: TransformationRule | null;
  transformation_summary: string | null;
  error_message: string | null;
  row_total_count: number;
  row_success_count: number;
  row_partial_count: number;
  row_error_count: number;
  warning_count: number;
  created_at_local: string;
  updated_at_local: string;
  created_at?: string;
  updated_at?: string;
};

export type TransformationRule = {
  status: string;
  confidence: number;
  rule_description: string;
  columns: string[];
  output: Record<string, unknown>;
};

export type CsvRowTransformation = {
  id?: number;
  csv_file_id: number;
  transformation_plan_id: number;
  row_number: number;
  source_row_hash: string;
  source_row_json: Record<string, unknown>;
  date_start: string | null;
  date_end: string | null;
  borough_name: string | null;
  date_status: string;
  borough_status: string;
  status: string;
  error_message: string | null;
  created_at_local: string;
  updated_at_local: string;
  created_at?: string;
  updated_at?: string;
  csv_title: string | null;
  csv_file_name: string | null;
  source_title: string | null;
};

export type BoroughDataFile = {
  csv_file_id: number;
  csv_title: string | null;
  csv_file_name: string | null;
  total_rows: number;
  rows: CsvRowTransformation[];
};

export type BoroughDataDataset = {
  source_id: number;
  source_title: string | null;
  files: BoroughDataFile[];
};

export type BoroughData = {
  borough_name: string;
  rows_per_file: number;
  max_files: number;
  total_rows: number;
  total_files: number;
  total_datasets: number;
  datasets: BoroughDataDataset[];
};

export type Source = {
  id: number;
  uuid: string;
  source_code: string | null;
  dataset_url: string;
  title: string;
  description: string | null;
  organisation_name: string | null;
  licence_name: string | null;
  created_at_source: string | null;
  updated_at_source: string | null;
  tags: string[];
  categories: string[];
  raw_metadata: unknown;
  scraped_at: string;
  csv_count: number;
  pending_count: number;
  success_count: number;
  error_count: number;
};

export type CsvFile = {
  id: number;
  dataset_source_id: number;
  source_id?: number;
  source_title?: string;
  resource_uuid: string | null;
  resource_code: string | null;
  title: string;
  description: string | null;
  csv_url: string;
  local_path: string | null;
  file_name: string | null;
  file_size_bytes: number | null;
  source_file_size_bytes: number | null;
  content_hash: string | null;
  format: string;
  status: number;
  error_message: string | null;
  downloaded_at: string | null;
};

export type CsvPreview = {
  file: CsvFile;
  columns: string[];
  rows: Record<string, string>[];
  page: number;
  page_size: number;
  total_rows: number | null;
  has_more: boolean;
};

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json() as Promise<T>;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    return typeof payload.detail === "string"
      ? payload.detail
      : `Request failed with ${response.status}`;
  } catch {
    return `Request failed with ${response.status}`;
  }
}

export function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(size >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-GB", {
    year: "numeric",
    month: "short",
    day: "2-digit",
  }).format(date);
}

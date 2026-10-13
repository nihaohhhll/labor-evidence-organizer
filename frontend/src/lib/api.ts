/**
 * Typed API client for the Labor Evidence Organizer backend.
 *
 * Every request goes through `request()`, which is the single place that
 * attaches the bearer token, parses the uniform error envelope described in
 * docs/06_API_SPEC.md and converts failures into `ApiError`.
 */

export type ApiErrorBody = {
  error: { code: string; message: string; request_id: string };
};

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId: string;

  constructor(status: number, code: string, message: string, requestId = "") {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

const BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1";

const TOKEN_KEY = "leo.token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
};

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...opts.headers,
  };
  // An empty Content-Type means "let the browser fill it in" — required for
  // multipart uploads so it can set the boundary.
  if (headers["Content-Type"] === "") delete headers["Content-Type"];

  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      method: opts.method ?? "GET",
      headers,
      // FormData must be passed through untouched; JSON bodies are stringified.
      body:
        opts.body === undefined
          ? undefined
          : opts.body instanceof FormData
            ? opts.body
            : JSON.stringify(opts.body),
      signal: opts.signal,
    });
  } catch (err) {
    // Network failure: surface it with a stable code the UI can branch on.
    throw new ApiError(0, "NETWORK_ERROR", "无法连接服务器，请稍后重试。");
  }

  if (res.status === 204) return undefined as T;

  const text = await res.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = null;
    }
  }

  if (!res.ok) {
    const envelope = payload as ApiErrorBody | null;
    const err = envelope?.error;
    throw new ApiError(
      res.status,
      err?.code ?? "HTTP_ERROR",
      err?.message ?? `请求失败（${res.status}）`,
      err?.request_id ?? "",
    );
  }

  return payload as T;
}

/** GET with the bearer token; failures use the project error envelope. */
async function fetchWithAuth(path: string): Promise<Response> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, { headers });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "无法连接服务器，请稍后重试。");
  }
  if (res.ok) return res;
  let payload: ApiErrorBody | null = null;
  try {
    payload = JSON.parse(await res.text()) as ApiErrorBody;
  } catch {
    payload = null;
  }
  throw new ApiError(
    res.status,
    payload?.error?.code ?? "HTTP_ERROR",
    payload?.error?.message ?? `请求失败（${res.status}）`,
    payload?.error?.request_id ?? "",
  );
}

async function fetchBlob(path: string): Promise<Blob> {
  return (await fetchWithAuth(path)).blob();
}

export function parseDownloadFilename(header: string | null): string | null {
  if (!header) return null;
  // RFC 5987 `filename*` (UTF-8) wins over the ASCII fallback whenever present.
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (utf8?.[1]) {
    try {
      const decoded = decodeURIComponent(utf8[1]).trim();
      if (decoded) return decoded;
    } catch {
      /* fall through to the plain parameter */
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain?.[1]?.trim() || null;
}

/**
 * Authenticated download: fetch the bytes with the token, then trigger the
 * browser's save dialog via a blob URL. A bare `<a href>` cannot carry the
 * Authorization header and would hit 401 on protected downloads.
 */
async function downloadWithAuth(path: string, fallbackName: string): Promise<void> {
  const res = await fetchWithAuth(path);
  const blob = await res.blob();
  const name = parseDownloadFilename(res.headers.get("Content-Disposition")) ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export const api = {
  register: (body: { email: string; password: string; display_name?: string }) =>
    request<import("./types").TokenResponse>("/auth/register", {
      method: "POST",
      body,
    }),
  login: (body: { email: string; password: string }) =>
    request<import("./types").TokenResponse>("/auth/login", { method: "POST", body }),
  me: () => request<import("./types").User>("/auth/me"),

  listCases: (limit = 20, offset = 0) =>
    request<import("./types").CasePage>(`/cases?limit=${limit}&offset=${offset}`),
  getCase: (id: string) => request<import("./types").CaseDetail>(`/cases/${id}`),
  createCase: (body: { name: string; description?: string | null }) =>
    request<import("./types").CaseDetail>("/cases", { method: "POST", body }),
  updateCase: (id: string, body: Record<string, unknown>) =>
    request<import("./types").CaseDetail>(`/cases/${id}`, { method: "PATCH", body }),
  deleteCase: (id: string) => request<void>(`/cases/${id}`, { method: "DELETE" }),

  // ---- files ----
  uploadFiles: (caseId: string, files: File[]) => {
    const form = new FormData();
    for (const f of files) form.append("files", f, f.name);
    return request<import("./types").UploadResult>(`/cases/${caseId}/files`, {
      method: "POST",
      body: form,
      // Let the browser set the multipart boundary itself.
      headers: { "Content-Type": "" },
    });
  },
  listFiles: (caseId: string) =>
    request<import("./types").CaseFileList>(`/cases/${caseId}/files`),
  deleteFile: (id: string) => request<void>(`/files/${id}`, { method: "DELETE" }),
  retryFile: (id: string) =>
    request<import("./types").CaseFile>(`/files/${id}/retry`, { method: "POST" }),
  fileContentUrl: (id: string) => `${BASE_URL}/files/${id}/content`,
  /**
   * Fetch an original file *with* the bearer token. `<img>`/`<iframe>` src
   * cannot carry an Authorization header, so previews go through this and
   * are turned into a blob: URL. Permission checks stay on the backend; a
   * missing original surfaces as ApiError 410 (CONTENT_MISSING).
   */
  fetchFileContent: (id: string): Promise<Blob> => fetchBlob(`/files/${id}/content`),

  // ---- analysis ----
  analyzeFile: (id: string) =>
    request<import("./types").Analysis>(`/files/${id}/analyze`, { method: "POST" }),
  analyzeCase: (caseId: string) =>
    request<{ analyzed: number; failed: number }>(`/cases/${caseId}/analyze`, {
      method: "POST",
    }),
  getAnalysis: (id: string) => request<import("./types").Analysis>(`/files/${id}/analysis`),

  // ---- evidence ----
  listEvidence: (caseId: string) =>
    request<{ evidence: import("./types").EvidenceRow[]; total: number }>(
      `/cases/${caseId}/evidence`,
    ),
  updateEvidence: (id: string, body: Record<string, unknown>) =>
    request<import("./types").EvidenceRow>(`/evidence/${id}`, { method: "PATCH", body }),
  confirmEvidence: (id: string) =>
    request<{ id: string; review_status: string }>(`/evidence/${id}/confirm`, {
      method: "POST",
    }),
  reanalyzeEvidence: (id: string) =>
    request<import("./types").EvidenceRow>(`/evidence/${id}/reanalyze`, { method: "POST" }),

  // ---- review ----
  listReviewItems: (caseId: string) =>
    request<{ items: import("./types").ReviewItem[]; total: number }>(
      `/cases/${caseId}/review-items`,
    ),
  saveReviewValue: (id: string, userValue: Record<string, string | null>) =>
    request<import("./types").ReviewItem>(`/review-items/${id}`, {
      method: "PATCH",
      body: { user_value: userValue },
    }),
  confirmReviewItem: (id: string) =>
    request<{ id: string; status: string; applied: Record<string, unknown> }>(
      `/review-items/${id}/confirm`,
      { method: "POST" },
    ),
  discardReviewItem: (id: string) =>
    request<{ id: string; status: string }>(`/review-items/${id}/discard`, {
      method: "POST",
    }),

  // ---- timeline ----
  listEvents: (caseId: string) =>
    request<{ events: import("./types").TimelineEvent[]; total: number }>(
      `/cases/${caseId}/events`,
    ),
  buildTimeline: (caseId: string) =>
    request<{ events: import("./types").TimelineEvent[]; total: number }>(
      `/cases/${caseId}/events/build`,
      { method: "POST" },
    ),
  createEvent: (caseId: string, body: Record<string, unknown>) =>
    request<import("./types").TimelineEvent>(`/cases/${caseId}/events`, {
      method: "POST",
      body,
    }),
  updateEvent: (id: string, body: Record<string, unknown>) =>
    request<import("./types").TimelineEvent>(`/events/${id}`, { method: "PATCH", body }),
  deleteEvent: (id: string) => request<void>(`/events/${id}`, { method: "DELETE" }),
  mergeEvents: (eventIds: string[], title?: string) =>
    request<import("./types").TimelineEvent>(`/events/merge`, {
      method: "POST",
      body: { event_ids: eventIds, title: title ?? null },
    }),

  // ---- export ----
  createExport: (caseId: string, format: string) =>
    request<import("./types").ExportJob>(`/cases/${caseId}/exports`, {
      method: "POST",
      body: { format },
    }),
  listExports: (caseId: string) =>
    request<{ exports: import("./types").ExportJob[]; total: number }>(
      `/cases/${caseId}/exports`,
    ),
  /** Authenticated download of any export job (case bundle or package volume). */
  downloadExport: (id: string, fallbackName = "export-download") =>
    downloadWithAuth(`/exports/${id}/download`, fallbackName),

  // ---- evidence gaps (A3) ----
  triggerEvidenceGaps: (caseId: string) =>
    request<import("./types").EvidenceGapResult>(`/cases/${caseId}/evidence-gaps`, {
      method: "POST",
    }),
  getLatestEvidenceGaps: (caseId: string) =>
    request<import("./types").EvidenceGapResult>(`/cases/${caseId}/evidence-gaps`),
  getEvidenceGapsHistory: (caseId: string, limit = 20, offset = 0) =>
    request<import("./types").EvidenceGapHistory>(
      `/cases/${caseId}/evidence-gaps/history?limit=${limit}&offset=${offset}`,
    ),

  // ---- material packages (Phase 9-A/9-B/9-C) ----
  listMaterialPackages: (caseId: string, limit = 100, offset = 0) =>
    request<import("./types").MaterialPackageList>(
      `/cases/${caseId}/material-packages?limit=${limit}&offset=${offset}`,
    ),
  createMaterialPackage: (caseId: string, name: string) =>
    request<import("./types").MaterialPackageDetail>(`/cases/${caseId}/material-packages`, {
      method: "POST",
      body: { name },
    }),
  getMaterialPackage: (id: string) =>
    request<import("./types").MaterialPackageDetail>(`/material-packages/${id}`),
  updateMaterialPackage: (id: string, body: { name?: string; status?: string }) =>
    request<import("./types").MaterialPackageDetail>(`/material-packages/${id}`, {
      method: "PATCH",
      body,
    }),
  deleteMaterialPackage: (id: string) =>
    request<void>(`/material-packages/${id}`, { method: "DELETE" }),
  saveMaterialPackageItems: (
    id: string,
    expectedDraftVersion: number,
    items: import("./types").MaterialPackageItemInput[],
  ) =>
    request<import("./types").MaterialPackageDetail>(`/material-packages/${id}/items`, {
      method: "PUT",
      body: { expected_draft_version: expectedDraftVersion, items },
    }),
  createMaterialPackageSnapshot: (id: string, expectedDraftVersion: number) =>
    request<import("./types").MaterialPackageSnapshot>(`/material-packages/${id}/snapshots`, {
      method: "POST",
      body: { expected_draft_version: expectedDraftVersion },
    }),
  listMaterialPackageSnapshots: (id: string) =>
    request<import("./types").MaterialPackageSnapshotList>(
      `/material-packages/${id}/snapshots`,
    ),
  getMaterialPackageSnapshot: (id: string, version: number) =>
    request<import("./types").MaterialPackageSnapshot>(
      `/material-packages/${id}/snapshots/${version}`,
    ),
  // ---- package volume exports (Phase 9-C: 成卷输出) ----
  createMaterialPackageExport: (
    id: string,
    body: { format: string; snapshot_version?: number; include_gap_appendix?: boolean },
  ) =>
    request<import("./types").ExportJob>(`/material-packages/${id}/exports`, {
      method: "POST",
      body,
    }),
  listMaterialPackageExports: (id: string, limit = 100, offset = 0) =>
    request<{ exports: import("./types").ExportJob[]; total: number }>(
      `/material-packages/${id}/exports?limit=${limit}&offset=${offset}`,
    ),
};

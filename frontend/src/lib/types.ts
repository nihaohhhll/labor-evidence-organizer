/** Shared frontend types mirroring the backend Pydantic schemas. */

export type User = {
  id: string;
  email: string;
  display_name: string | null;
  created_at: string;
};

export type TokenResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
};

export type CaseSummary = {
  id: string;
  name: string;
  description: string | null;
  status: "ACTIVE" | "ARCHIVED" | "CLOSED";
  created_at: string;
  updated_at: string;
};

export type CaseDetail = CaseSummary & {
  file_count: number;
  evidence_count: number;
  event_count: number;
};

export type CasePage = {
  items: CaseSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type FileStatus =
  | "UPLOADED"
  | "QUEUED"
  | "PROCESSING"
  | "REVIEW_REQUIRED"
  | "COMPLETED"
  | "FAILED";

export type EvidenceItem = {
  id: string;
  case_id: string;
  evidence_number: number;
  title: string;
  category: string;
  event_date: string | null;
  summary: string | null;
  proof_purpose: string | null;
  confidence: number | null;
  review_status: "PENDING" | "CONFIRMED" | "REJECTED";
};

export type TimelineEvent = {
  id: string;
  case_id: string;
  event_date: string | null;
  precision: "day" | "month" | "unknown";
  title: string;
  description: string | null;
  confidence: number | null;
  review_status: string;
};

export type CaseFile = {
  id: string;
  case_id: string;
  original_filename: string;
  mime_type: string;
  size: number;
  sha256: string;
  status: FileStatus;
  error_message: string | null;
  created_at: string;
  download_url: string;
};

export type UploadResult = {
  files: CaseFile[];
  skipped: { filename: string; reason: string }[];
};

export type CaseFileList = {
  files: CaseFile[];
  status_counts: Record<string, number>;
};

export type Analysis = {
  id: string;
  file_id: string;
  provider: string;
  model: string;
  prompt_version: string;
  classification: string | null;
  classification_reason: string | null;
  confidence: number | null;
  raw_text: string | null;
  created_at: string;
  dates: string[];
  amounts: string[];
  persons: string[];
  organizations: string[];
  events: { kind: string; value: string; excerpt: string }[];
  summary: string | null;
  proof_purpose: string | null;
};

export type EvidenceRow = {
  id: string;
  case_id: string;
  source_file_id: string | null;
  evidence_number: number;
  title: string;
  category: string;
  event_date: string | null;
  summary: string | null;
  proof_purpose: string | null;
  confidence: number | null;
  review_status: "PENDING" | "CONFIRMED" | "REJECTED";
  user_edited_fields: string[];
  created_at: string;
  updated_at: string;
};

export type ReviewItem = {
  id: string;
  case_id: string;
  entity_type: string;
  entity_id: string;
  field_name: string;
  ai_value: Record<string, string | null> | null;
  user_value: Record<string, string | null> | null;
  status: string;
  confidence: number | null;
};

export type GapSource = {
  kind: string;
  id: string;
  excerpt: string | null;
};

export type MissingItem = {
  code: string;
  title: string;
  description: string;
  related_fact_ids: string[];
  suggested_evidence_types: string[];
  priority: string;
  gap_id: string | null;
  sources: GapSource[];
  check_basis: Record<string, unknown> | null;
};

export type EvidenceGapResult = {
  id: string;
  case_id: string;
  version: number;
  status: string;
  gap_json: { missing_items: MissingItem[] } | null;
  error_type: string | null;
  error_message: string | null;
  created_at: string;
};

export type EvidenceGapHistory = {
  results: EvidenceGapResult[];
  total: number;
};

export type ExportJob = {
  id: string;
  case_id: string;
  format: string;
  status: string;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
  // Phase 9-C: material package binding (absent/null for case bundles)
  package_id?: string | null;
  snapshot_id?: string | null;
  snapshot_version?: number | null;
  include_gap_appendix?: boolean;
  gap_result_id?: string | null;
};

// ---------- material packages (Phase 9-A/9-B) ----------

export type MaterialPackageStatus = "DRAFT" | "PUBLISHED" | "ARCHIVED";

export type MaterialPackageItemReview = "PENDING" | "APPROVED" | "REJECTED";

export type MaterialPackageItem = {
  id: string;
  evidence_id: string;
  evidence_number: number | null;
  source_file_id: string | null;
  item_order: number;
  display_number: number;
  display_name: string;
  proof_purpose: string | null;
  review_status: MaterialPackageItemReview;
  created_at: string;
  updated_at: string;
};

export type MaterialPackage = {
  id: string;
  case_id: string;
  name: string;
  status: MaterialPackageStatus;
  draft_version: number;
  item_count: number;
  snapshot_count: number;
  created_at: string;
  updated_at: string;
};

export type MaterialPackageDetail = MaterialPackage & {
  items: MaterialPackageItem[];
};

export type MaterialPackageList = {
  items: MaterialPackage[];
  total: number;
  limit: number;
  offset: number;
};

export type MaterialPackageItemInput = {
  evidence_id: string;
  display_name?: string | null;
  proof_purpose?: string | null;
  review_status?: MaterialPackageItemReview | null;
};

export type MaterialPackageSnapshotItem = {
  item_id: string;
  evidence_id: string;
  evidence_number: number | null;
  item_order: number;
  display_number: number;
  display_name: string;
  proof_purpose: string | null;
  review_status: string;
  evidence_title: string | null;
  evidence_category: string | null;
  source_file_id: string | null;
  evidence_updated_at: string | null;
  /** Computed at read time by the snapshot detail endpoint, never stored. */
  source_status?: "OK" | "CHANGED" | "MISSING";
};

export type MaterialPackageSnapshot = {
  id: string;
  package_id: string;
  version: number;
  draft_version_captured: number;
  created_at: string;
  content: {
    package?: { name: string; status: string };
    draft_version?: number;
    captured_at?: string;
    items: MaterialPackageSnapshotItem[];
  };
};

export type MaterialPackageSnapshotList = {
  snapshots: MaterialPackageSnapshot[];
  total: number;
};

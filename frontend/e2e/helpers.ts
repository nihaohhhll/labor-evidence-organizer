import { expect, request as pwRequest, type APIRequestContext, type Page } from "@playwright/test";

/**
 * Shared setup for Phase 9-C UI E2E. API calls with `request` create the
 * fixtures (users, cases, evidence, snapshots) that each scenario then
 * drives through the real UI.
 *
 * URL joining: Playwright resolves request URLs like `new URL(url, baseURL)`,
 * so a path-absolute URL ("/auth/register") would drop the /api/v1 prefix.
 * Every call therefore uses a *relative* path against a baseURL ending in "/".
 *
 * Auth: /auth/register allows 5/min and /auth/login 10/min per IP — one
 * shared account is registered per run and injected into localStorage
 * ("leo.token") instead of logging in through the UI in every test.
 */

export const API_BASE = (
  process.env.API_BASE ?? "http://127.0.0.1:8000/api/v1"
).replace(/\/$/, "");
const CONTEXT_BASE = `${API_BASE}/`;

export type TestUser = { email: string; password: string; token: string };

export async function newAuthorizedApi(token: string): Promise<APIRequestContext> {
  return pwRequest.newContext({
    baseURL: CONTEXT_BASE,
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  });
}

export async function registerUser(tag: string): Promise<TestUser> {
  const email = `e2e9c-${tag}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
  const password = "correct-horse-battery";
  const ctx = await pwRequest.newContext({ baseURL: CONTEXT_BASE });
  try {
    const res = await ctx.post("auth/register", {
      data: { email, password, display_name: `E2E ${tag}` },
    });
    expect(res.ok(), await res.text()).toBeTruthy();
    const body = await res.json();
    return { email, password, token: body.access_token };
  } finally {
    await ctx.dispose();
  }
}

/** Seed the bearer token into localStorage before any page script runs. */
export async function seedAuth(page: Page, token: string): Promise<void> {
  await page.addInitScript((t) => window.localStorage.setItem("leo.token", t), token);
}

export async function apiJson<T = any>(
  api: APIRequestContext,
  method: "get" | "post" | "put" | "patch" | "delete",
  path: string,
  data?: unknown,
): Promise<{ status: number; body: T }> {
  const rel = path.startsWith("/") ? path.slice(1) : path;
  const res = await api[method](rel, data === undefined ? undefined : { data });
  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  return { status: res.status(), body: body as T };
}

export async function createCase(api: APIRequestContext, name: string): Promise<string> {
  const { status, body } = await apiJson<{ id: string }>(api, "post", "/cases", {
    name,
    description: "Phase 9-C UI E2E",
  });
  expect(status, JSON.stringify(body)).toBe(201);
  return body.id;
}

/** Manual evidence row (no analysis needed) — fast, deterministic fixture. */
export async function createEvidence(
  api: APIRequestContext,
  caseId: string,
  title = "工资条",
  summary?: string,
): Promise<string> {
  const payload: Record<string, unknown> = {
    title,
    category: "wage",
    confirm_now: true,
    proof_purpose: "用于证明工资数额。",
  };
  if (summary) payload.summary = summary;
  const { status, body } = await apiJson<{ id: string }>(
    api,
    "post",
    `/cases/${caseId}/evidence`,
    payload,
  );
  expect(status, JSON.stringify(body)).toBe(201);
  return body.id;
}

export async function createPackage(
  api: APIRequestContext,
  caseId: string,
  name: string,
): Promise<string> {
  const { status, body } = await apiJson<{ id: string }>(
    api,
    "post",
    `/cases/${caseId}/material-packages`,
    { name },
  );
  expect(status, JSON.stringify(body)).toBe(201);
  return body.id;
}

export async function addItems(
  api: APIRequestContext,
  packageId: string,
  evidenceIds: string[],
): Promise<number> {
  const detail = await apiJson<{ draft_version: number }>(
    api,
    "get",
    `/material-packages/${packageId}`,
  );
  const { status, body } = await apiJson<{ draft_version: number }>(
    api,
    "put",
    `/material-packages/${packageId}/items`,
    {
      expected_draft_version: detail.body.draft_version,
      items: evidenceIds.map((evidence_id) => ({ evidence_id })),
    },
  );
  expect(status, JSON.stringify(body)).toBe(200);
  return body.draft_version;
}

export async function createSnapshot(
  api: APIRequestContext,
  packageId: string,
): Promise<number> {
  const detail = await apiJson<{ draft_version: number }>(
    api,
    "get",
    `/material-packages/${packageId}`,
  );
  const { status, body } = await apiJson<{ version: number }>(
    api,
    "post",
    `/material-packages/${packageId}/snapshots`,
    { expected_draft_version: detail.body.draft_version },
  );
  expect(status, JSON.stringify(body)).toBe(201);
  return body.version;
}

export async function setStatus(
  api: APIRequestContext,
  packageId: string,
  status: string,
): Promise<number> {
  const res = await api.patch(`/material-packages/${packageId}`, { data: { status } });
  return res.status();
}

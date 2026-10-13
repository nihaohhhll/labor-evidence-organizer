"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, api } from "@/lib/api";

/** Create a case (US-001 / Epic A). */
export default function NewCasePage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const created = await api.createCase({
        name: name.trim(),
        description: description.trim() || null,
      });
      router.replace(`/cases/${created.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "创建失败，请稍后重试。");
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg">
      <h1 className="mb-4 text-xl font-semibold">新建案件</h1>
      <form onSubmit={onSubmit} className="card space-y-3">
        <label className="block text-sm">
          <span className="mb-1 block text-slate-600">案件名称 *</span>
          <input
            className="input"
            required
            maxLength={200}
            placeholder="例如：某某科技有限公司违法解除劳动合同"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-slate-600">简单描述</span>
          <textarea
            className="input"
            rows={4}
            maxLength={5000}
            placeholder="简单说明争议经过，仅自己可见"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>

        {error && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
            {error}
          </p>
        )}

        <div className="flex gap-2">
          <button className="btn-primary" type="submit" disabled={busy}>
            {busy ? "创建中…" : "创建案件"}
          </button>
          <button className="btn-ghost" type="button" onClick={() => router.back()}>
            取消
          </button>
        </div>
      </form>
    </div>
  );
}

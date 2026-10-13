"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ApiError, api, getToken } from "@/lib/api";

/** 新建材料包草稿：输入名称 → 创建 → 跳转编辑页。 */
export default function NewMaterialPackagePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) router.replace("/login");
  }, [router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError("请输入材料包名称");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const pkg = await api.createMaterialPackage(params.id, name.trim());
      router.push(`/cases/${params.id}/material-packages/${pkg.id}/edit`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "创建失败，请重试");
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-lg space-y-4">
      <h1 className="text-xl font-semibold">新建材料包</h1>
      <form onSubmit={onSubmit} className="card space-y-3">
        <label className="block text-sm">
          材料包名称
          <input
            className="input mt-1 w-full"
            value={name}
            maxLength={200}
            placeholder="例如：仲裁提交材料（第一版）"
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
        </label>
        {error && (
          <p className="text-sm text-red-600" role="alert">
            {error}
          </p>
        )}
        <div className="flex gap-2">
          <button className="btn-primary" type="submit" disabled={saving}>
            {saving ? "创建中…" : "创建草稿"}
          </button>
          <Link className="btn-ghost" href={`/cases/${params.id}/material-packages`}>
            取消
          </Link>
        </div>
      </form>
    </div>
  );
}

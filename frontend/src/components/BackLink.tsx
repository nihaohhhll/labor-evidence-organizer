"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

/** Back navigation link. `to` omitted = browser history back. */
export default function BackLink({
  href,
  label,
}: {
  href?: string;
  label: string;
}) {
  const router = useRouter();
  if (href) {
    return (
      <Link
        href={href}
        className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900"
      >
        ← {label}
      </Link>
    );
  }
  return (
    <button
      type="button"
      onClick={() => router.back()}
      className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-900"
    >
      ← {label}
    </button>
  );
}

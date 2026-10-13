"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** Root route: send visitors to their case list. */
export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/cases");
  }, [router]);
  return (
    <div className="empty-state" role="status">
      正在跳转…
    </div>
  );
}

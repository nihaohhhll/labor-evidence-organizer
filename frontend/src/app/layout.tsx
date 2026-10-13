import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "劳动争议证据整理器",
  description: "把零散材料整理成可核对、可追溯的证据材料。",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
            <Link href="/cases" className="text-lg font-semibold">
              劳动争议证据整理器
            </Link>
            <nav className="flex items-center gap-4 text-sm text-slate-600">
              <Link href="/cases" className="hover:text-slate-900">
                我的案件
              </Link>
              <Link href="/login" className="hover:text-slate-900">
                登录
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
        <footer className="mx-auto max-w-5xl px-4 py-8 text-xs text-slate-400">
          本系统输出内容仅供参考，不构成正式法律意见或执业律师代理服务。
        </footer>
      </body>
    </html>
  );
}

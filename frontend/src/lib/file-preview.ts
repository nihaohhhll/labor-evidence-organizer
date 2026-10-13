/**
 * Authenticated file preview (Phase 9-B).
 *
 * `<img src>` / `<iframe src>` cannot carry the Authorization header, so the
 * file is fetched through the API client (which enforces backend permission
 * checks) and handed to the DOM as an object URL. A deleted original shows up
 * as an explicit error (backend 410 CONTENT_MISSING) instead of a broken
 * image — OCR text is never substituted for the original.
 */

import { useEffect, useState } from "react";
import { ApiError, api } from "./api";

export type FilePreviewState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; url: string }
  | { kind: "error"; message: string };

export function useFilePreview(fileId: string | null | undefined): FilePreviewState {
  const [state, setState] = useState<FilePreviewState>({ kind: "idle" });

  useEffect(() => {
    if (!fileId) {
      setState({ kind: "idle" });
      return;
    }
    let objectUrl: string | null = null;
    let cancelled = false;
    setState({ kind: "loading" });

    void (async () => {
      try {
        const blob = await api.fetchFileContent(fileId);
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setState({ kind: "ready", url: objectUrl });
      } catch (err) {
        if (cancelled) return;
        setState({
          kind: "error",
          message:
            err instanceof ApiError
              ? err.code === "CONTENT_MISSING"
                ? "原始文件已不存在，无法预览。"
                : err.message
              : "预览加载失败。",
        });
      }
    })();

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [fileId]);

  return state;
}

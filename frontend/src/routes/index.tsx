import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { CaptionStudio } from "../components/CaptionStudio";

// No head() here: the home route inherits title/description/og/twitter from
// __root.tsx, and ships no og:image so serve-time hosting can inject the
// project's social preview (explicit og:image or latest screenshot).
export const Route = createFileRoute("/")({
  component: CaptionStudio,
});

const ACCEPTED_VIDEO_TYPES = ["video/mp4", "video/webm", "video/quicktime", "video/x-matroska"];

interface LocalVideoItem {
  id: string;
  name: string;
  sizeMb: string;
  type: string;
}

function Index() {
  const [mode, setMode] = useState<"local" | "url">("local");
  const [files, setFiles] = useState<LocalVideoItem[]>([]);
  const [urlValue, setUrlValue] = useState("");
  const [urlQueue, setUrlQueue] = useState<string[]>([]);

  const totalQueued = useMemo(() => files.length + urlQueue.length, [files.length, urlQueue.length]);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(event.target.files ?? []);
    if (!selected.length) return;

    const normalized = selected.map((file) => ({
      id: `${file.name}-${file.lastModified}`,
      name: file.name,
      type: file.type || "unknown",
      sizeMb: (file.size / (1024 * 1024)).toFixed(2),
    }));

    setFiles((prev) => {
      const existing = new Set(prev.map((item) => item.id));
      const deduped = normalized.filter((item) => !existing.has(item.id));
      return [...prev, ...deduped];
    });

    event.target.value = "";
  };

  const addUrl = () => {
    const trimmed = urlValue.trim();
    if (!trimmed) return;

    try {
      const parsed = new URL(trimmed);
      if (!(parsed.protocol === "https:" || parsed.protocol === "http:")) return;
      setUrlQueue((prev) => (prev.includes(trimmed) ? prev : [...prev, trimmed]));
      setUrlValue("");
    } catch {
      // ignore invalid URL input until user provides a valid one
    }
  };

  const removeLocal = (id: string) => setFiles((prev) => prev.filter((item) => item.id !== id));
  const removeUrl = (url: string) => setUrlQueue((prev) => prev.filter((item) => item !== url));

  return (
    <div className="min-h-screen bg-background text-foreground">
      <main className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-4 py-10 sm:px-6 lg:px-8">
        <header className="space-y-3">
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">AI Video Captioning Studio</h1>
          <p className="max-w-3xl text-sm text-muted-foreground sm:text-base">
            Queue videos from your device or from direct links, then run the backend pipeline to generate
            formal, sarcastic, humorous-tech, and humorous-non-tech captions for each file.
          </p>
        </header>

        <section className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <div className="rounded-lg border border-border bg-card p-5 sm:p-6">
            <div className="mb-5 flex flex-wrap gap-2">
              <button
                onClick={() => setMode("local")}
                className={`inline-flex items-center rounded-md border px-3 py-2 text-sm font-medium transition-colors ${
                  mode === "local"
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-input bg-background text-foreground hover:bg-accent"
                }`}
                type="button"
              >
                Local upload
              </button>
              <button
                onClick={() => setMode("url")}
                className={`inline-flex items-center rounded-md border px-3 py-2 text-sm font-medium transition-colors ${
                  mode === "url"
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-input bg-background text-foreground hover:bg-accent"
                }`}
                type="button"
              >
                Paste URL
              </button>
            </div>

            {mode === "local" ? (
              <div className="space-y-4">
                <label
                  htmlFor="local-video-upload"
                  className="flex min-h-44 cursor-pointer flex-col items-center justify-center rounded-md border border-dashed border-input bg-background p-6 text-center transition-colors hover:bg-accent"
                >
                  <span className="text-sm font-medium">Drop videos here or click to browse</span>
                  <span className="mt-1 text-xs text-muted-foreground">Accepted: mp4, webm, mov, mkv</span>
                </label>
                <input
                  id="local-video-upload"
                  type="file"
                  accept=".mp4,.webm,.mov,.mkv,video/*"
                  multiple
                  className="sr-only"
                  onChange={handleFileChange}
                />

                {files.length > 0 && (
                  <ul className="space-y-2">
                    {files.map((file) => (
                      <li
                        key={file.id}
                        className="flex items-center justify-between rounded-md border border-border bg-background px-3 py-2"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium">{file.name}</p>
                          <p className="text-xs text-muted-foreground">
                            {file.sizeMb} MB · {file.type || "video"}
                          </p>
                        </div>
                        <button
                          onClick={() => removeLocal(file.id)}
                          type="button"
                          className="ml-3 rounded-md border border-input px-2 py-1 text-xs text-foreground transition-colors hover:bg-accent"
                        >
                          Remove
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex flex-col gap-2 sm:flex-row">
                  <input
                    type="url"
                    value={urlValue}
                    onChange={(event) => setUrlValue(event.target.value)}
                    placeholder="https://example.com/video.mp4"
                    className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm outline-none ring-ring transition focus-visible:ring-2"
                    aria-label="Video URL"
                  />
                  <button
                    onClick={addUrl}
                    type="button"
                    className="inline-flex h-10 items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
                  >
                    Add URL
                  </button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Use direct downloadable video links. Duplicates are ignored automatically.
                </p>

                {urlQueue.length > 0 && (
                  <ul className="space-y-2">
                    {urlQueue.map((url) => (
                      <li
                        key={url}
                        className="flex items-center justify-between rounded-md border border-border bg-background px-3 py-2"
                      >
                        <p className="min-w-0 truncate text-sm">{url}</p>
                        <button
                          onClick={() => removeUrl(url)}
                          type="button"
                          className="ml-3 rounded-md border border-input px-2 py-1 text-xs text-foreground transition-colors hover:bg-accent"
                        >
                          Remove
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

          <aside className="space-y-4 rounded-lg border border-border bg-card p-5 sm:p-6">
            <h2 className="text-lg font-semibold tracking-tight">Queue summary</h2>
            <div className="rounded-md border border-border bg-background p-4">
              <p className="text-sm text-muted-foreground">Total queued videos</p>
              <p className="mt-1 text-3xl font-semibold">{totalQueued}</p>
            </div>

            <dl className="space-y-2 text-sm">
              <div className="flex items-center justify-between rounded-md border border-border bg-background px-3 py-2">
                <dt className="text-muted-foreground">Local files</dt>
                <dd className="font-medium">{files.length}</dd>
              </div>
              <div className="flex items-center justify-between rounded-md border border-border bg-background px-3 py-2">
                <dt className="text-muted-foreground">Video URLs</dt>
                <dd className="font-medium">{urlQueue.length}</dd>
              </div>
            </dl>

            <div className="rounded-md border border-dashed border-input bg-background p-4 text-xs text-muted-foreground">
              Frontend upload + URL queueing is ready. Hook this UI to your Python pipeline endpoint when you add
              backend processing.
            </div>
          </aside>
        </section>
      </main>
    </div>
  );
}

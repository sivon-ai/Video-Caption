import { useEffect, useMemo, useState } from "react";

const ACCEPTED_VIDEO_TYPES = ["video/mp4", "video/webm", "video/quicktime", "video/x-matroska"];
const ACCEPTED_VIDEO_EXTENSIONS = [".mp4", ".webm", ".mov", ".mkv"];
const API_BASE_URL = ((import.meta.env.VITE_BACKEND_URL as string | undefined) ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

interface LocalVideoItem {
  id: string;
  name: string;
  sizeMb: string;
  type: string;
  file: File;
}

interface CaptionResult {
  video: string;
  neutral: string;
  formal: string;
  sarcastic: string;
  humorous_tech: string;
  humorous_non_tech: string;
  factual_description: string;
  processing_seconds: number;
  frame_count: number;
}

interface ProcessingError {
  video: string;
  error: string;
}

interface BatchResponse {
  results: CaptionResult[];
  errors: ProcessingError[];
  output_file: string;
  stats: {
    total: number;
    succeeded: number;
    failed: number;
    processing_seconds: number;
  };
}

interface HealthResponse {
  ok: boolean;
  api_configured: boolean;
  vision_model: string;
  text_model: string;
}

function isAcceptedVideo(file: File) {
  const lowerName = file.name.toLowerCase();
  return (
    ACCEPTED_VIDEO_TYPES.includes(file.type) ||
    ACCEPTED_VIDEO_EXTENSIONS.some((extension) => lowerName.endsWith(extension))
  );
}

export function CaptionStudio() {
  const [mode, setMode] = useState<"local" | "url">("local");
  const [files, setFiles] = useState<LocalVideoItem[]>([]);
  const [urlValue, setUrlValue] = useState("");
  const [urlQueue, setUrlQueue] = useState<string[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [formError, setFormError] = useState("");
  const [response, setResponse] = useState<BatchResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState("");

  const totalQueued = useMemo(() => files.length + urlQueue.length, [files.length, urlQueue.length]);
  const canProcess = totalQueued > 0 && !isProcessing;

  useEffect(() => {
    let cancelled = false;

    fetch(`${API_BASE_URL}/health`)
      .then(async (res) => {
        if (!res.ok) throw new Error("Backend health check failed");
        return (await res.json()) as HealthResponse;
      })
      .then((payload) => {
        if (!cancelled) {
          setHealth(payload);
          setHealthError("");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setHealth(null);
          setHealthError(`Backend offline at ${API_BASE_URL}`);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(event.target.files ?? []);
    if (!selected.length) return;

    const validFiles = selected.filter(isAcceptedVideo);
    if (validFiles.length !== selected.length) {
      setFormError("Some files were skipped. Accepted formats: mp4, webm, mov, mkv.");
    } else {
      setFormError("");
    }

    const normalized = validFiles.map((file) => ({
      id: `${file.name}-${file.lastModified}-${file.size}`,
      name: file.name,
      type: file.type || "video",
      sizeMb: (file.size / (1024 * 1024)).toFixed(2),
      file,
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
      if (!(parsed.protocol === "https:" || parsed.protocol === "http:")) {
        setFormError("Video URL must start with http:// or https://.");
        return;
      }
      setUrlQueue((prev) => (prev.includes(trimmed) ? prev : [...prev, trimmed]));
      setUrlValue("");
      setFormError("");
    } catch {
      setFormError("Enter a valid direct video URL.");
    }
  };

  const processQueue = async () => {
    if (!canProcess) return;

    setIsProcessing(true);
    setFormError("");
    setResponse(null);

    const formData = new FormData();
    files.forEach((item) => formData.append("files", item.file, item.file.name));
    urlQueue.forEach((url) => formData.append("urls", url));

    try {
      const result = await fetch(`${API_BASE_URL}/api/captions/process`, {
        method: "POST",
        body: formData,
      });
      const payload = await result.json();
      if (!result.ok) {
        throw new Error(payload.detail ?? "Caption processing failed.");
      }
      setResponse(payload as BatchResponse);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Caption processing failed.");
    } finally {
      setIsProcessing(false);
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
            Queue videos from your device or direct links, then run the Python AI pipeline to generate formal,
            sarcastic, humorous-tech, and humorous-non-tech captions.
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
                            {file.sizeMb} MB - {file.type || "video"}
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

            <div className="rounded-md border border-border bg-background p-3 text-xs">
              {health ? (
                <p className={health.api_configured ? "text-muted-foreground" : "text-destructive"}>
                  Backend online. {health.api_configured ? "Models configured." : "Add API key and model names."}
                </p>
              ) : (
                <p className="text-destructive">{healthError || "Checking backend..."}</p>
              )}
            </div>

            <button
              onClick={processQueue}
              disabled={!canProcess}
              type="button"
              className="inline-flex h-11 w-full items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isProcessing ? "Generating captions..." : "Run caption pipeline"}
            </button>

            {formError && (
              <div className="rounded-md border border-destructive bg-background p-3 text-sm text-destructive">
                {formError}
              </div>
            )}
          </aside>
        </section>

        {response && (
          <section className="space-y-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <h2 className="text-xl font-semibold tracking-tight">Generated captions</h2>
                <p className="text-sm text-muted-foreground">
                  {response.stats.succeeded} succeeded, {response.stats.failed} failed in{" "}
                  {response.stats.processing_seconds}s
                </p>
              </div>
              <p className="text-xs text-muted-foreground">Saved to {response.output_file}</p>
            </div>

            <div className="grid gap-4">
              {response.results.map((result) => (
                <article key={result.video} className="rounded-lg border border-border bg-card p-5">
                  <div className="mb-4 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                    <h3 className="truncate text-base font-semibold">{result.video}</h3>
                    <p className="text-xs text-muted-foreground">
                      {result.frame_count} frames - {result.processing_seconds}s
                    </p>
                  </div>

                  <p className="mb-4 rounded-md border border-border bg-background p-3 text-sm">
                    <span className="font-medium">Neutral:</span> {result.neutral}
                  </p>

                  <dl className="grid gap-3 sm:grid-cols-2">
                    <div className="rounded-md border border-border bg-background p-3">
                      <dt className="text-xs font-medium text-muted-foreground">Formal</dt>
                      <dd className="mt-1 text-sm">{result.formal}</dd>
                    </div>
                    <div className="rounded-md border border-border bg-background p-3">
                      <dt className="text-xs font-medium text-muted-foreground">Sarcastic</dt>
                      <dd className="mt-1 text-sm">{result.sarcastic}</dd>
                    </div>
                    <div className="rounded-md border border-border bg-background p-3">
                      <dt className="text-xs font-medium text-muted-foreground">Humorous-Tech</dt>
                      <dd className="mt-1 text-sm">{result.humorous_tech}</dd>
                    </div>
                    <div className="rounded-md border border-border bg-background p-3">
                      <dt className="text-xs font-medium text-muted-foreground">Humorous-Non-Tech</dt>
                      <dd className="mt-1 text-sm">{result.humorous_non_tech}</dd>
                    </div>
                  </dl>
                </article>
              ))}
            </div>

            {response.errors.length > 0 && (
              <div className="rounded-lg border border-destructive bg-card p-5">
                <h3 className="text-base font-semibold text-destructive">Processing errors</h3>
                <ul className="mt-3 space-y-2 text-sm">
                  {response.errors.map((item) => (
                    <li key={`${item.video}-${item.error}`}>
                      <span className="font-medium">{item.video}:</span> {item.error}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}
      </main>
    </div>
  );
}

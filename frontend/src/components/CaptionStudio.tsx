import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BookOpenText,
  CheckCircle2,
  Clapperboard,
  Cpu,
  FileVideo,
  Film,
  Flame,
  Link2,
  Loader2,
  PartyPopper,
  Sparkles,
  Upload,
  UploadCloud,
  Wand2,
  X,
} from "lucide-react";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Tabs, TabsList, TabsTrigger } from "./ui/tabs";
import { cn } from "@/lib/utils";

const ACCEPTED_VIDEO_TYPES = ["video/mp4", "video/webm", "video/quicktime", "video/x-matroska"];
const ACCEPTED_VIDEO_EXTENSIONS = [".mp4", ".webm", ".mov", ".mkv"];
const API_BASE_URL = (
  (import.meta.env.VITE_BACKEND_URL as string | undefined) ?? "http://localhost:8000"
).replace(/\/$/, "");

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
  const [isDragging, setIsDragging] = useState(false);

  const totalQueued = useMemo(
    () => files.length + urlQueue.length,
    [files.length, urlQueue.length],
  );
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

  const addFiles = (incoming: File[]) => {
    if (!incoming.length) return;

    const validFiles = incoming.filter(isAcceptedVideo);
    if (validFiles.length !== incoming.length) {
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
  };

  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(event.target.files ?? []);
    addFiles(selected);
    event.target.value = "";
  };

  const handleDrop = (event: React.DragEvent<HTMLLabelElement>) => {
    event.preventDefault();
    setIsDragging(false);
    addFiles(Array.from(event.dataTransfer.files ?? []));
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
      <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
        <div className="absolute -top-32 left-1/2 h-96 w-[64rem] -translate-x-1/2 rounded-full bg-primary/10 blur-3xl" />
        <div className="absolute bottom-0 right-0 h-72 w-72 rounded-full bg-chart-2/10 blur-3xl" />
      </div>

      <main className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-4 py-10 sm:px-6 lg:px-8">
        <header className="space-y-4">
          <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card/60 px-3 py-1 text-xs font-medium text-muted-foreground shadow-sm backdrop-blur">
            <Sparkles className="size-3.5 text-primary" />
            AI-Powered Captioning
          </div>
          <h1 className="flex items-center gap-3 text-3xl font-semibold tracking-tight sm:text-4xl">
            <span className="flex size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm sm:size-11">
              <Clapperboard className="size-5 sm:size-6" />
            </span>
            AI Video Captioning Studio
          </h1>
          <p className="max-w-3xl text-sm text-muted-foreground sm:text-base">
            Queue videos from your device or direct links, then run the Python AI pipeline to
            generate formal, sarcastic, humorous-tech, and humorous-non-tech captions.
          </p>
        </header>

        <section className="grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
          <Card className="border-border/80 shadow-sm">
            <CardContent className="p-5 sm:p-6">
              <Tabs value={mode} onValueChange={(value) => setMode(value as "local" | "url")}>
                <TabsList className="mb-5">
                  <TabsTrigger value="local" className="gap-1.5">
                    <Upload className="size-3.5" />
                    Local upload
                  </TabsTrigger>
                  <TabsTrigger value="url" className="gap-1.5">
                    <Link2 className="size-3.5" />
                    Paste URL
                  </TabsTrigger>
                </TabsList>
              </Tabs>

              {mode === "local" ? (
                <div className="space-y-4">
                  <label
                    htmlFor="local-video-upload"
                    onDragOver={(event) => {
                      event.preventDefault();
                      setIsDragging(true);
                    }}
                    onDragLeave={() => setIsDragging(false)}
                    onDrop={handleDrop}
                    className={cn(
                      "flex min-h-44 cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-6 text-center transition-all",
                      isDragging
                        ? "border-primary bg-primary/5 scale-[1.01]"
                        : "border-input bg-background hover:border-primary/50 hover:bg-accent",
                    )}
                  >
                    <span
                      className={cn(
                        "flex size-12 items-center justify-center rounded-full bg-secondary transition-colors",
                        isDragging && "bg-primary/10 text-primary",
                      )}
                    >
                      <UploadCloud className="size-6" />
                    </span>
                    <span className="text-sm font-medium">Drop videos here or click to browse</span>
                    <span className="text-xs text-muted-foreground">
                      Accepted: mp4, webm, mov, mkv
                    </span>
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
                          className="flex items-center justify-between gap-3 rounded-md border border-border bg-background px-3 py-2.5 transition-colors hover:border-primary/30"
                        >
                          <div className="flex min-w-0 items-center gap-2.5">
                            <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
                              <FileVideo className="size-4" />
                            </span>
                            <div className="min-w-0">
                              <p className="truncate text-sm font-medium">{file.name}</p>
                              <p className="text-xs text-muted-foreground">
                                {file.sizeMb} MB · {file.type || "video"}
                              </p>
                            </div>
                          </div>
                          <Button
                            onClick={() => removeLocal(file.id)}
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="size-7 shrink-0 text-muted-foreground hover:text-destructive"
                          >
                            <X className="size-4" />
                          </Button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="flex flex-col gap-2 sm:flex-row">
                    <div className="relative w-full">
                      <Link2 className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                      <input
                        type="url"
                        value={urlValue}
                        onChange={(event) => setUrlValue(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") addUrl();
                        }}
                        placeholder="https://example.com/video.mp4"
                        className="h-10 w-full rounded-md border border-input bg-background pl-9 pr-3 text-sm outline-none ring-ring transition focus-visible:ring-2"
                        aria-label="Video URL"
                      />
                    </div>
                    <Button onClick={addUrl} type="button" className="h-10 gap-1.5 sm:shrink-0">
                      <Link2 className="size-3.5" />
                      Add URL
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Use direct downloadable video links. Duplicates are ignored automatically.
                  </p>

                  {urlQueue.length > 0 && (
                    <ul className="space-y-2">
                      {urlQueue.map((url) => (
                        <li
                          key={url}
                          className="flex items-center justify-between gap-3 rounded-md border border-border bg-background px-3 py-2.5 transition-colors hover:border-primary/30"
                        >
                          <div className="flex min-w-0 items-center gap-2.5">
                            <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-secondary text-secondary-foreground">
                              <Link2 className="size-4" />
                            </span>
                            <p className="min-w-0 truncate text-sm">{url}</p>
                          </div>
                          <Button
                            onClick={() => removeUrl(url)}
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="size-7 shrink-0 text-muted-foreground hover:text-destructive"
                          >
                            <X className="size-4" />
                          </Button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="border-border/80 shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-lg">Queue summary</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="rounded-lg border border-border bg-gradient-to-br from-primary/5 to-transparent p-4">
                <p className="text-sm text-muted-foreground">Total queued videos</p>
                <p className="mt-1 text-3xl font-semibold tabular-nums">{totalQueued}</p>
              </div>

              <dl className="space-y-2 text-sm">
                <div className="flex items-center justify-between rounded-md border border-border bg-background px-3 py-2">
                  <dt className="flex items-center gap-2 text-muted-foreground">
                    <Film className="size-3.5" />
                    Local files
                  </dt>
                  <dd className="font-medium tabular-nums">{files.length}</dd>
                </div>
                <div className="flex items-center justify-between rounded-md border border-border bg-background px-3 py-2">
                  <dt className="flex items-center gap-2 text-muted-foreground">
                    <Link2 className="size-3.5" />
                    Video URLs
                  </dt>
                  <dd className="font-medium tabular-nums">{urlQueue.length}</dd>
                </div>
              </dl>

              <div className="rounded-md border border-border bg-background p-3 text-xs">
                {health ? (
                  <p
                    className={cn(
                      "flex items-center gap-1.5",
                      health.api_configured ? "text-muted-foreground" : "text-destructive",
                    )}
                  >
                    <span
                      className={cn(
                        "size-1.5 shrink-0 rounded-full",
                        health.api_configured ? "bg-emerald-500" : "bg-destructive",
                      )}
                    />
                    Backend online.{" "}
                    {health.api_configured ? "Models configured." : "Add API key and model names."}
                  </p>
                ) : (
                  <p className="flex items-center gap-1.5 text-destructive">
                    <span className="size-1.5 shrink-0 rounded-full bg-destructive" />
                    {healthError || "Checking backend..."}
                  </p>
                )}
              </div>

              <Button
                onClick={processQueue}
                disabled={!canProcess}
                type="button"
                className="h-11 w-full gap-2"
              >
                {isProcessing ? (
                  <>
                    <Loader2 className="size-4 animate-spin" />
                    Generating captions...
                  </>
                ) : (
                  <>
                    <Wand2 className="size-4" />
                    Run caption pipeline
                  </>
                )}
              </Button>

              {formError && (
                <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
                  <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                  <span>{formError}</span>
                </div>
              )}
            </CardContent>
          </Card>
        </section>

        {response && (
          <section className="space-y-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <h2 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
                  <Sparkles className="size-5 text-primary" />
                  Generated captions
                </h2>
                <p className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                  <Badge
                    variant="outline"
                    className="gap-1 border-emerald-500/40 text-emerald-600 dark:text-emerald-400"
                  >
                    <CheckCircle2 className="size-3" />
                    {response.stats.succeeded} succeeded
                  </Badge>
                  {response.stats.failed > 0 && (
                    <Badge
                      variant="outline"
                      className="gap-1 border-destructive/40 text-destructive"
                    >
                      <X className="size-3" />
                      {response.stats.failed} failed
                    </Badge>
                  )}
                  <span>in {response.stats.processing_seconds}s</span>
                </p>
              </div>
              <p className="truncate text-xs text-muted-foreground">
                Saved to {response.output_file}
              </p>
            </div>

            <div className="grid gap-4">
              {response.results.map((result) => (
                <Card key={result.video} className="border-border/80 shadow-sm">
                  <CardContent className="p-5">
                    <div className="mb-4 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                      <h3 className="flex items-center gap-2 truncate text-base font-semibold">
                        <FileVideo className="size-4 shrink-0 text-muted-foreground" />
                        {result.video}
                      </h3>
                      <p className="text-xs text-muted-foreground">
                        {result.frame_count} frames · {result.processing_seconds}s
                      </p>
                    </div>

                    <div className="mb-4 rounded-md border border-border bg-muted/40 p-3 text-sm">
                      <span className="font-medium">Neutral:</span> {result.neutral}
                    </div>

                    <dl className="grid gap-3 sm:grid-cols-2">
                      <div className="rounded-md border border-blue-500/20 bg-blue-500/5 p-3">
                        <dt className="flex items-center gap-1.5 text-xs font-medium text-blue-600 dark:text-blue-400">
                          <BookOpenText className="size-3.5" />
                          Formal
                        </dt>
                        <dd className="mt-1 text-sm">{result.formal}</dd>
                      </div>
                      <div className="rounded-md border border-amber-500/20 bg-amber-500/5 p-3">
                        <dt className="flex items-center gap-1.5 text-xs font-medium text-amber-600 dark:text-amber-400">
                          <Flame className="size-3.5" />
                          Sarcastic
                        </dt>
                        <dd className="mt-1 text-sm">{result.sarcastic}</dd>
                      </div>
                      <div className="rounded-md border border-violet-500/20 bg-violet-500/5 p-3">
                        <dt className="flex items-center gap-1.5 text-xs font-medium text-violet-600 dark:text-violet-400">
                          <Cpu className="size-3.5" />
                          Humorous-Tech
                        </dt>
                        <dd className="mt-1 text-sm">{result.humorous_tech}</dd>
                      </div>
                      <div className="rounded-md border border-pink-500/20 bg-pink-500/5 p-3">
                        <dt className="flex items-center gap-1.5 text-xs font-medium text-pink-600 dark:text-pink-400">
                          <PartyPopper className="size-3.5" />
                          Humorous-Non-Tech
                        </dt>
                        <dd className="mt-1 text-sm">{result.humorous_non_tech}</dd>
                      </div>
                    </dl>
                  </CardContent>
                </Card>
              ))}
            </div>

            {response.errors.length > 0 && (
              <Card className="border-destructive/40">
                <CardHeader className="pb-3">
                  <CardTitle className="flex items-center gap-2 text-base text-destructive">
                    <AlertTriangle className="size-4" />
                    Processing errors
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="space-y-2 text-sm">
                    {response.errors.map((item) => (
                      <li key={`${item.video}-${item.error}`}>
                        <span className="font-medium">{item.video}:</span> {item.error}
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}
          </section>
        )}
      </main>
    </div>
  );
}

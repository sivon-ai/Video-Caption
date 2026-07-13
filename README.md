# AI Video Captioning Studio

AI Video Captioning Studio is a full-stack project that generates four styled captions for each video:

- Formal
- Sarcastic
- Humorous-Tech
- Humorous-Non-Tech

The frontend lets users upload local videos or add direct video URLs, preview the active video, monitor queue/backend status, and run the caption pipeline. The Python backend extracts representative frames, asks a vision-language model for a factual description and neutral caption, then rewrites that caption into all four styles.

## Latest Features

- Local video upload with drag-and-drop support.
- Direct video URL queueing with duplicate prevention.
- Video preview panel for uploaded files and URL videos.
- Compact queue counters for total videos, local files, and URLs.
- Backend health/status badge in the main UI.
- Single `Run caption pipeline` action in the upload workflow.
- Generated caption results with success/failure counts and saved output path.
- FastAPI backend with `/health` and `/api/captions/process`.
- CLI batch mode through `python app.py`.
- Dockerized Linux backend image that runs evaluator batch mode by default.
- Docker API mode remains available with the `api` command.
- Docker submission tag: `22102005/video-caption:evaluator-20260713`.
- Docker Hub page: https://hub.docker.com/r/22102005/video-caption.

## What The Project Does

1. Accepts videos from the web UI or from `backend/videos`.
2. Extracts representative frames instead of processing every frame.
3. Removes duplicate-looking frames and skips very blurry, very dark, or overexposed frames.
4. Sends sampled frames to a vision model for a factual description and neutral caption.
5. Captures an optional chronological scene timeline.
6. Rewrites the neutral caption into four required caption styles in one model call.
7. Validates model JSON with Pydantic.
8. Saves caption output as JSON in `backend/outputs`.
9. Logs processing details and errors in `backend/logs`.

No dataset is required for normal usage. You only need videos, an API key, a vision-capable model, and a text model.

## Project Structure

```text
Video Caption/
|-- Dockerfile
|-- .dockerignore
|-- README.md
|-- backend/
|   |-- app.py
|   |-- api.py
|   |-- evaluator.py
|   |-- config.py
|   |-- requirements.txt
|   |-- .env.example
|   |-- videos/
|   |-- outputs/
|   |-- logs/
|   |-- prompts/
|   |   |-- vision_prompt.txt
|   |   `-- rewrite_prompt.txt
|   `-- src/
|       |-- frame_extractor.py
|       |-- video_processor.py
|       |-- fireworks_client.py
|       |-- caption_generator.py
|       |-- style_generator.py
|       |-- validator.py
|       |-- models.py
|       `-- utils.py
`-- frontend/
    |-- package.json
    |-- vite.config.ts
    `-- src/
        |-- components/
        |   `-- CaptionStudio.tsx
        `-- routes/
            `-- index.tsx
```

## Backend

- `backend/app.py`: CLI entry point. Processes every video in `backend/videos`.
- `backend/api.py`: FastAPI service used by the frontend.
- `backend/evaluator.py`: Container entry point for evaluator jobs. Reads `/input/tasks.json`, writes `/output/results.json`, and exits.
- `backend/config.py`: Loads `.env` settings, model names, API key, limits, CORS origins, and folder paths.
- `backend/src/frame_extractor.py`: Samples representative frames with OpenCV.
- `backend/src/fireworks_client.py`: OpenAI-compatible chat completions client with retries and timeouts.
- `backend/src/caption_generator.py`: Generates factual video descriptions and neutral captions.
- `backend/src/style_generator.py`: Generates all four styled captions in one text-model request.
- `backend/src/validator.py`: Extracts and validates strict JSON responses.
- `backend/src/video_processor.py`: Orchestrates processing, logging, errors, stats, and output writing.

## Frontend

The frontend route renders `CaptionStudio`, which supports:

- Local upload and paste-URL modes.
- Active video preview with browser video controls.
- Queue count badges for local files and URLs.
- Backend readiness badge from `GET /health`.
- One primary `Run caption pipeline` button.
- Generated caption cards for each processed video.

Set `VITE_BACKEND_URL` if the backend is not running on `http://localhost:8000`.

For a Vercel deployment, `VITE_BACKEND_URL` must be an HTTPS URL. Browsers block
requests from `https://video-caption-gold.vercel.app` to a plain `http://`
backend as mixed content, even when the backend itself is running. Put the
FastAPI service behind HTTPS through a domain with TLS, a reverse proxy such as
Caddy or Nginx with Let's Encrypt, or a hosting provider that gives the backend
an HTTPS URL, then update the Vercel environment variable.

## Setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `backend/.env`:

```env
API_KEY=your_api_key
API_BASE_URL=https://api.fireworks.ai/inference/v1
VISION_MODEL=your_vision_model
TEXT_MODEL=your_text_model
REQUEST_TIMEOUT=45
MAX_RETRIES=2
MAX_WORKERS=2
MAX_URL_DOWNLOAD_WORKERS=4
MIN_FRAMES=2
MAX_FRAMES=10
JPEG_QUALITY=68
MAX_FRAME_EDGE=640
MIN_FRAME_EDGE=448
MAX_VIDEO_SECONDS=65
FAST_STYLE_MAX_SECONDS=8
```

The backend expects an OpenAI-compatible chat completions API that supports image inputs through `image_url` message content.
For short uploads, frame sampling is adaptive: clips up to 8 seconds use 2 frames,
up to 15 seconds use 4, up to 20 seconds use 6, up to 35 seconds use 8, and
longer clips up to about one minute use 10. Clips up to `FAST_STYLE_MAX_SECONDS`
use one vision-model request and local style rewrites, avoiding the second model
call so evaluation runtime stays low.

For multi-video or multi-URL batches, `MAX_WORKERS` controls how many videos can
be captioned in parallel. Raise it only as far as your model provider rate limits
allow. `MAX_URL_DOWNLOAD_WORKERS` controls URL downloads separately, so several
linked videos can be fetched at once without increasing model API concurrency.

### Frontend

```bash
cd frontend
npm install
```

## Running Locally

Start the backend API:

```bash
cd backend
uvicorn api:app --reload --host 127.0.0.1 --port 8000
```

Start the frontend:

```bash
cd frontend
npm run dev
```

Open the frontend URL shown by Vite, usually:

```text
http://localhost:5173
```

## Docker

The Docker image runs evaluator batch mode by default. It reads configuration from environment variables instead of copying `.env` into the image.

Submission image tag:

```text
22102005/video-caption:evaluator-20260713
```

Docker Hub page: https://hub.docker.com/r/22102005/video-caption

Build locally:

```bash
docker build -t 22102005/video-caption:evaluator-20260713 .
```

Run the evaluator locally from Docker:

```bash
docker run --rm \
  -e API_KEY="$API_KEY" \
  -e API_BASE_URL="https://api.fireworks.ai/inference/v1" \
  -e VISION_MODEL="$VISION_MODEL" \
  -e TEXT_MODEL="$TEXT_MODEL" \
  -v "$(pwd)/input:/input:ro" \
  -v "$(pwd)/output:/output" \
  22102005/video-caption:evaluator-20260713
```

The evaluator reads `${TASK_INPUT_PATH:-/input/tasks.json}` and writes `/output/results.json` unless `TASK_OUTPUT_PATH`, `RESULT_OUTPUT_PATH`, or `OUTPUT_PATH` is set.

Run the API locally from Docker:

```bash
docker run --rm \
  -p 8000:8000 \
  -e API_KEY="$API_KEY" \
  -e API_BASE_URL="https://api.fireworks.ai/inference/v1" \
  -e VISION_MODEL="$VISION_MODEL" \
  -e TEXT_MODEL="$TEXT_MODEL" \
  22102005/video-caption:evaluator-20260713 api
```

Run batch mode with mounted folders:

```bash
docker run --rm \
  -e API_KEY="$API_KEY" \
  -e API_BASE_URL="https://api.fireworks.ai/inference/v1" \
  -e VISION_MODEL="$VISION_MODEL" \
  -e TEXT_MODEL="$TEXT_MODEL" \
  -v "$(pwd)/backend/videos:/app/videos" \
  -v "$(pwd)/backend/outputs:/app/outputs" \
  22102005/video-caption:evaluator-20260713 batch
```

Pull the public image:

```bash
docker pull 22102005/video-caption:evaluator-20260713
```

Push the image:

```bash
docker login
docker push 22102005/video-caption:evaluator-20260713
```

The image startup is:

```json
{
  "ENTRYPOINT": ["docker-entrypoint.sh"],
  "CMD": ["eval"]
}
```

For evaluator submissions, keep the default command so the container reads `/input/tasks.json`, writes `/output/results.json`, and exits. For Render or another web service, pass `api` so the service listens on `${PORT:-8000}`. The legacy folder batch mode remains available with `batch`; with no videos mounted, it writes an empty JSON array to `/app/outputs/captions.json`.

## Batch Mode

For CLI processing, place videos in `backend/videos`, then run:

```bash
cd backend
python app.py
```

The batch output is saved to:

```text
backend/outputs/captions.json
```

## API Endpoints

### `GET /health`

Returns service status and whether API settings are configured.

### `POST /api/captions/process`

Multipart fields:

- `files`: one or more uploaded video files
- `urls`: one or more direct downloadable video URLs

Returns generated captions, processing statistics, per-video errors, and the output JSON file path.

## Output Format

```json
[
  {
    "video": "example.mp4",
    "neutral": "A person walks across a room while holding a bag.",
    "factual_description": "A person moves through an indoor room carrying a bag.",
    "scene_timeline": ["The person enters the frame.", "The person walks across the room."],
    "formal": "A person walks across a room while holding a bag.",
    "sarcastic": "A person heroically completes the advanced mission of walking across a room with a bag.",
    "humorous_tech": "A person runs walkAcrossRoom() with bag mode enabled.",
    "humorous_non_tech": "A person crosses the room with a bag like they have somewhere important to be.",
    "frame_count": 12,
    "processing_seconds": 8.42
  }
]
```

## Submission Checklist

- Docker builds: verified.
- Docker runs: verified.
- API key via environment variable: implemented and verified.
- `requirements.txt` complete: verified during Docker build.
- No Windows paths required for setup/runtime: implemented.
- Works on Linux: verified with Docker Linux image.
- Produces output JSON: verified.
- Docker image tag: `22102005/video-caption:evaluator-20260713`.
- Docker Hub page: https://hub.docker.com/r/22102005/video-caption.
- Correct image tag: `22102005/video-caption:evaluator-20260713`.
- ENTRYPOINT works: `["docker-entrypoint.sh"]`.
- Evaluator startup works through default `CMD ["eval"]`.
- Render web startup works with the explicit `api` command.

## Implementation Checklist

- Python 3.11+ backend.
- FastAPI backend endpoints.
- React/TanStack frontend interface.
- OpenCV frame extraction.
- FFmpeg/MoviePy dependency support.
- Fireworks/OpenAI-compatible API support.
- `.env` configuration with `.env.example`.
- Representative frame sampling.
- Duplicate frame removal.
- Basic frame quality filtering.
- Scene timeline metadata.
- Factual vision prompt.
- One neutral caption.
- One style-generation request for all four captions.
- JSON-only validation with Pydantic.
- API retries, timeouts, and retryable rate-limit/server-error handling.
- Logging with Loguru.
- Configurable parallel workers through `MAX_WORKERS`.
- CLI batch mode.
- Docker batch image.
- Docker evaluator mode.
- Docker API web service mode for Render.
- Public Docker Hub image.

## Requirement Before Real Captioning

Real caption generation requires valid values in `backend/.env` or environment variables:

- `API_KEY`
- `VISION_MODEL`
- `TEXT_MODEL`

Without these, `/health` still works, but processing returns a configuration error instead of calling a model.

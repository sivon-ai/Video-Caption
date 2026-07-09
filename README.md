# AI Video Captioning Studio

AI Video Captioning Studio is a full-stack hackathon project that generates four styled captions for each video:

- Formal
- Sarcastic
- Humorous-Tech
- Humorous-Non-Tech

The frontend lets a user queue local video files or direct video URLs. The Python backend extracts representative frames, sends those frames to a vision-language model for a factual scene description and one neutral caption, then sends one text-generation request to rewrite that neutral caption into all four required styles.

## What The Project Does

1. Accepts videos from the web UI or from `backend/videos`.
2. Extracts about 8 to 12 representative frames instead of processing every frame.
3. Removes duplicate-looking frames and skips very blurry, very dark, or overexposed frames.
4. Asks a vision model for a factual description and neutral caption.
5. Captures an optional chronological scene timeline from visible events.
6. Rewrites the neutral caption into four styles in one model call.
7. Validates model JSON with Pydantic.
8. Saves caption output as JSON in `backend/outputs`.
9. Logs processing details and errors in `backend/logs`.

No dataset is required for normal usage. You only need videos, an API key, a vision-capable model, and a text model. A dataset is only needed if you want to fine-tune models or benchmark quality.

## File Architecture

```text
Video Caption/
├── README.md
├── backend/
│   ├── app.py
│   ├── api.py
│   ├── config.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── README.md
│   ├── videos/
│   ├── outputs/
│   ├── logs/
│   ├── prompts/
│   │   ├── vision_prompt.txt
│   │   └── rewrite_prompt.txt
│   └── src/
│       ├── frame_extractor.py
│       ├── video_processor.py
│       ├── fireworks_client.py
│       ├── caption_generator.py
│       ├── style_generator.py
│       ├── validator.py
│       ├── models.py
│       └── utils.py
└── frontend/
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── components/
        │   └── CaptionStudio.tsx
        └── routes/
            └── index.tsx
```

## Backend Modules

- `backend/app.py`: CLI entry point. Running `python app.py` processes every video in `backend/videos`.
- `backend/api.py`: FastAPI service used by the frontend. Exposes `/health` and `/api/captions/process`.
- `backend/config.py`: Loads `.env` settings, model names, API key, limits, CORS origins, and folder paths.
- `backend/src/frame_extractor.py`: Uses OpenCV to sample representative frames, remove duplicates, and skip low-quality frames.
- `backend/src/fireworks_client.py`: OpenAI-compatible chat completions client with retries, timeouts, API latency tracking, and token usage capture.
- `backend/src/caption_generator.py`: Sends sampled frames to the vision model and validates the factual response.
- `backend/src/style_generator.py`: Converts the neutral caption into all four caption styles in one text-model request.
- `backend/src/validator.py`: Extracts and validates strict JSON responses.
- `backend/src/video_processor.py`: Orchestrates processing, optional parallel workers, logging, progress display, error collection, and output writing.

## Frontend Integration

The frontend route renders `CaptionStudio`, which:

- Accepts local files and direct video URLs.
- Sends queued videos to `POST http://localhost:8000/api/captions/process` as `FormData`.
- Checks backend status with `GET http://localhost:8000/health`.
- Shows processing state, API errors, saved output path, and generated captions.

Set `VITE_BACKEND_URL` in the frontend environment if your backend is not running on `http://localhost:8000`.

## Setup

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Fill `backend/.env`:

```env
API_KEY=your_api_key
API_BASE_URL=https://api.fireworks.ai/inference/v1
VISION_MODEL=your_vision_model
TEXT_MODEL=your_text_model
MAX_WORKERS=1
```

The backend expects an OpenAI-compatible chat completions API that supports image inputs through `image_url` message content.

### Frontend

```bash
cd frontend
npm install
```

## Running The Project

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

Returns service status and whether API settings are ready.

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
    "formal": "A person walks across a room while holding a bag.",
    "sarcastic": "A person heroically completes the advanced mission of walking across a room with a bag.",
    "humorous_tech": "A person runs walkAcrossRoom() with bag mode enabled.",
    "humorous_non_tech": "A person crosses the room with a bag like they have somewhere important to be."
  }
]
```

## Implementation Checklist

- Python 3.11+ backend: implemented.
- OpenCV frame extraction: implemented.
- FFmpeg/MoviePy dependency support: included in requirements.
- Requests, python-dotenv, tqdm, pydantic, and loguru: included.
- Fireworks/OpenAI-compatible API support: implemented through chat completions.
- `.env` configuration: implemented with `.env.example`.
- Representative frame sampling: implemented.
- Duplicate frame removal: implemented.
- Basic frame quality filtering: implemented.
- Scene timeline metadata: implemented in API responses.
- Factual vision prompt: implemented.
- One neutral caption: implemented.
- One style-generation request for all four captions: implemented.
- JSON-only validation: implemented with Pydantic.
- API retries, timeouts, and retryable rate-limit/server-error handling: implemented.
- Logging: implemented with Loguru.
- Configurable parallel workers: implemented with `MAX_WORKERS`, defaulting to `1` for rate-limit safety.
- Frontend connection: implemented with FastAPI endpoints.
- CLI batch mode: implemented with `python app.py`.

## Current Requirement Before Real Captioning

The code is wired and runnable, but real caption generation needs valid values in `backend/.env`:

- `API_KEY`
- `VISION_MODEL`
- `TEXT_MODEL`

Without these, `/health` still works, but processing returns a configuration error instead of calling a model.

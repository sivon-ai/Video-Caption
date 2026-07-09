# AI Video Captioning Backend

Python backend for generating four caption styles per video:

- Formal
- Sarcastic
- Humorous-Tech
- Humorous-Non-Tech

The pipeline extracts representative frames, asks a vision-language model for one factual description and neutral caption, then uses one text-generation request to rewrite that caption into all four styles.
API responses also include a factual scene timeline when the vision model returns one.

## Setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Fill `backend/.env`:

```env
API_KEY=your_key
API_BASE_URL=https://api.fireworks.ai/inference/v1
VISION_MODEL=your_vision_model
TEXT_MODEL=your_text_model
MAX_WORKERS=1
```

Any OpenAI-compatible chat completions endpoint should work if it accepts image inputs in `image_url` message content.

## Run API for the Frontend

```bash
cd backend
uvicorn api:app --reload --host 127.0.0.1 --port 8000
```

Frontend default backend URL is `http://localhost:8000`. Override it with:

```env
VITE_BACKEND_URL=http://localhost:8000
```

## Run Batch Mode

Put videos in `backend/videos`, then run:

```bash
cd backend
python app.py
```

Output is written to:

```text
backend/outputs/captions.json
```

## API

### `GET /health`

Returns service status and whether API settings are configured.

### `POST /api/captions/process`

Multipart form fields:

- `files`: one or more uploaded video files
- `urls`: one or more direct downloadable video URLs

Response includes full metadata plus `outputs/captions-<batch>.json`.

`MAX_WORKERS` can be raised for parallel processing, but `1` is the safest default for rate-limited model APIs.

## Example Output

```json
[
  {
    "video": "dog.mp4",
    "formal": "A dog walks across a grassy area.",
    "sarcastic": "A dog bravely completes the ancient quest of walking on grass.",
    "humorous_tech": "A dog executes walk() across the grass with zero visible errors.",
    "humorous_non_tech": "A dog takes a casual stroll like it owns the lawn."
  }
]
```

## Do You Need a Dataset?

No dataset is required for inference. You only need:

- Video files to process
- A vision-capable model
- A text model
- An API key for an OpenAI-compatible provider such as Fireworks AI

Use a dataset only if you plan to fine-tune or benchmark caption quality.

# Agentic Trip Planner - Frontend

Next.js web application for the Agentic Trip Planner.

## Development

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

## Features

- Natural language trip request input
- Real-time profile extraction via Gemini API
- Display extracted trip details (destination, dates, budget, travelers, interests)
- Clarification questions for incomplete profiles
- Responsive Tailwind CSS design

## API Integration

The frontend connects to the FastAPI backend at `http://localhost:8000`.

Make sure the backend is running before starting the frontend:

```bash
cd ../backend
source ../venv/bin/activate
uvicorn app.main:app --reload
```

## Tech Stack

- Next.js 15 (App Router)
- TypeScript
- Tailwind CSS
- React 19

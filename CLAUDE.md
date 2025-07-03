# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a LINE Bot with AI integration - a FastAPI-based web application that serves as a LINE chatbot powered by OpenAI GPT-4 and backed by Supabase for data persistence.

**Tech Stack**: Python 3.12+, FastAPI, LangChain, OpenAI GPT-4, Supabase, LINE Messaging API SDK v3

## Development Commands

```bash
# Install dependencies
uv sync

# Run development server
uv run uvicorn app.main:app --reload --port 8000

# Production server
gunicorn app.main:app

# Database management
supabase start          # Start local Supabase instance
supabase db reset       # Reset database with migrations
```

## Architecture

### Core Components
- **`app/main.py`**: FastAPI webhook endpoint (`/api/webhook`) for LINE messages with async processing
- **`app/ai_service.py`**: LangChain integration with OpenAI GPT-4 using thread pool execution
- **`app/message_service.py`**: Message history retrieval and persistence with Supabase
- **`supabase/migrations/`**: Database schema with users, groups, group_members, messages, and money_requests tables

### Key Patterns
- **Async/await throughout**: Non-blocking operations with `asyncio.gather()` for parallel execution
- **Service layer architecture**: Singleton pattern for service instances with dependency injection
- **Event-driven processing**: LINE webhook events trigger async message processing with background tasks

### Special Features
- **Money request detection**: AI-powered parsing to detect payment requests and set reminders
- **Conversation context**: Maintains chat history for contextual AI responses
- **Full message logging**: Complete LINE webhook payload storage in database

## Environment Variables Required
- `LINE_CHANNEL_SECRET` / `LINE_CHANNEL_ACCESS_TOKEN`: LINE bot credentials
- `OPENAI_API_KEY`: OpenAI API key for GPT-4
- `SUPABASE_URL` / `SUPABASE_ANON_KEY`: Supabase database connection

## Database Schema
Tables: `users`, `groups`, `group_members`, `messages`, `money_requests`
- Message history stored with full LINE webhook payloads
- Many-to-many relationship between users and groups
- Money requests tracked separately for reminder functionality
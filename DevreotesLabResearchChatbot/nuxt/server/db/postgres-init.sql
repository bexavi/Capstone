-- Neon / Postgres schema for Nuxt chat persistence.
-- Run this manually in Neon SQL Editor (or psql).
-- Keep this OUTSIDE server/db/migrations so NuxtHub sqlite migrations do not execute it.

CREATE TABLE IF NOT EXISTS users (
  id text PRIMARY KEY,
  email text NOT NULL,
  name text NOT NULL,
  avatar text NOT NULL,
  username text NOT NULL,
  provider text NOT NULL,
  provider_id text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS users_provider_id_idx ON users(provider, provider_id);

CREATE TABLE IF NOT EXISTS chats (
  id text PRIMARY KEY,
  title text,
  summary text,
  user_id text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chats_user_id_idx ON chats(user_id);

-- If chats existed without summary: ALTER TABLE chats ADD COLUMN IF NOT EXISTS summary text;

CREATE TABLE IF NOT EXISTS messages (
  id text PRIMARY KEY,
  chat_id text NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
  role text NOT NULL,
  parts jsonb,
  devreotes_trace jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS messages_chat_id_idx ON messages(chat_id);


-- Run once in Neon if `messages.parts` / `devreotes_trace` were created as `text`.
-- Fixes: "t.parts.filter is not a function" (UI expects parsed JSON arrays).

ALTER TABLE messages
  ALTER COLUMN parts TYPE jsonb USING (
    CASE
      WHEN parts IS NULL THEN NULL
      ELSE parts::jsonb
    END
  );

ALTER TABLE messages
  ALTER COLUMN devreotes_trace TYPE jsonb USING (
    CASE
      WHEN devreotes_trace IS NULL THEN NULL
      ELSE devreotes_trace::jsonb
    END
  );

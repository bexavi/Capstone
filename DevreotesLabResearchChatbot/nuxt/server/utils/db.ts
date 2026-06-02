import { drizzle } from 'drizzle-orm/node-postgres'
import { drizzle as drizzleLibsql } from 'drizzle-orm/libsql'
import { Pool } from 'pg'
import { createClient } from '@libsql/client'
import { dirname, resolve } from 'node:path'
import { mkdirSync } from 'node:fs'
import * as pgSchema from '../db/schema.pg'
import * as sqliteSchema from '../db/schema'

const databaseUrl = process.env.DATABASE_URL?.trim()
const isProduction = process.env.NODE_ENV === 'production'

let db: unknown
let schema: unknown

if (databaseUrl) {
  const pool = new Pool({
    connectionString: databaseUrl,
    // Required by Neon and other managed Postgres providers.
    ssl: { rejectUnauthorized: false }
  })
  db = drizzle(pool, { schema: pgSchema })
  schema = pgSchema
} else if (!isProduction) {
  // Local demo/dev fallback: plain sqlite file under .data/db.
  const sqlitePath = resolve(process.cwd(), '.data', 'db', 'sqlite.db')
  mkdirSync(dirname(sqlitePath), { recursive: true })
  const client = createClient({ url: `file:${sqlitePath}` })
  db = drizzleLibsql(client, { schema: sqliteSchema })
  schema = sqliteSchema
} else {
  throw new Error('DATABASE_URL is required in production')
}

export { db, schema }


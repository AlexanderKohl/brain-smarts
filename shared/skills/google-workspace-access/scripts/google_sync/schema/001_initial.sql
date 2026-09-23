-- Local Gmail / Google Tasks sync schema (SQLite)

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS google_connections (
    id TEXT PRIMARY KEY,
    account_alias TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL,
    reconnect_required INTEGER NOT NULL DEFAULT 0,
    last_auth_error TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_locks (
    lock_key TEXT PRIMARY KEY,
    holder TEXT,
    acquired_at TEXT,
    expires_at TEXT
);

CREATE TABLE IF NOT EXISTS gmail_sync_state (
    google_account_id TEXT PRIMARY KEY,
    last_history_id TEXT,
    watch_expiration TEXT,
    watch_resource_id TEXT,
    received_history_id TEXT,
    initial_sync_completed_at TEXT,
    last_incremental_sync_started_at TEXT,
    last_incremental_sync_completed_at TEXT,
    last_successful_sync_at TEXT,
    last_reconciliation_at TEXT,
    last_watch_renewed_at TEXT,
    last_sync_error TEXT,
    sync_status TEXT NOT NULL DEFAULT 'idle',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (google_account_id) REFERENCES google_connections(id)
);

CREATE TABLE IF NOT EXISTS gmail_threads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    google_account_id TEXT NOT NULL,
    gmail_thread_id TEXT NOT NULL,
    subject TEXT,
    snippet TEXT,
    last_message_internal_date INTEGER,
    message_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_synced_at TEXT,
    UNIQUE (google_account_id, gmail_thread_id),
    FOREIGN KEY (google_account_id) REFERENCES google_connections(id)
);

CREATE TABLE IF NOT EXISTS gmail_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    google_account_id TEXT NOT NULL,
    gmail_message_id TEXT NOT NULL,
    gmail_thread_id TEXT NOT NULL,
    history_id TEXT,
    internal_date INTEGER,
    sender_name TEXT,
    sender_email TEXT,
    recipients_json TEXT,
    cc_json TEXT,
    subject TEXT,
    snippet TEXT,
    label_ids_json TEXT,
    is_unread INTEGER NOT NULL DEFAULT 0,
    is_starred INTEGER NOT NULL DEFAULT 0,
    is_important INTEGER NOT NULL DEFAULT 0,
    has_attachments INTEGER NOT NULL DEFAULT 0,
    size_estimate INTEGER,
    mime_type TEXT,
    body_cached INTEGER NOT NULL DEFAULT 0,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_synced_at TEXT,
    UNIQUE (google_account_id, gmail_message_id),
    FOREIGN KEY (google_account_id) REFERENCES google_connections(id)
);

CREATE INDEX IF NOT EXISTS idx_gmail_messages_account_date
    ON gmail_messages (google_account_id, internal_date DESC);
CREATE INDEX IF NOT EXISTS idx_gmail_messages_account_thread
    ON gmail_messages (google_account_id, gmail_thread_id);
CREATE INDEX IF NOT EXISTS idx_gmail_messages_sender
    ON gmail_messages (google_account_id, sender_email);

CREATE TABLE IF NOT EXISTS gmail_message_bodies (
    google_account_id TEXT NOT NULL,
    gmail_message_id TEXT NOT NULL,
    text_body TEXT,
    html_body TEXT,
    content_hash TEXT,
    fetched_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (google_account_id, gmail_message_id),
    FOREIGN KEY (google_account_id, gmail_message_id)
        REFERENCES gmail_messages (google_account_id, gmail_message_id)
);

CREATE TABLE IF NOT EXISTS gmail_attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    google_account_id TEXT NOT NULL,
    gmail_message_id TEXT NOT NULL,
    gmail_attachment_id TEXT,
    filename TEXT,
    mime_type TEXT,
    size INTEGER,
    content_id TEXT,
    is_inline INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (google_account_id, gmail_message_id, gmail_attachment_id)
);

CREATE TABLE IF NOT EXISTS gmail_labels (
    google_account_id TEXT NOT NULL,
    label_id TEXT NOT NULL,
    name TEXT,
    label_type TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (google_account_id, label_id)
);

CREATE TABLE IF NOT EXISTS gmail_message_labels (
    google_account_id TEXT NOT NULL,
    gmail_message_id TEXT NOT NULL,
    label_id TEXT NOT NULL,
    PRIMARY KEY (google_account_id, gmail_message_id, label_id)
);

CREATE TABLE IF NOT EXISTS body_fetch_locks (
    google_account_id TEXT NOT NULL,
    gmail_message_id TEXT NOT NULL,
    holder TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    PRIMARY KEY (google_account_id, gmail_message_id)
);

CREATE TABLE IF NOT EXISTS internal_tasks (
    id TEXT PRIMARY KEY,
    google_account_id TEXT,
    title TEXT NOT NULL,
    description TEXT,
    due_at TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    completed_at TEXT,
    completed_source TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (google_account_id) REFERENCES google_connections(id)
);

CREATE INDEX IF NOT EXISTS idx_internal_tasks_status
    ON internal_tasks (status, updated_at DESC);

CREATE TABLE IF NOT EXISTS google_task_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    internal_task_id TEXT NOT NULL,
    google_account_id TEXT NOT NULL,
    google_task_list_id TEXT NOT NULL,
    google_task_id TEXT NOT NULL,
    google_etag TEXT,
    google_status TEXT,
    google_updated_at TEXT,
    google_self_link TEXT,
    google_web_view_link TEXT,
    mapping_status TEXT NOT NULL DEFAULT 'active',
    last_pushed_at TEXT,
    last_pulled_at TEXT,
    last_sync_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (internal_task_id, google_account_id),
    UNIQUE (google_account_id, google_task_list_id, google_task_id),
    FOREIGN KEY (internal_task_id) REFERENCES internal_tasks(id),
    FOREIGN KEY (google_account_id) REFERENCES google_connections(id)
);

CREATE TABLE IF NOT EXISTS google_task_sync_state (
    google_account_id TEXT NOT NULL,
    google_task_list_id TEXT NOT NULL,
    list_title TEXT,
    last_poll_started_at TEXT,
    last_poll_completed_at TEXT,
    last_successful_poll_at TEXT,
    last_updated_min TEXT,
    last_sync_error TEXT,
    sync_status TEXT NOT NULL DEFAULT 'idle',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (google_account_id, google_task_list_id),
    FOREIGN KEY (google_account_id) REFERENCES google_connections(id)
);

CREATE TABLE IF NOT EXISTS sync_jobs (
    id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    google_account_id TEXT,
    dedupe_key TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 8,
    run_after TEXT NOT NULL,
    payload_json TEXT,
    last_error TEXT,
    last_error_category TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sync_jobs_active_dedupe
    ON sync_jobs (dedupe_key)
    WHERE dedupe_key IS NOT NULL AND status IN ('pending', 'running');

CREATE INDEX IF NOT EXISTS idx_sync_jobs_claim
    ON sync_jobs (status, run_after);

CREATE TABLE IF NOT EXISTS sync_outbox (
    id TEXT PRIMARY KEY,
    operation TEXT NOT NULL,
    google_account_id TEXT NOT NULL,
    internal_task_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 8,
    run_after TEXT NOT NULL,
    payload_json TEXT,
    last_error TEXT,
    last_error_category TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (operation, internal_task_id, google_account_id)
);

CREATE INDEX IF NOT EXISTS idx_sync_outbox_claim
    ON sync_outbox (status, run_after);

CREATE TABLE IF NOT EXISTS sync_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    google_account_id TEXT,
    job_id TEXT,
    outbox_id TEXT,
    error_category TEXT NOT NULL,
    error_message TEXT NOT NULL,
    context_json TEXT,
    created_at TEXT NOT NULL
);

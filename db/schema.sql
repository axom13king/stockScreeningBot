-- Supabase (PostgreSQL) schema for stock screening bot
-- Run this in the Supabase SQL editor when setting up the project.

-- スクリーニング条件マスタ(config/screening_conditions.yaml の内容を反映する運用も可)
create table if not exists screening_conditions (
    id bigint generated always as identity primary key,
    name text not null,
    indicator text not null,       -- 例: 'per', 'pbr', 'sma_cross', 'volume_spike'
    operator text not null,        -- 例: '<', '>', '<=', '>='
    threshold numeric,
    enabled boolean not null default true,
    created_at timestamptz not null default now()
);

-- 保有銘柄
create table if not exists holdings (
    id bigint generated always as identity primary key,
    ticker_code text not null,
    ticker_name text,
    buy_price numeric not null,
    buy_date date not null,
    quantity integer not null,
    status text not null default 'open',  -- 'open' | 'closed'
    sell_price numeric,
    sell_date date,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- 日次スクリーニング結果の履歴
create table if not exists screening_history (
    id bigint generated always as identity primary key,
    run_date date not null,
    ticker_code text not null,
    ticker_name text,
    matched_conditions jsonb,
    price numeric,
    notified_at timestamptz
);

-- 通知ログ
create table if not exists notification_log (
    id bigint generated always as identity primary key,
    sent_at timestamptz not null default now(),
    channel text not null default 'telegram',
    message text not null,
    status text not null default 'sent'
);

-- Telegramのポーリング用: 最後に処理したupdate_idを保持(1行のみ想定)
create table if not exists telegram_poll_state (
    id smallint primary key default 1,
    last_update_id bigint not null default 0
);
insert into telegram_poll_state (id, last_update_id)
values (1, 0)
on conflict (id) do nothing;

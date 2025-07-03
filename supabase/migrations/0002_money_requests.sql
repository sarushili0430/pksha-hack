------------------------------------------------------------
-- money_requests テーブル
-- お金の催促リクエストを管理するテーブル
------------------------------------------------------------

create table money_requests (
  id                  uuid primary key default gen_random_uuid(),
  group_id            uuid references groups(id) on delete cascade not null,
  requester_user_id   uuid references users(id) on delete cascade not null,
  amount              integer not null,                    -- 請求金額
  remind_at           timestamptz not null,                -- リマインド送信予定時刻
  created_at          timestamptz not null default now(),  -- 作成日時
  
  -- インデックス用制約
  constraint money_requests_amount_positive check (amount > 0)
);

-- インデックス
create index idx_money_requests_remind_at on money_requests(remind_at);
create index idx_money_requests_group_requester on money_requests(group_id, requester_user_id);
create index idx_money_requests_created_at on money_requests(created_at);

-- コメント
comment on table money_requests is 'お金の催促リクエストを管理するテーブル';
comment on column money_requests.group_id is 'グループID（外部キー）';
comment on column money_requests.requester_user_id is '請求者のユーザーID（外部キー）';
comment on column money_requests.amount is '請求金額（円）';
comment on column money_requests.remind_at is 'リマインド送信予定時刻';
comment on column money_requests.created_at is 'リクエスト作成日時';
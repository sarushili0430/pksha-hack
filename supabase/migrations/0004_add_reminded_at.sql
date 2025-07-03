------------------------------------------------------------
-- money_requests テーブルにリマインダー送信状態を追加
------------------------------------------------------------

-- reminded_at カラムを追加（リマインダー送信日時）
alter table money_requests 
add column reminded_at timestamptz;

-- インデックスを追加
create index idx_money_requests_reminded_at on money_requests(reminded_at);

-- コメント追加
comment on column money_requests.reminded_at is 'リマインダー送信日時（未送信の場合はNULL）';
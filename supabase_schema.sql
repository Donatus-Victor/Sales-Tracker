-- ══════════════════════════════════════════════════════════════
--  SalesTrack Pro — COMPLETE FRESH SCHEMA
--  Run this in Supabase → SQL Editor → New Query
-- ══════════════════════════════════════════════════════════════

-- 1. USERS
create table if not exists users (
  id                text primary key,
  username          text unique not null,
  password_hash     text not null default '',
  role              text not null default 'sales',
  branch            text,
  company_id        text,
  is_active         boolean default true,
  must_set_password boolean default false,
  created_at        timestamptz default now()
);

-- 2. COMPANIES
create table if not exists companies (
  id                    text primary key,
  name                  text not null,
  email                 text,
  phone                 text,
  plan                  text default 'Basic',
  is_active             boolean default true,
  subscription_expires  text,
  created_at            timestamptz default now()
);

-- 3. PRODUCTS
create table if not exists products (
  id          text primary key,
  name        text not null,
  category    text,
  company_id  text,
  created_at  timestamptz default now()
);

-- 4. SELLERS
create table if not exists sellers (
  id          text primary key,
  name        text not null,
  branch      text,
  company_id  text,
  created_at  timestamptz default now()
);

-- 5. SALES
create table if not exists sales (
  id              text primary key,
  date            date not null,
  seller_id       text,
  seller_name     text,
  product_id      text,
  product_name    text,
  branch          text,
  customer_name   text,
  customer_phone  text,
  invoice_no      text,
  opening_stock   integer default 0,
  units_sold      integer default 0,
  closing_stock   integer default 0,
  unit_price      numeric(15,2) default 0,
  total_revenue   numeric(15,2) default 0,
  payment_method  text,
  notes           text,
  submitted_at    timestamptz default now(),
  fraud_score     numeric(5,2) default 0,
  company_id      text,
  created_at      timestamptz default now()
);

-- 6. CDC LOG
create table if not exists cdc_log (
  id            text primary key,
  table_name    text not null,
  record_id     text not null,
  field_changed text not null,
  old_value     text,
  new_value     text,
  changed_by    text not null,
  reason        text,
  company_id    text,
  changed_at    timestamptz default now()
);

-- ── Disable RLS (app handles auth) ──
alter table users      disable row level security;
alter table companies  disable row level security;
alter table products   disable row level security;
alter table sellers    disable row level security;
alter table sales      disable row level security;
alter table cdc_log    disable row level security;

-- ── Indexes ──
create index if not exists idx_sales_date        on sales(date);
create index if not exists idx_sales_seller      on sales(seller_name);
create index if not exists idx_sales_fraud       on sales(fraud_score);
create index if not exists idx_sales_company     on sales(company_id);
create index if not exists idx_cdc_record        on cdc_log(record_id);
create index if not exists idx_cdc_company       on cdc_log(company_id);
create index if not exists idx_users_company     on users(company_id);
create index if not exists idx_products_company  on products(company_id);
create index if not exists idx_sellers_company   on sellers(company_id);

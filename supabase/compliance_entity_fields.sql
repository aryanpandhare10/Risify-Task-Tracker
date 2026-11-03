-- ============================================================
-- Company fields for compliance entities, matching the entity register:
--   Name | Country | Type of entity | Business Activity | Incorporation Date |
--   Years | Name of Director | Name of Shareholder | No. of Shares | Face Value |
--   Paid up Capital | % of Shareholding
-- "Years", "Paid up Capital" and "% of Shareholding" are calculated in the
-- app (years since incorporation; shares x face value; shares / total).
--
-- Run AFTER compliance.sql, in Supabase: SQL Editor -> New query -> paste
-- -> Run. Safe to re-run.
-- ============================================================

alter table compliance_entities
  add column if not exists country            text,
  add column if not exists entity_type        text,   -- Pvt Ltd, LLP, Partnership firm, Trust, LLC, ...
  add column if not exists business_activity  text,
  add column if not exists incorporation_date date,
  add column if not exists currency           text,   -- currency of the face value, e.g. AED
  add column if not exists shareholders       jsonb not null default '[]'::jsonb;
  -- [{"name": "...", "shares": 100000, "face_value": 1000}]

-- Move the matching values the seed data kept as free-form details
-- ("Shareholders", "Quantity", "Rate per share", "Incorporation date",
-- "% Holding") into the new columns. Only touches companies that have no
-- shareholders yet; "Directors", "License No." etc. stay as details.
do $$
declare
  e    record;
  sh   text; qty text; rate text; inc text;
  cur  text; face numeric; inc_date date;
begin
  for e in
    select * from compliance_entities where kind = 'company' and shareholders = '[]'::jsonb
  loop
    select
      max(x->>'value') filter (where x->>'field' = 'Shareholders'),
      max(x->>'value') filter (where x->>'field' = 'Quantity'),
      max(x->>'value') filter (where x->>'field' = 'Rate per share'),
      max(x->>'value') filter (where x->>'field' = 'Incorporation date')
    into sh, qty, rate, inc
    from jsonb_array_elements(e.details) x;

    continue when coalesce(trim(sh), '') = '';

    cur := null; face := null; inc_date := null;
    if rate ~ '^[A-Za-z]{3} *[0-9.,]+$' then
      cur  := upper(substring(rate from '^([A-Za-z]{3})'));
      face := replace(substring(rate from '([0-9.,]+)$'), ',', '')::numeric;
    end if;
    if inc ~ '^\d{2}\.\d{2}\.\d{4}$' then
      inc_date := to_date(inc, 'DD.MM.YYYY');
    end if;

    update compliance_entities set
      shareholders = jsonb_build_array(jsonb_build_object(
        'name', trim(sh),
        'shares', case when replace(qty, ',', '') ~ '^[0-9.]+$' then replace(qty, ',', '')::numeric end,
        'face_value', face)),
      currency           = coalesce(currency, cur),
      incorporation_date = coalesce(incorporation_date, inc_date),
      -- the seed entities all come from the "Dubai Entities" calendar
      country            = coalesce(country, 'Dubai'),
      details = (
        select coalesce(jsonb_agg(x), '[]'::jsonb)
        from jsonb_array_elements(e.details) x
        where x->>'field' not in ('Shareholders', 'Quantity', 'Rate per share', '% Holding')
          and not (x->>'field' = 'Incorporation date' and inc_date is not null)
      )
    where id = e.id;
  end loop;
end $$;

-- ---------------------------------------------------------------
-- Directors: a list, one name per entry (was a free-form "Directors" detail)
-- ---------------------------------------------------------------
alter table compliance_entities
  add column if not exists directors jsonb not null default '[]'::jsonb;  -- [{"name": "..."}]

-- Move "Directors" details into the list (a value like "A, B" or "A & B"
-- becomes two directors), and drop them from the free-form details.
update compliance_entities e set
  directors = coalesce((
    select jsonb_agg(jsonb_build_object('name', trim(t.n)) order by x.pos, t.ord)
    from jsonb_array_elements(e.details) with ordinality as x(el, pos),
         regexp_split_to_table(x.el->>'value', '\s*[,;&]\s*') with ordinality as t(n, ord)
    where x.el->>'field' = 'Directors' and trim(t.n) <> ''
  ), '[]'::jsonb),
  details = (
    select coalesce(jsonb_agg(x), '[]'::jsonb)
    from jsonb_array_elements(e.details) x
    where x->>'field' is distinct from 'Directors'
  )
where e.kind = 'company'
  and e.directors = '[]'::jsonb
  and exists (select 1 from jsonb_array_elements(e.details) x where x->>'field' = 'Directors');

-- Make the API see the new columns right away.
notify pgrst, 'reload schema';

-- READ ONLY: candidate index equivalence & dependency proof.
-- Not a permission to drop indexes; no DDL or source writes occur.
-- Review at the current main production SHA before any separate change.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '7s';
SET LOCAL lock_timeout = '1s';
WITH pairs(candidate_name, survivor_name) AS (
  VALUES
    ('public.idx_mw_snap_scraped'::regclass,
     'public.idx_mw_snap_scraped_utc'::regclass),
    ('public.idx_live_snapshots_hash'::regclass,
     'public.idx_live_snap_hash'::regclass)
), m AS (
  SELECT p.*,c.*,s.indexrelid AS survivor_id,
         (SELECT COUNT(*) FROM pg_constraint k WHERE k.conindid=p.candidate_name) AS constraint_refs,
         (SELECT COUNT(*) FROM pg_depend d
          WHERE d.refobjid=p.candidate_name AND d.deptype NOT IN ('i','a')) AS external_refs
  FROM pairs p
  JOIN pg_index c ON c.indexrelid=p.candidate_name
  JOIN pg_index s ON s.indexrelid=p.survivor_name
)
SELECT m.candidate_name::text AS proposed_retire_index,
       m.survivor_name::text AS survivor_index,
       pg_size_pretty(pg_relation_size(m.candidate_name)) AS prospective_reclaim,
       COALESCE(cstat.idx_scan,0) AS candidate_index_scans,
       COALESCE(sstat.idx_scan,0) AS survivor_index_scans,
       m.constraint_refs,m.external_refs,
       (
         c.indrelid=s.indrelid
         AND c.indnatts=s.indnatts
         AND c.indnkeyatts=s.indnkeyatts
         AND c.indkey=s.indkey
         AND c.indclass=s.indclass
         AND c.indcollation=s.indcollation
         AND c.indoption=s.indoption
         AND c.indisvalid AND s.indisvalid
         AND c.indisready AND s.indisready
         AND NOT c.indisunique AND NOT s.indisunique
         AND NOT c.indisprimary AND NOT s.indisprimary
         AND pg_get_expr(c.indpred,c.indrelid)
             IS NOT DISTINCT FROM pg_get_expr(s.indpred,s.indrelid)
         AND pg_get_expr(c.indexprs,c.indrelid)
             IS NOT DISTINCT FROM pg_get_expr(s.indexprs,s.indrelid)
       ) AS structurally_equivalent,
       FALSE AS production_drop_authorized
FROM m
JOIN pg_index c ON c.indexrelid=m.candidate_name
JOIN pg_index s ON s.indexrelid=m.survivor_name
LEFT JOIN pg_stat_user_indexes cstat ON cstat.indexrelid=m.candidate_name
LEFT JOIN pg_stat_user_indexes sstat ON sstat.indexrelid=m.survivor_name
ORDER BY proposed_retire_index;
COMMIT;

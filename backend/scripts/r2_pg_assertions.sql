\set ON_ERROR_STOP on
BEGIN READ ONLY;
SELECT version(), current_database(), inet_server_addr(), inet_server_port();
SHOW transaction_isolation;
SHOW fsync;
SELECT extname, extversion FROM pg_extension ORDER BY extname;
SELECT datname FROM pg_database ORDER BY datname;
SELECT app, name FROM django_migrations WHERE app = 'practical_training' ORDER BY name;
SELECT
  (SELECT count(*) FROM practical_training_serverevidence) AS evidence,
  (SELECT count(*) FROM practical_training_repairclaim) AS repair_claim,
  (SELECT count(*) FROM skill_review_submissionsnapshot) AS submissions,
  (SELECT count(*) FROM skill_review_verificationresult) AS results,
  (SELECT count(*) FROM learning_map_verificationfact) AS facts,
  (SELECT count(*) FROM skill_review_downstreamnotice) AS notices,
  (SELECT count(*) FROM skill_review_retestassignment) AS retests;
SELECT key, evidence_id, attempt_id, result_id, status
FROM practical_training_serverevidence ORDER BY key;
SELECT attempt_id, count(*) AS submissions,
       count(*) FILTER (WHERE first_effective) AS first_effective,
       array_agg(sequence ORDER BY sequence) AS sequences
FROM skill_review_submissionsnapshot GROUP BY attempt_id ORDER BY attempt_id;
SELECT status, count(*), min(attempts), max(attempts)
FROM skill_review_downstreamnotice GROUP BY status;
SELECT status, outcome, count(*) FROM skill_review_retestassignment GROUP BY status, outcome;
SELECT conrelid::regclass AS table_name, conname, pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid IN ('practical_training_serverevidence'::regclass,
                   'practical_training_repairclaim'::regclass,
                   'skill_review_submissionsnapshot'::regclass)
  AND contype = 'u'
ORDER BY table_name, conname;
SELECT count(*) AS duplicate_evidence_keys FROM (
  SELECT key FROM practical_training_serverevidence GROUP BY key HAVING count(*) > 1
) q;
SELECT count(*) AS duplicate_first_effective_attempts FROM (
  SELECT attempt_id FROM skill_review_submissionsnapshot
  WHERE first_effective GROUP BY attempt_id HAVING count(*) > 1
) q;
COMMIT;

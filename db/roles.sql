-- Least privilege, enforced by Postgres itself (not just by our code).
-- pulse_engine  = the robot. May read the pipeline and write ONLY the 4 signal columns.
-- pulse_founder = the app's edit screen. May write ONLY Vikram's own columns.
grant usage on schema public to pulse_engine, pulse_founder;

revoke all on vcs from pulse_engine, pulse_founder;
grant select on vcs to pulse_engine, pulse_founder;
grant update (last_signal_date, signal_summary, follow_up_score, recommended_action) on vcs to pulse_engine;
grant update (name, firm, thesis, region, status, last_contact_date, contact_history, notes, feed_url) on vcs to pulse_founder;
grant insert (name, firm, thesis, region, status, last_contact_date, contact_history, notes, feed_url) on vcs to pulse_founder;
grant delete on vcs to pulse_founder;
grant usage on sequence vcs_id_seq to pulse_founder;

grant select, insert, update, delete on signals, runs, vc_changes to pulse_engine;
grant usage on sequence signals_id_seq, runs_id_seq to pulse_engine;
grant select on signals, runs, vc_changes to pulse_founder;

grant select, insert on drafts to pulse_engine;
grant usage on sequence drafts_id_seq to pulse_engine;

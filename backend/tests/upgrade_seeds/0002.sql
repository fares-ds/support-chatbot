-- Revision 0002: the heartbeats table. The worker's last beat, an hour old.
INSERT INTO heartbeats (name, beat_at) VALUES ('worker', now() - interval '1 hour');

-- expect: S-SEC-7
-- mookko:phase migrate
INSERT INTO __SCHEMA__.secrets_ref (ref_id, value) VALUES ('a', pgp_sym_encrypt('x', 'k'));

-- Applied transactionally by scripts/migrate.py. No production credentials here.
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'portfolio_writer') THEN
    CREATE ROLE portfolio_writer NOLOGIN NOINHERIT NOBYPASSRLS;
  END IF;
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'portfolio_writer'
             AND (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb)) THEN
    RAISE EXCEPTION 'portfolio_writer must be an unprivileged role';
  END IF;
END $$;
GRANT portfolio_writer TO authenticator;
-- Explicit schema ACLs survive restoring into a database with different defaults.
GRANT USAGE ON SCHEMA public TO anon,authenticated,portfolio_writer;
REVOKE CREATE ON SCHEMA public FROM PUBLIC,anon,authenticated,portfolio_writer;

CREATE DOMAIN pf_private.sha256_hex AS text
  CHECK (VALUE ~ '^[0-9a-f]{64}$');
CREATE DOMAIN pf_private.finite_float AS double precision
  CHECK (VALUE > '-Infinity'::double precision AND VALUE < 'Infinity'::double precision);

-- Normalize equivalent JSON numbers (5, 5.0) before deriving semantic identity.
CREATE FUNCTION pf_private.canonical_json(value jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE STRICT SET search_path = '' AS $$
DECLARE normalized jsonb;
BEGIN
 CASE jsonb_typeof(value)
 WHEN 'object' THEN
   SELECT coalesce(jsonb_object_agg(key,pf_private.canonical_json(v)),'{}'::jsonb)
   INTO normalized FROM jsonb_each(value) AS fields(key,v);
 WHEN 'array' THEN
   SELECT coalesce(jsonb_agg(pf_private.canonical_json(v) ORDER BY ordinal),'[]'::jsonb)
   INTO normalized FROM jsonb_array_elements(value) WITH ORDINALITY AS entries(v,ordinal);
 WHEN 'number' THEN normalized:=to_jsonb(trim_scale((value #>> '{}')::numeric));
 ELSE normalized:=value;
 END CASE;
 RETURN normalized;
END $$;
CREATE FUNCTION pf_private.hash_json(value jsonb) RETURNS text
LANGUAGE sql IMMUTABLE STRICT SET search_path = '' AS $$
  SELECT encode(sha256(convert_to(pf_private.canonical_json(value)::text, 'UTF8')), 'hex')
$$;
CREATE FUNCTION pf_private.num(value jsonb) RETURNS double precision
LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $$
DECLARE result pf_private.finite_float;
BEGIN
  IF jsonb_typeof(value) IS DISTINCT FROM 'number' THEN
    RAISE EXCEPTION 'missing or invalid scientific number' USING ERRCODE='23514';
  END IF;
  result := (value #>> '{}')::double precision;
  RETURN result;
END $$;
CREATE FUNCTION pf_private.day(value text) RETURNS date
LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $$
BEGIN
  IF value IS NULL OR value !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN
    RAISE EXCEPTION 'missing or invalid ISO session date' USING ERRCODE='23514';
  END IF;
  RETURN value::date;
END $$;
CREATE FUNCTION pf_private.instant(value text) RETURNS timestamptz
LANGUAGE plpgsql IMMUTABLE SET search_path = '' AS $$
BEGIN
  IF value IS NULL OR value !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}T.*(Z|[+-][0-9]{2}:[0-9]{2})$' THEN
    RAISE EXCEPTION 'missing or naive ISO timestamp' USING ERRCODE='23514';
  END IF;
  RETURN value::timestamptz;
END $$;

CREATE TABLE pf_private.snapshots (
  snapshot_sha256 pf_private.sha256_hex PRIMARY KEY,
  content text NOT NULL CHECK (octet_length(content) BETWEEN 1 AND 16777216),
  data_sha256 pf_private.sha256_hex NOT NULL,
  captured_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  CHECK (snapshot_sha256 = encode(sha256(convert_to(content,'UTF8')),'hex'))
);
CREATE TABLE pf_private.runs (
  run_id uuid PRIMARY KEY,
  request_key pf_private.sha256_hex NOT NULL UNIQUE,
  identity jsonb NOT NULL CHECK (jsonb_typeof(identity)='object'),
  snapshot_sha256 pf_private.sha256_hex NOT NULL REFERENCES pf_private.snapshots,
  state text NOT NULL DEFAULT 'staged' CHECK (state IN ('staged','published')),
  executed_at timestamptz NOT NULL,
  completed_at timestamptz,
  published_at timestamptz,
  cutoff date NOT NULL,
  target date NOT NULL CHECK (target > cutoff),
  target_open timestamptz NOT NULL,
  target_close timestamptz NOT NULL CHECK (target_close > target_open),
  payload jsonb,
  result_sha256 pf_private.sha256_hex,
  CHECK (cutoff=pf_private.day(identity->>'observation_cutoff')
     AND target=pf_private.day(identity->>'forecast_target')
     AND (target_open AT TIME ZONE 'America/New_York')::date=target
     AND (target_close AT TIME ZONE 'America/New_York')::date=target),
  CHECK (request_key=pf_private.hash_json(identity)),
  CHECK (run_id=substr(request_key,1,32)::uuid),
  CHECK ((state='staged' AND payload IS NULL AND result_sha256 IS NULL
          AND published_at IS NULL AND completed_at IS NULL)
         OR (state='published' AND payload IS NOT NULL AND result_sha256 IS NOT NULL
          AND completed_at IS NOT NULL AND published_at IS NOT NULL
          AND completed_at>=executed_at AND published_at>=completed_at)),
  CHECK (result_sha256 IS NULL OR result_sha256=pf_private.hash_json(payload))
);
CREATE INDEX runs_published_order ON pf_private.runs
  (target DESC, published_at DESC, run_id DESC) WHERE state='published';
CREATE TABLE pf_private.asset_results (
  run_id uuid NOT NULL REFERENCES pf_private.runs,
  ticker text NOT NULL CHECK (ticker ~ '^[A-Z0-9]+([.-][A-Z0-9]+)*$'),
  observed_price pf_private.finite_float NOT NULL CHECK (observed_price>0),
  predicted_price pf_private.finite_float NOT NULL CHECK (predicted_price>0),
  predicted_return pf_private.finite_float NOT NULL,
  weight pf_private.finite_float NOT NULL CHECK (weight>=-1e-9 AND weight<=1+1e-9),
  model jsonb NOT NULL CHECK (jsonb_typeof(model)='object'
    AND jsonb_typeof(model->'constructor') IS NOT DISTINCT FROM 'object'
    AND model->'constructor'<>'{}'::jsonb
    AND jsonb_typeof(model->'fit') IS NOT DISTINCT FROM 'object'
    AND model->'fit'<>'{}'::jsonb),
  recent_history jsonb NOT NULL CHECK (jsonb_typeof(recent_history)='array' AND jsonb_array_length(recent_history)>0),
  PRIMARY KEY (run_id,ticker),
  CHECK (abs(predicted_return-(predicted_price/observed_price-1))
         <=1e-12+1e-10*abs(predicted_return))
);
CREATE INDEX asset_results_ticker ON pf_private.asset_results (ticker,run_id);
CREATE TABLE pf_private.attempts (
  attempt_id uuid PRIMARY KEY,
  run_id uuid NOT NULL REFERENCES pf_private.runs,
  started_at timestamptz NOT NULL,
  finished_at timestamptz,
  state text NOT NULL CHECK (state IN ('registered','failed','published')),
  diagnostics jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(diagnostics)='object'),
  CHECK (finished_at IS NULL OR finished_at>=started_at)
);
CREATE INDEX attempts_run ON pf_private.attempts(run_id,started_at);

CREATE FUNCTION pf_private.validate_snapshot(p_identity jsonb, p_content text)
RETURNS jsonb LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE s jsonb:=p_content::jsonb; a jsonb; o jsonb; names jsonb; dates jsonb;
  ordinal integer; lower_bound double precision; upper_bound double precision; count_assets integer;
BEGIN
  IF octet_length(p_content)>16777216 OR s->>'kind' IS DISTINCT FROM 'forecast_inputs'
     OR s->>'schema_version' IS DISTINCT FROM '1'
     OR p_identity->>'schema_version' IS DISTINCT FROM '1'
     OR p_identity->>'mode' NOT IN ('live','retrospective')
     OR p_identity->>'mode' IS NULL
     OR p_identity->>'scientific_revision' IS NULL
     OR p_identity->>'scientific_revision' !~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'
     OR jsonb_typeof(p_identity->'universe') IS DISTINCT FROM 'array'
     OR jsonb_typeof(s->'assets') IS DISTINCT FROM 'array'
     OR jsonb_typeof(s->'plan'->'sessions') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'invalid identity or snapshot schema' USING ERRCODE='23514';
  END IF;
  PERFORM (p_identity->>'software_revision')::pf_private.sha256_hex;
  PERFORM (p_identity->>'lock_sha256')::pf_private.sha256_hex;
  IF p_identity->>'software_revision' IS NULL OR p_identity->>'lock_sha256' IS NULL
     OR p_identity->>'python_version' IS NULL THEN
    RAISE EXCEPTION 'missing release provenance' USING ERRCODE='23514';
  END IF;
  SELECT jsonb_agg(value ORDER BY value) INTO names
    FROM (SELECT DISTINCT value FROM jsonb_array_elements(p_identity->'universe')) q;
  IF names IS DISTINCT FROM p_identity->'universe' OR jsonb_array_length(names)=0 THEN
    RAISE EXCEPTION 'universe must be nonempty unique canonical order' USING ERRCODE='23514';
  END IF;
  SELECT jsonb_agg(value->'ticker' ORDER BY value->>'ticker') INTO names
    FROM jsonb_array_elements(s->'assets');
  IF names IS DISTINCT FROM p_identity->'universe' THEN
    RAISE EXCEPTION 'snapshot universe mismatch' USING ERRCODE='23514';
  END IF;
  SELECT jsonb_agg(value ORDER BY value) INTO names
    FROM jsonb_array_elements(s->'request'->'tickers');
  IF names IS DISTINCT FROM p_identity->'universe'
     OR s->'request'->>'mode' IS DISTINCT FROM p_identity->>'mode'
     OR s->'request'->>'history_start' IS DISTINCT FROM p_identity->>'history_start'
     OR s->'request'->>'scientific_revision' IS DISTINCT FROM p_identity->>'scientific_revision'
     OR s->'request'->'forecast' IS DISTINCT FROM p_identity->'forecast'
     OR s->'request'->'allocation' IS DISTINCT FROM p_identity->'allocation'
     OR s->'request'->'data' IS DISTINCT FROM p_identity->'data'
     OR s->'plan'->>'observation_cutoff' IS DISTINCT FROM p_identity->>'observation_cutoff'
     OR s->'plan'->>'forecast_target' IS DISTINCT FROM p_identity->>'forecast_target'
     OR s->>'price_basis' IS DISTINCT FROM 'adjusted_close'
     OR p_identity->'data'->>'currency' IS DISTINCT FROM 'USD'
     OR p_identity->'data'->>'calendar' IS DISTINCT FROM 'XNYS' THEN
    RAISE EXCEPTION 'snapshot differs from logical request' USING ERRCODE='23514';
  END IF;
  IF pf_private.day(p_identity->>'observation_cutoff')>=pf_private.day(p_identity->>'forecast_target')
     OR pf_private.day(p_identity->>'history_start')>pf_private.day(p_identity->>'observation_cutoff') THEN
    RAISE EXCEPTION 'invalid session horizon' USING ERRCODE='23514';
  END IF;
  count_assets:=jsonb_array_length(names);
  lower_bound:=pf_private.num(p_identity->'allocation'->'lower_bound');
  upper_bound:=pf_private.num(p_identity->'allocation'->'upper_bound');
  IF lower_bound<0 OR upper_bound>1 OR lower_bound>upper_bound
     OR count_assets*(p_identity->'allocation'->>'lower_bound')::numeric>1
     OR count_assets*(p_identity->'allocation'->>'upper_bound')::numeric<1
     OR pf_private.num(p_identity->'allocation'->'risk_aversion')<=0
     OR pf_private.num(p_identity->'allocation'->'risk_window')<2 THEN
    RAISE EXCEPTION 'infeasible allocation settings' USING ERRCODE='23514';
  END IF;
  dates:=s->'plan'->'sessions';
  IF jsonb_array_length(dates)<(p_identity->'allocation'->>'risk_window')::integer+1
     OR dates->>-1 IS DISTINCT FROM p_identity->>'observation_cutoff' THEN
    RAISE EXCEPTION 'incomplete dated risk history' USING ERRCODE='23514';
  END IF;
  ordinal:=0;
  FOR o IN SELECT value FROM jsonb_array_elements(dates) LOOP
    PERFORM pf_private.day(o #>> '{}');
    IF ordinal>0 AND (dates->>ordinal)<=(dates->>(ordinal-1)) THEN
      RAISE EXCEPTION 'unordered or duplicate sessions' USING ERRCODE='23514';
    END IF;
    ordinal:=ordinal+1;
  END LOOP;
  FOR a IN SELECT value FROM jsonb_array_elements(s->'assets') LOOP
    IF a->>'ticker' !~ '^[A-Z0-9]+([.-][A-Z0-9]+)*$'
       OR jsonb_typeof(a->'metadata') IS DISTINCT FROM 'array'
       OR a->>'provider' IS NULL OR a->>'provider'=''
       OR jsonb_typeof(a->'observations') IS DISTINCT FROM 'array'
       OR jsonb_array_length(a->'observations')<>jsonb_array_length(dates) THEN
      RAISE EXCEPTION 'invalid asset input provenance/history' USING ERRCODE='23514';
    END IF;
    IF pf_private.instant(a->>'retrieved_at')>clock_timestamp()+interval '1 minute' THEN
      RAISE EXCEPTION 'input retrieval timestamp is in the future' USING ERRCODE='23514';
    END IF;
    ordinal:=0;
    FOR o IN SELECT value FROM jsonb_array_elements(a->'observations') LOOP
      IF o->>'session' IS DISTINCT FROM dates->>ordinal OR pf_private.num(o->'price')<=0 THEN
        RAISE EXCEPTION 'missing, invalid or misaligned observed price' USING ERRCODE='23514';
      END IF;
      ordinal:=ordinal+1;
    END LOOP;
  END LOOP;
  PERFORM (s->>'data_sha256')::pf_private.sha256_hex;
  IF s->>'data_sha256' IS NULL OR jsonb_typeof(s->'provider_options') IS DISTINCT FROM 'object'
     OR jsonb_typeof(s->'software') IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'missing data provenance' USING ERRCODE='23514';
  END IF;
  RETURN s;
END $$;

CREATE FUNCTION pf_private.protect_rows() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE rid uuid;
BEGIN
  IF TG_TABLE_NAME='runs' THEN
    IF TG_OP='DELETE' OR (TG_OP='UPDATE' AND OLD.state='published') THEN
      RAISE EXCEPTION 'run identity and published content are immutable' USING ERRCODE='23514';
    END IF;
    IF TG_OP='UPDATE' AND (NEW.identity IS DISTINCT FROM OLD.identity
       OR NEW.snapshot_sha256 IS DISTINCT FROM OLD.snapshot_sha256
       OR NEW.executed_at IS DISTINCT FROM OLD.executed_at
       OR NEW.request_key IS DISTINCT FROM OLD.request_key OR NEW.run_id<>OLD.run_id
       OR NEW.cutoff<>OLD.cutoff OR NEW.target<>OLD.target
       OR NEW.target_open<>OLD.target_open OR NEW.target_close<>OLD.target_close) THEN
      RAISE EXCEPTION 'bound request is immutable' USING ERRCODE='23514';
    END IF;
  ELSIF TG_TABLE_NAME='snapshots' THEN
    RAISE EXCEPTION 'snapshots are immutable' USING ERRCODE='23514';
  ELSE
    rid:=CASE WHEN TG_OP='DELETE' THEN OLD.run_id ELSE NEW.run_id END;
    IF EXISTS (SELECT FROM pf_private.runs WHERE run_id=rid AND state='published') THEN
      RAISE EXCEPTION 'published asset results are immutable' USING ERRCODE='23514';
    END IF;
  END IF;
  IF TG_OP='DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER snapshots_immutable BEFORE UPDATE OR DELETE ON pf_private.snapshots
  FOR EACH ROW EXECUTE FUNCTION pf_private.protect_rows();
CREATE TRIGGER runs_immutable BEFORE UPDATE OR DELETE ON pf_private.runs
  FOR EACH ROW EXECUTE FUNCTION pf_private.protect_rows();
CREATE TRIGGER assets_immutable BEFORE INSERT OR UPDATE OR DELETE ON pf_private.asset_results
  FOR EACH ROW EXECUTE FUNCTION pf_private.protect_rows();
CREATE FUNCTION pf_private.complete_run() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
DECLARE names jsonb; total double precision; low double precision; high double precision;
BEGIN
  IF NEW.state='published' THEN
    SELECT jsonb_agg(ticker ORDER BY ticker),sum(weight),min(weight),max(weight)
      INTO names,total,low,high FROM pf_private.asset_results WHERE run_id=NEW.run_id;
    IF names IS NULL OR NEW.identity->'universe' IS NULL
       OR names IS DISTINCT FROM NEW.identity->'universe' OR abs(total-1)>1e-9
       OR low<(NEW.identity->'allocation'->>'lower_bound')::double precision-1e-9
       OR high>(NEW.identity->'allocation'->>'upper_bound')::double precision+1e-9 THEN
      RAISE EXCEPTION 'published run must contain one complete feasible portfolio' USING ERRCODE='23514';
    END IF;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER require_complete_run AFTER INSERT OR UPDATE ON pf_private.runs
  FOR EACH ROW EXECUTE FUNCTION pf_private.complete_run();

CREATE FUNCTION public.pf_access() RETURNS jsonb
LANGUAGE sql STABLE SECURITY INVOKER SET search_path = '' AS $$
  SELECT jsonb_build_object('role',current_user,'schema_version',1)
$$;
CREATE FUNCTION public.pf_lookup(p_identity jsonb DEFAULT NULL,p_run_id uuid DEFAULT NULL)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
 SELECT to_jsonb(r)-'payload' FROM pf_private.runs r
 WHERE (p_identity IS NOT NULL AND r.request_key=pf_private.hash_json(p_identity))
    OR (p_run_id IS NOT NULL AND r.run_id=p_run_id)
$$;
CREATE FUNCTION public.pf_snapshot(p_hash text) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
 SELECT jsonb_build_object('snapshot_sha256',snapshot_sha256,'content',content)
 FROM pf_private.snapshots WHERE snapshot_sha256=p_hash
$$;
CREATE FUNCTION public.pf_attempt(p_run_id uuid,p_attempt_id uuid,p_started_at timestamptz)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE a pf_private.attempts;
BEGIN
 IF p_started_at IS NULL OR p_started_at>clock_timestamp()+interval '1 minute' THEN
   RAISE EXCEPTION 'invalid attempt timestamp' USING ERRCODE='23514';
 END IF;
 INSERT INTO pf_private.attempts(attempt_id,run_id,started_at,state)
 VALUES(p_attempt_id,p_run_id,p_started_at,'registered') ON CONFLICT DO NOTHING;
 SELECT * INTO STRICT a FROM pf_private.attempts WHERE attempt_id=p_attempt_id;
 IF a.run_id<>p_run_id OR a.started_at<>p_started_at THEN
   RAISE EXCEPTION 'attempt identity conflict' USING ERRCODE='PT409';
 END IF;
 RETURN to_jsonb(a);
END $$;
CREATE FUNCTION public.pf_stage(p_identity jsonb,p_snapshot text,p_attempt_id uuid,p_started_at timestamptz)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE s jsonb; h text; k text; r pf_private.runs;
BEGIN
 s:=pf_private.validate_snapshot(p_identity,p_snapshot);
 h:=encode(sha256(convert_to(p_snapshot,'UTF8')),'hex'); k:=pf_private.hash_json(p_identity);
 IF p_started_at IS NULL OR p_started_at<=pf_private.instant(s->'plan'->>'cutoff_close')
    OR p_started_at>clock_timestamp()+interval '1 minute' THEN
   RAISE EXCEPTION 'invalid execution time' USING ERRCODE='23514';
 END IF;
 IF p_identity->>'mode'='live' AND clock_timestamp()>=pf_private.instant(s->'plan'->>'target_open') THEN
   RAISE EXCEPTION 'live publication deadline elapsed' USING ERRCODE='PT410';
 END IF;
 INSERT INTO pf_private.snapshots(snapshot_sha256,content,data_sha256)
 VALUES(h,p_snapshot,s->>'data_sha256') ON CONFLICT DO NOTHING;
 INSERT INTO pf_private.runs(run_id,request_key,identity,snapshot_sha256,executed_at,
                            cutoff,target,target_open,target_close)
 VALUES(substr(k,1,32)::uuid,k,p_identity,h,p_started_at,
        pf_private.day(p_identity->>'observation_cutoff'),pf_private.day(p_identity->>'forecast_target'),
        pf_private.instant(s->'plan'->>'target_open'),pf_private.instant(s->'plan'->>'target_close'))
 ON CONFLICT DO NOTHING;
 SELECT * INTO STRICT r FROM pf_private.runs WHERE request_key=k FOR UPDATE;
 IF r.snapshot_sha256<>h THEN
   RAISE EXCEPTION 'request already bound to a different snapshot' USING ERRCODE='PT409';
 END IF;
 PERFORM public.pf_attempt(r.run_id,p_attempt_id,p_started_at);
 RETURN to_jsonb(r)-'payload';
END $$;
CREATE FUNCTION public.pf_fail(p_run_id uuid,p_attempt_id uuid,p_stage text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
 IF p_stage NOT IN ('data','forecast','allocation','publication','readback') THEN
   RAISE EXCEPTION 'invalid failure stage' USING ERRCODE='23514';
 END IF;
 UPDATE pf_private.attempts SET state='failed',finished_at=clock_timestamp(),
   diagnostics=jsonb_build_object('stage',p_stage)
 WHERE attempt_id=p_attempt_id AND run_id=p_run_id AND state='registered';
 RETURN jsonb_build_object('recorded',FOUND);
END $$;
CREATE FUNCTION public.pf_publish(p_run_id uuid,p_payload jsonb,p_attempt_id uuid,
                                  p_completed_at timestamptz,p_diagnostics jsonb DEFAULT '{}')
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE r pf_private.runs; a jsonb; input jsonb; observed jsonb; history jsonb;
  s jsonb; names jsonb; i integer:=0; n integer; j integer; price double precision;
BEGIN
 SELECT * INTO STRICT r FROM pf_private.runs WHERE run_id=p_run_id FOR UPDATE;
 IF r.state='published' THEN
   IF r.payload IS DISTINCT FROM p_payload THEN
     RAISE EXCEPTION 'published scientific payload conflict' USING ERRCODE='PT409';
   END IF;
   RETURN jsonb_build_object('run_id',r.run_id,'state',r.state,'idempotent',true);
 END IF;
 IF p_completed_at IS NULL OR p_completed_at<r.executed_at OR p_completed_at>clock_timestamp()
    OR NOT EXISTS(SELECT FROM pf_private.attempts WHERE attempt_id=p_attempt_id
                  AND run_id=p_run_id AND started_at<=p_completed_at) THEN
   RAISE EXCEPTION 'invalid completion/attempt identity' USING ERRCODE='23514';
 END IF;
 IF r.identity->>'mode'='live' AND clock_timestamp()>=r.target_open THEN
   RAISE EXCEPTION 'live publication deadline elapsed' USING ERRCODE='PT410';
 END IF;
 IF p_payload->>'schema_version' IS DISTINCT FROM '1'
    OR jsonb_typeof(p_payload->'assets') IS DISTINCT FROM 'array'
    OR p_payload->>'risk_estimator' IS DISTINCT FROM 'observed_sample_ddof1'
    OR p_payload->>'expectation_estimator' IS DISTINCT FROM 'direct_forecast_return'
    OR p_payload->>'risk_observations' IS DISTINCT FROM r.identity->'allocation'->>'risk_window'
    OR p_payload->'software'->>'source_sha256' IS DISTINCT FROM r.identity->>'software_revision'
    OR p_payload->>'lock_sha256' IS DISTINCT FROM r.identity->>'lock_sha256'
    OR p_payload->'solver'->>'status' IS DISTINCT FROM '0'
    OR coalesce(p_payload->'solver'->>'method','')=''
    OR jsonb_typeof(p_payload->'software'->'packages') IS DISTINCT FROM 'object'
    OR p_payload->'software'->'packages'='{}'::jsonb
    OR p_payload->'software'->>'python' IS DISTINCT FROM r.identity->>'python_version'
    OR jsonb_typeof(p_diagnostics) IS DISTINCT FROM 'object' THEN
   RAISE EXCEPTION 'missing scientific outputs/provenance' USING ERRCODE='23514';
 END IF;
 SELECT jsonb_agg(value->'ticker' ORDER BY value->>'ticker') INTO names
 FROM jsonb_array_elements(p_payload->'assets');
 IF names IS DISTINCT FROM r.identity->'universe' THEN
   RAISE EXCEPTION 'complete ticker membership required' USING ERRCODE='23514';
 END IF;
 n:=jsonb_array_length(names);
 IF jsonb_typeof(p_payload->'expected_returns') IS DISTINCT FROM 'array'
    OR jsonb_typeof(p_payload->'covariance') IS DISTINCT FROM 'array'
    OR jsonb_array_length(p_payload->'expected_returns')<>n
    OR jsonb_array_length(p_payload->'covariance')<>n THEN
   RAISE EXCEPTION 'invalid risk/vector dimensions' USING ERRCODE='23514';
 END IF;
 SELECT content::jsonb INTO STRICT s FROM pf_private.snapshots WHERE snapshot_sha256=r.snapshot_sha256;
 FOR a IN SELECT value FROM jsonb_array_elements(p_payload->'assets') ORDER BY value->>'ticker' LOOP
   SELECT value INTO STRICT input FROM jsonb_array_elements(s->'assets') WHERE value->>'ticker'=a->>'ticker';
   observed:=input->'observations'->-1;
   price:=pf_private.num(a->'observed_price');
   IF price<=0 OR price<>pf_private.num(observed->'price')
      OR pf_private.num(a->'predicted_price')<=0
      OR abs(pf_private.num(a->'predicted_return')-pf_private.num(p_payload->'expected_returns'->i))>1e-12 THEN
     RAISE EXCEPTION 'invalid observed/forecast/expectation basis' USING ERRCODE='23514';
   END IF;
   SELECT jsonb_agg(value ORDER BY value->>'session') INTO history
   FROM jsonb_array_elements(input->'observations')
   WHERE pf_private.day(value->>'session')>=r.cutoff-(r.identity->'data'->>'recent_history_days')::integer;
   IF history IS DISTINCT FROM a->'recent_history' THEN
     RAISE EXCEPTION 'recent history must preserve exact dated inputs' USING ERRCODE='23514';
   END IF;
   IF jsonb_typeof(p_payload->'covariance'->i) IS DISTINCT FROM 'array'
      OR jsonb_array_length(p_payload->'covariance'->i)<>n THEN
     RAISE EXCEPTION 'invalid covariance row dimensions' USING ERRCODE='23514';
   END IF;
   FOR j IN 0..n-1 LOOP
     price:=pf_private.num(p_payload->'covariance'->i->j);
     IF (i=j AND price<0) OR abs(price-pf_private.num(p_payload->'covariance'->j->i))>1e-10*greatest(abs(price),1e-12) THEN
       RAISE EXCEPTION 'invalid covariance symmetry/diagonal' USING ERRCODE='23514';
     END IF;
   END LOOP;
   INSERT INTO pf_private.asset_results VALUES(r.run_id,a->>'ticker',pf_private.num(a->'observed_price'),
     pf_private.num(a->'predicted_price'),pf_private.num(a->'predicted_return'),
     pf_private.num(a->'weight'),a->'model',a->'recent_history');
   i:=i+1;
 END LOOP;
 -- Recheck after validation/inserts, immediately before becoming reader-visible.
 IF r.identity->>'mode'='live' AND clock_timestamp()>=r.target_open THEN
   RAISE EXCEPTION 'live publication deadline elapsed' USING ERRCODE='PT410';
 END IF;
 -- The run trigger checks the whole portfolio in this same transaction.
 UPDATE pf_private.runs SET state='published',payload=p_payload,
   result_sha256=pf_private.hash_json(p_payload),completed_at=p_completed_at,published_at=clock_timestamp()
 WHERE run_id=r.run_id;
 UPDATE pf_private.attempts SET state='published',finished_at=clock_timestamp(),diagnostics=p_diagnostics
 WHERE attempt_id=p_attempt_id AND run_id=r.run_id;
 RETURN jsonb_build_object('run_id',r.run_id,'state','published','idempotent',false);
END $$;

ALTER TABLE pf_private.runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE pf_private.asset_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE pf_private.snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE pf_private.attempts ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON SCHEMA pf_private FROM PUBLIC,anon,authenticated,service_role,portfolio_writer;
GRANT USAGE ON SCHEMA pf_private TO anon,authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA pf_private FROM PUBLIC,anon,authenticated,service_role,portfolio_writer;
GRANT SELECT ON pf_private.runs,pf_private.asset_results TO anon,authenticated;
CREATE POLICY published_runs ON pf_private.runs FOR SELECT TO anon,authenticated USING (state='published');
CREATE POLICY published_assets ON pf_private.asset_results FOR SELECT TO anon,authenticated
 USING (EXISTS(SELECT FROM pf_private.runs r WHERE r.run_id=asset_results.run_id AND r.state='published'));
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA pf_private FROM PUBLIC,anon,authenticated,service_role,portfolio_writer;
REVOKE ALL ON FUNCTION public.pf_access(),public.pf_lookup(jsonb,uuid),public.pf_snapshot(text),
 public.pf_attempt(uuid,uuid,timestamptz),public.pf_stage(jsonb,text,uuid,timestamptz),
 public.pf_fail(uuid,uuid,text),public.pf_publish(uuid,jsonb,uuid,timestamptz,jsonb)
 FROM PUBLIC,anon,authenticated,service_role,portfolio_writer;
GRANT EXECUTE ON FUNCTION public.pf_access() TO anon,authenticated,portfolio_writer;
GRANT EXECUTE ON FUNCTION public.pf_lookup(jsonb,uuid),public.pf_snapshot(text),
 public.pf_attempt(uuid,uuid,timestamptz),public.pf_stage(jsonb,text,uuid,timestamptz),
 public.pf_fail(uuid,uuid,text),public.pf_publish(uuid,jsonb,uuid,timestamptz,jsonb) TO portfolio_writer;
NOTIFY pgrst,'reload schema';

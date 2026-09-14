CREATE TABLE pf_private.outcomes (
 run_id uuid NOT NULL,
 ticker text NOT NULL,
 source_sha256 pf_private.sha256_hex NOT NULL REFERENCES pf_private.snapshots(snapshot_sha256),
 target date NOT NULL,
 observed_at timestamptz NOT NULL,
 state text NOT NULL CHECK (state IN ('matched','pending','incompatible')),
 actual_price pf_private.finite_float,
 reason text NOT NULL,
 basis_policy text NOT NULL CHECK (basis_policy='all_overlap_unchanged_v1'),
 PRIMARY KEY(run_id,ticker,source_sha256),
 FOREIGN KEY(run_id,ticker) REFERENCES pf_private.asset_results,
 CHECK ((state='matched' AND actual_price IS NOT NULL AND actual_price>0)
     OR (state IN ('pending','incompatible') AND actual_price IS NULL))
);
CREATE INDEX outcomes_latest ON pf_private.outcomes(run_id,ticker,observed_at DESC,source_sha256 DESC);
CREATE FUNCTION pf_private.outcome_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path = '' AS $$
BEGIN
 IF TG_OP<>'INSERT' THEN
   RAISE EXCEPTION 'outcome evidence is immutable' USING ERRCODE='23514';
 END IF;
 IF NOT EXISTS(SELECT FROM pf_private.runs r WHERE r.run_id=NEW.run_id
               AND r.state='published' AND r.target=NEW.target) THEN
   RAISE EXCEPTION 'outcome must match published forecast target' USING ERRCODE='23514';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER immutable_outcomes BEFORE INSERT OR UPDATE OR DELETE ON pf_private.outcomes
 FOR EACH ROW EXECUTE FUNCTION pf_private.outcome_guard();
CREATE FUNCTION public.pf_observe(p_run_id uuid,p_snapshot text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE r pf_private.runs; s jsonb:=p_snapshot::jsonb; original jsonb; identity jsonb;
 a jsonb; newer jsonb; actual jsonb; oldrow jsonb; newrow jsonb; h text;
 status text; reason text; price double precision; captured timestamptz;
BEGIN
 SELECT * INTO STRICT r FROM pf_private.runs WHERE run_id=p_run_id AND state='published';
 identity:=r.identity || jsonb_build_object(
   'mode',s->'request'->'mode','history_start',s->'request'->'history_start',
   'scientific_revision',s->'request'->'scientific_revision',
   'forecast',s->'request'->'forecast','allocation',s->'request'->'allocation',
   'data',s->'request'->'data','observation_cutoff',s->'plan'->'observation_cutoff',
   'forecast_target',s->'plan'->'forecast_target',
   'universe',(SELECT jsonb_agg(value ORDER BY value) FROM jsonb_array_elements(s->'request'->'tickers')));
 s:=pf_private.validate_snapshot(identity,p_snapshot);
 h:=encode(sha256(convert_to(p_snapshot,'UTF8')),'hex');
 INSERT INTO pf_private.snapshots(snapshot_sha256,content,data_sha256)
 VALUES(h,p_snapshot,s->>'data_sha256') ON CONFLICT DO NOTHING;
 SELECT content::jsonb INTO STRICT original FROM pf_private.snapshots WHERE snapshot_sha256=r.snapshot_sha256;
 FOR a IN SELECT value FROM jsonb_array_elements(original->'assets') LOOP
   SELECT value INTO newer FROM jsonb_array_elements(s->'assets') WHERE value->>'ticker'=a->>'ticker';
   SELECT max(pf_private.instant(value->>'retrieved_at')) INTO captured FROM jsonb_array_elements(s->'assets');
   status:='pending'; reason:='target_unavailable'; price:=NULL; actual:=NULL;
   IF newer IS NOT NULL THEN
     captured:=pf_private.instant(newer->>'retrieved_at');
     SELECT value INTO actual FROM jsonb_array_elements(newer->'observations')
       WHERE pf_private.day(value->>'session')=r.target;
   END IF;
   IF actual IS NOT NULL AND captured>=r.target_close THEN
     status:='matched'; reason:='exact_target_and_unchanged_overlap';
     IF newer->>'provider' IS DISTINCT FROM a->>'provider'
        OR newer->'metadata' IS DISTINCT FROM a->'metadata'
        OR s->>'price_basis' IS DISTINCT FROM original->>'price_basis' THEN
       status:='incompatible'; reason:='provenance_changed';
     ELSE
       FOR oldrow IN SELECT value FROM jsonb_array_elements(a->'observations') LOOP
         SELECT value INTO newrow FROM jsonb_array_elements(newer->'observations')
           WHERE value->>'session'=oldrow->>'session';
         IF newrow IS NULL THEN
           status:='incompatible'; reason:='insufficient_overlap'; EXIT;
         END IF;
         IF abs(pf_private.num(newrow->'price')-pf_private.num(oldrow->'price'))
            >1e-8+1e-10*abs(pf_private.num(oldrow->'price')) THEN
           status:='incompatible'; reason:='adjusted_history_changed'; EXIT;
         END IF;
       END LOOP;
     END IF;
     IF status='matched' THEN price:=pf_private.num(actual->'price'); END IF;
   END IF;
   INSERT INTO pf_private.outcomes VALUES(r.run_id,a->>'ticker',h,r.target,captured,status,price,reason,'all_overlap_unchanged_v1')
   ON CONFLICT DO NOTHING;
 END LOOP;
 RETURN jsonb_build_object('run_id',r.run_id,'source_sha256',h,
   'matched',(SELECT count(*) FROM pf_private.outcomes WHERE run_id=r.run_id AND source_sha256=h AND state='matched'),
   'pending',(SELECT count(*) FROM pf_private.outcomes WHERE run_id=r.run_id AND source_sha256=h AND state='pending'),
   'incompatible',(SELECT count(*) FROM pf_private.outcomes WHERE run_id=r.run_id AND source_sha256=h AND state='incompatible'));
END $$;

CREATE FUNCTION pf_private.asset_view(a pf_private.asset_results) RETURNS jsonb
LANGUAGE sql STABLE SET search_path = '' AS $$
 SELECT (to_jsonb(a)-'run_id') || jsonb_build_object('outcome',(
   SELECT to_jsonb(o)-'run_id'-'ticker' FROM pf_private.outcomes o
   WHERE o.run_id=a.run_id AND o.ticker=a.ticker
   ORDER BY o.observed_at DESC,o.source_sha256 DESC LIMIT 1))
$$;
CREATE FUNCTION public.pf_run(p_run_id uuid) RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
 SELECT jsonb_build_object('run_id',r.run_id,'request_key',r.request_key,'identity',r.identity,
   'state',r.state,'executed_at',r.executed_at,'completed_at',r.completed_at,'published_at',r.published_at,
   'target_open',r.target_open,'target_close',r.target_close,
   'input_provenance', (SELECT jsonb_build_object(
      'data_sha256',s.content::jsonb->'data_sha256',
      'price_basis',s.content::jsonb->'price_basis',
      'provider_options',s.content::jsonb->'provider_options',
      'assets',(SELECT jsonb_agg(value-'observations' ORDER BY value->>'ticker')
                FROM jsonb_array_elements(s.content::jsonb->'assets')))
      FROM pf_private.snapshots s WHERE s.snapshot_sha256=r.snapshot_sha256),
   'snapshot_sha256',r.snapshot_sha256,'result_sha256',r.result_sha256,'scientific_payload',r.payload,
   'assets',(SELECT jsonb_agg(pf_private.asset_view(a) ORDER BY a.ticker)
             FROM pf_private.asset_results a WHERE a.run_id=r.run_id))
 FROM pf_private.runs r WHERE r.run_id=p_run_id AND r.state='published'
$$;
CREATE FUNCTION pf_private.page(p_limit integer,p_cursor jsonb,p_as_of timestamptz,
                                p_ticker text,p_start date,p_end date) RETURNS jsonb
LANGUAGE plpgsql STABLE SET search_path = '' AS $$
DECLARE watermark timestamptz:=coalesce(p_as_of,statement_timestamp());
 cursor_target date; cursor_time timestamptz; cursor_id uuid; result jsonb;
BEGIN
 IF p_limit IS NULL OR p_limit<1 OR p_limit>100 OR watermark>statement_timestamp()+interval '1 second' THEN
   RAISE EXCEPTION 'page limit must be between 1 and 100; watermark cannot be future' USING ERRCODE='23514';
 END IF;
 IF p_ticker IS NOT NULL AND (p_ticker !~ '^[A-Z0-9]+([.-][A-Z0-9]+)*$'
    OR p_start IS NULL OR p_end IS NULL OR p_start>p_end) THEN
   RAISE EXCEPTION 'ticker history requires valid inclusive date bounds' USING ERRCODE='23514';
 END IF;
 IF p_cursor IS NOT NULL THEN
   cursor_target:=pf_private.day(p_cursor->>'target');
   cursor_time:=pf_private.instant(p_cursor->>'published_at');
   cursor_id:=(p_cursor->>'run_id')::uuid;
   IF cursor_id IS NULL THEN RAISE EXCEPTION 'missing page cursor ID' USING ERRCODE='23514'; END IF;
 END IF;
 WITH candidates AS (
   SELECT r.*,row_number() OVER(ORDER BY r.target DESC,r.published_at DESC,r.run_id DESC) AS ordinal
   FROM pf_private.runs r WHERE r.state='published' AND r.published_at<=watermark
    AND (p_cursor IS NULL OR (r.target,r.published_at,r.run_id)<(cursor_target,cursor_time,cursor_id))
    AND (p_ticker IS NULL OR (r.target BETWEEN p_start AND p_end AND EXISTS(
         SELECT FROM pf_private.asset_results a WHERE a.run_id=r.run_id AND a.ticker=p_ticker)))
   ORDER BY r.target DESC,r.published_at DESC,r.run_id DESC LIMIT p_limit+1
 ), entries AS (
   SELECT *,jsonb_build_object('run_id',run_id,'target',target,'observation_cutoff',cutoff,
     'executed_at',executed_at,'published_at',published_at,'universe',identity->'universe',
     'scientific_revision',identity->>'scientific_revision','mode',identity->>'mode')
     || CASE WHEN p_ticker IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('asset',(
        SELECT pf_private.asset_view(a) FROM pf_private.asset_results a
        WHERE a.run_id=candidates.run_id AND a.ticker=p_ticker)) END AS entry
   FROM candidates
 ) SELECT jsonb_build_object(
   'items',coalesce((SELECT jsonb_agg(entry ORDER BY ordinal) FROM entries WHERE ordinal<=p_limit),'[]'::jsonb),
   'as_of',watermark,'next_cursor',CASE WHEN (SELECT count(*) FROM candidates)>p_limit THEN (
      SELECT jsonb_build_object('target',target,'published_at',published_at,'run_id',run_id)
      FROM candidates WHERE ordinal=p_limit) ELSE NULL END,
   'requested_start',p_start,'requested_end',p_end)
 INTO result;
 RETURN result;
END $$;
CREATE FUNCTION public.pf_runs(p_limit integer DEFAULT 50,p_cursor jsonb DEFAULT NULL,p_as_of timestamptz DEFAULT NULL)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
 SELECT pf_private.page(p_limit,p_cursor,p_as_of,NULL,NULL,NULL)
$$;
CREATE FUNCTION public.pf_history(p_ticker text,p_start date,p_end date,p_limit integer DEFAULT 50,
                                 p_cursor jsonb DEFAULT NULL,p_as_of timestamptz DEFAULT NULL)
RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER SET search_path = '' AS $$
 SELECT pf_private.page(p_limit,p_cursor,p_as_of,p_ticker,p_start,p_end)
$$;
ALTER TABLE pf_private.outcomes ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON pf_private.outcomes FROM PUBLIC,anon,authenticated,service_role,portfolio_writer;
GRANT SELECT ON pf_private.outcomes TO anon,authenticated;
CREATE POLICY published_outcomes ON pf_private.outcomes FOR SELECT TO anon,authenticated
 USING (EXISTS(SELECT FROM pf_private.runs r WHERE r.run_id=outcomes.run_id AND r.state='published'));
REVOKE ALL ON FUNCTION pf_private.outcome_guard(),pf_private.asset_view(pf_private.asset_results),
 pf_private.page(integer,jsonb,timestamptz,text,date,date) FROM PUBLIC,anon,authenticated,service_role,portfolio_writer;
REVOKE ALL ON FUNCTION public.pf_observe(uuid,text),public.pf_run(uuid),
 public.pf_runs(integer,jsonb,timestamptz),public.pf_history(text,date,date,integer,jsonb,timestamptz)
 FROM PUBLIC,anon,authenticated,service_role,portfolio_writer;
GRANT EXECUTE ON FUNCTION public.pf_observe(uuid,text) TO portfolio_writer;
GRANT EXECUTE ON FUNCTION public.pf_run(uuid),public.pf_runs(integer,jsonb,timestamptz),
 public.pf_history(text,date,date,integer,jsonb,timestamptz) TO anon,authenticated,portfolio_writer;
NOTIFY pgrst,'reload schema';

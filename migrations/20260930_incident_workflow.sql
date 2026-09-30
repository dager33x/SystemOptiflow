-- Incident review and response tracking. Existing records/evidence are preserved.
BEGIN;
ALTER TABLE public.accidents ADD COLUMN IF NOT EXISTS review_status TEXT NOT NULL DEFAULT 'unreviewed';
ALTER TABLE public.accidents ADD COLUMN IF NOT EXISTS response_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE public.accidents ADD COLUMN IF NOT EXISTS reviewed_by UUID;
ALTER TABLE public.accidents ADD COLUMN IF NOT EXISTS reviewed_by_name TEXT;
ALTER TABLE public.accidents ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;
ALTER TABLE public.accidents ADD COLUMN IF NOT EXISTS review_note TEXT;
ALTER TABLE public.accidents ADD COLUMN IF NOT EXISTS response_by UUID;
ALTER TABLE public.accidents ADD COLUMN IF NOT EXISTS response_by_name TEXT;
ALTER TABLE public.accidents ADD COLUMN IF NOT EXISTS response_at TIMESTAMPTZ;
ALTER TABLE public.accidents ADD COLUMN IF NOT EXISTS response_note TEXT;
ALTER TABLE public.accidents ADD COLUMN IF NOT EXISTS workflow_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE public.accidents ADD COLUMN IF NOT EXISTS workflow_history JSONB NOT NULL DEFAULT '[]'::jsonb;

-- Support both historical schema variants without requiring legacy columns.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='accidents' AND column_name='resolved') THEN
        EXECUTE 'UPDATE public.accidents SET response_status=''resolved'' WHERE resolved IS TRUE AND workflow_version=0';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='accidents' AND column_name='status') THEN
        EXECUTE 'UPDATE public.accidents SET response_status=''resolved'' WHERE lower(status::text) IN (''resolved'', ''closed'') AND workflow_version=0';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.accidents'::regclass AND conname='accidents_review_status_check') THEN
        ALTER TABLE public.accidents ADD CONSTRAINT accidents_review_status_check
            CHECK (review_status IN ('unreviewed', 'confirmed', 'false_detection', 'needs_investigation'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.accidents'::regclass AND conname='accidents_response_status_check') THEN
        ALTER TABLE public.accidents ADD CONSTRAINT accidents_response_status_check
            CHECK (response_status IN ('pending', 'acknowledged', 'responding', 'resolved'));
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS idx_accidents_workflow ON public.accidents(response_status, review_status);
NOTIFY pgrst, 'reload schema';
COMMIT;

-- Run once in the existing project's Supabase SQL Editor.
-- Existing accounts keep their current access; only new registrations default to pending.
BEGIN;

ALTER TABLE public.users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS approval_status TEXT NOT NULL DEFAULT 'approved';
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS reviewed_by UUID;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ;
ALTER TABLE public.users ADD COLUMN IF NOT EXISTS rejection_reason TEXT;

ALTER TABLE public.users ALTER COLUMN approval_status SET DEFAULT 'pending';
ALTER TABLE public.users ALTER COLUMN is_active SET DEFAULT FALSE;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conrelid = 'public.users'::regclass AND conname = 'users_approval_status_check') THEN
        ALTER TABLE public.users ADD CONSTRAINT users_approval_status_check
            CHECK (approval_status IN ('pending', 'approved', 'rejected'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_users_approval_status ON public.users (approval_status, created_at);
NOTIFY pgrst, 'reload schema';
COMMIT;

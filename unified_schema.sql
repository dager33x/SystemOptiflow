-- SystemOptiflow Unified Database Schema
-- Includes Users and Reports tables

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. USERS TABLE
CREATE TABLE IF NOT EXISTS public.users (
    user_id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    first_name TEXT,
    last_name TEXT,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'operator', -- 'admin' or 'operator'
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_login TIMESTAMPTZ
);

ALTER TABLE public.users ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;

-- 2. VEHICLES TABLE (Traffic Flow)
CREATE TABLE IF NOT EXISTS public.vehicles (
    vehicle_id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    vehicle_type TEXT, -- 'car', 'truck', 'bus', 'motorcycle'
    lane INTEGER,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    speed FLOAT -- Estimted speed (optional)
);

-- 3. VIOLATIONS TABLE (Red Light/Speeding)
CREATE TABLE IF NOT EXISTS public.violations (
    violation_id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    vehicle_id UUID, -- Link to vehicle if possible (optional)
    violation_type TEXT NOT NULL, -- 'Red Light Violation', 'Speeding'
    lane INTEGER,
    source TEXT DEFAULT 'SYSTEM', -- 'SYSTEM' or 'MANUAL'
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    image_url TEXT -- Path to snapshot (optional)
);

-- 4. ACCIDENTS TABLE (Incident Reporting)
CREATE TABLE IF NOT EXISTS public.accidents (
    accident_id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    lane INTEGER,
    severity TEXT DEFAULT 'Moderate', -- 'Minor', 'Moderate', 'Severe'
    detection_type TEXT DEFAULT 'SYSTEM', -- 'SYSTEM' or 'MANUAL'
    description TEXT,
    reported_by TEXT, -- User ID or Name
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    resolved BOOLEAN DEFAULT FALSE,
    image_url TEXT
);

-- Migration for existing databases: run once if column does not exist
-- ALTER TABLE public.accidents ADD COLUMN IF NOT EXISTS image_url TEXT;

-- 5. EMERGENCY EVENTS TABLE (Ambulance/Fire)
CREATE TABLE IF NOT EXISTS public.emergency_events (
    event_id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    vehicle_type TEXT, -- 'ambulance', 'fire_truck', 'police'
    lane INTEGER,
    action_taken TEXT, -- 'Green Light Forced', etc.
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- 6. REPORTS TABLE (Issue Tracking)
CREATE TABLE IF NOT EXISTS public.reports (
    report_id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    priority TEXT CHECK (priority IN ('Low', 'Medium', 'High')) DEFAULT 'Medium',
    status TEXT CHECK (status IN ('Open', 'In Progress', 'Resolved', 'Closed')) DEFAULT 'Open',
    author_id UUID REFERENCES public.users(user_id) ON DELETE SET NULL,
    author_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 7. SYSTEM LOGS TABLE
CREATE TABLE IF NOT EXISTS public.system_logs (
    log_id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    event_type TEXT, -- 'ACCIDENT_DETECTED', 'VIOLATION_DETECTED', etc.
    description TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- 8. VERIFICATION CODES TABLE
CREATE TABLE IF NOT EXISTS public.verification_codes (
    verification_id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    email TEXT NOT NULL,
    username TEXT,
    code TEXT NOT NULL,
    code_type TEXT NOT NULL, -- 'signup' or 'reset_password'
    payload JSONB DEFAULT '{}'::jsonb,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 8. ROW LEVEL SECURITY (RLS)
-- Enable RLS
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vehicles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.violations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.accidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.emergency_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.system_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.verification_codes ENABLE ROW LEVEL SECURITY;

-- Policies for USERS
-- Allow users to view their own data
CREATE POLICY "Users can view own data" ON public.users
    FOR SELECT USING (auth.uid() = user_id);

-- Global Read Access for Dashboard Data
-- Allow all authenticated users to view reports
CREATE POLICY "Enable read access for all users" ON public.reports
    FOR SELECT TO authenticated USING (true);
CREATE POLICY "Enable read access for vehicles" ON public.vehicles FOR SELECT TO authenticated USING (true);
CREATE POLICY "Enable read access for violations" ON public.violations FOR SELECT TO authenticated USING (true);
CREATE POLICY "Enable read access for accidents" ON public.accidents FOR SELECT TO authenticated USING (true);
CREATE POLICY "Enable read access for emergency" ON public.emergency_events FOR SELECT TO authenticated USING (true);
CREATE POLICY "Enable read access for logs" ON public.system_logs FOR SELECT TO authenticated USING (true);
CREATE POLICY "Enable read access for verification codes" ON public.verification_codes FOR SELECT TO authenticated USING (true);

-- Insert Access for System/Authenticated Users
-- Allow authenticated users to insert reports
CREATE POLICY "Enable insert for authenticated users" ON public.reports
    FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Enable insert for vehicles" ON public.vehicles FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Enable insert for violations" ON public.violations FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Enable insert for accidents" ON public.accidents FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Enable insert for emergency" ON public.emergency_events FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Enable insert for logs" ON public.system_logs FOR INSERT TO authenticated WITH CHECK (true);
CREATE POLICY "Enable insert for verification codes" ON public.verification_codes FOR INSERT TO authenticated WITH CHECK (true);

-- Allow admins/authors to update reports
CREATE POLICY "Enable update for users based on email" ON public.reports
    FOR UPDATE TO authenticated USING (true);
CREATE POLICY "Enable update for verification codes" ON public.verification_codes
    FOR UPDATE TO authenticated USING (true);

-- 9. INDEXES
CREATE INDEX IF NOT EXISTS idx_reports_status ON public.reports(status);
CREATE INDEX IF NOT EXISTS idx_reports_priority ON public.reports(priority);
CREATE INDEX IF NOT EXISTS idx_users_username ON public.users(username);
CREATE INDEX IF NOT EXISTS idx_violations_lane ON public.violations(lane);
CREATE INDEX IF NOT EXISTS idx_violations_type ON public.violations(violation_type);
CREATE INDEX IF NOT EXISTS idx_accidents_time ON public.accidents(timestamp);
CREATE INDEX IF NOT EXISTS idx_accidents_lane ON public.accidents(lane);
CREATE INDEX IF NOT EXISTS idx_accidents_severity ON public.accidents(severity);
CREATE INDEX IF NOT EXISTS idx_violations_time ON public.violations(timestamp);
CREATE INDEX IF NOT EXISTS idx_verification_codes_email_type ON public.verification_codes(email, code_type);

-- ═══════════════════════════════════════════════════════════════════════════
-- 10. SUPABASE STORAGE SETUP
-- ═══════════════════════════════════════════════════════════════════════════
-- Storage buckets cannot be created via plain SQL.
-- Perform these steps ONCE in the Supabase Dashboard:
--
--   a) Go to Storage → New bucket
--      Name  : evidence
--      Public: YES  (images are served as public URLs in the dashboard)
--
--   b) Supabase Storage has its own RLS. The app uses the service_role key
--      (SUPABASE_SERVICE_ROLE_KEY) for server-side uploads, which bypasses
--      RLS entirely — no additional storage policy is needed for uploads.
--
--   c) Copy the service_role key from:
--        Supabase Dashboard → Project Settings → API → service_role (secret)
--      Add it to your .env file:
--        SUPABASE_SERVICE_ROLE_KEY=eyJ...
--
-- If you prefer to use the anon key instead, create these storage policies
-- in the Dashboard (Storage → Policies → evidence bucket):
--
--   INSERT policy  — allow anon uploads:
--     (bucket_id = 'evidence')
--
--   SELECT policy  — public reads (auto-enabled on public buckets):
--     (bucket_id = 'evidence')
-- ═══════════════════════════════════════════════════════════════════════════

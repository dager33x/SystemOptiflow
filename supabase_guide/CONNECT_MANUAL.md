# Supabase Connection & Setup Guide

This guide contains the manual commands required to connect the SystemOptiflow application to Supabase.

## 1. Database Setup (SQL Command)
Copy and paste the following SQL command into the **Supabase SQL Editor** to create all necessary tables and policies.

```sql
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
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_login TIMESTAMPTZ
);

-- 2. VEHICLES TABLE
CREATE TABLE IF NOT EXISTS public.vehicles (
    vehicle_id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    vehicle_type TEXT,
    lane INTEGER,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    speed FLOAT
);

-- 3. VIOLATIONS TABLE
CREATE TABLE IF NOT EXISTS public.violations (
    violation_id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    vehicle_id UUID,
    violation_type TEXT NOT NULL,
    lane INTEGER,
    source TEXT DEFAULT 'SYSTEM',
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    image_url TEXT
);

-- 4. ACCIDENTS TABLE
CREATE TABLE IF NOT EXISTS public.accidents (
    accident_id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    lane INTEGER,
    severity TEXT DEFAULT 'Moderate',
    detection_type TEXT DEFAULT 'SYSTEM',
    description TEXT,
    reported_by TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    resolved BOOLEAN DEFAULT FALSE,
    image_url TEXT
);

-- 5. EMERGENCY EVENTS TABLE
CREATE TABLE IF NOT EXISTS public.emergency_events (
    event_id UUID DEFAULT uuid_generate_v4() PRIMARY KEY,
    vehicle_type TEXT,
    lane INTEGER,
    action_taken TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- 6. REPORTS TABLE
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
    event_type TEXT,
    description TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- 8. ROW LEVEL SECURITY (RLS)
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vehicles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.violations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.accidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.emergency_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.system_logs ENABLE ROW LEVEL SECURITY;

-- Allow read access for dashboard
CREATE POLICY "Enable read access for all users" ON public.reports FOR SELECT USING (true);
CREATE POLICY "Enable read access for vehicles" ON public.vehicles FOR SELECT USING (true);
CREATE POLICY "Enable read access for violations" ON public.violations FOR SELECT USING (true);
CREATE POLICY "Enable read access for accidents" ON public.accidents FOR SELECT USING (true);
CREATE POLICY "Enable read access for emergency" ON public.emergency_events FOR SELECT USING (true);
CREATE POLICY "Enable read access for logs" ON public.system_logs FOR SELECT USING (true);
CREATE POLICY "Users can view own data" ON public.users FOR SELECT USING (auth.uid() = user_id);

-- Allow insert access for system
CREATE POLICY "Enable insert for authenticated users" ON public.reports FOR INSERT WITH CHECK (true);
CREATE POLICY "Enable insert for vehicles" ON public.vehicles FOR INSERT WITH CHECK (true);
CREATE POLICY "Enable insert for violations" ON public.violations FOR INSERT WITH CHECK (true);
CREATE POLICY "Enable insert for accidents" ON public.accidents FOR INSERT WITH CHECK (true);
CREATE POLICY "Enable insert for emergency" ON public.emergency_events FOR INSERT WITH CHECK (true);
CREATE POLICY "Enable insert for logs" ON public.system_logs FOR INSERT WITH CHECK (true);

-- Allow updates
CREATE POLICY "Enable update for users based on email" ON public.reports FOR UPDATE USING (true);
```

## 2. Connect Application (.env)
Create a file named `.env` in the project root directory and paste the following content. Replace the values with your project credentials.

```bash
SUPABASE_URL=your_project_url_here
SUPABASE_KEY=your_anon_public_key_here
# Service role key for server-side Storage uploads (bypasses RLS)
# Supabase Dashboard → Project Settings → API → service_role
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here
```

> **Security**: `SUPABASE_SERVICE_ROLE_KEY` is used only by the backend process. Never expose it in the browser or commit it to source control.

## 3. Supabase Storage Setup

Evidence images (violations, accidents) are uploaded to Supabase Storage. Complete these steps once in the Supabase Dashboard:

1. Go to **Storage → New bucket**
   - Name: `evidence`
   - Public bucket: **Yes** (images are served as public URLs in the dashboard)

2. Copy your **service_role** key from **Project Settings → API → service_role (secret)** and add it as `SUPABASE_SERVICE_ROLE_KEY` in your `.env` file. The app uses this key for server-side uploads, which bypasses bucket RLS automatically — no additional storage policies are required.

3. *(Optional — if not using service_role key)* Add these Storage policies on the `evidence` bucket under **Storage → Policies**:
   - `INSERT` for anon role: `(bucket_id = 'evidence')`
   - `SELECT` is covered automatically by the public bucket setting

4. Run this migration in the **SQL Editor** to add the `image_url` column to the accidents table if you already created the schema before this update:

```sql
ALTER TABLE public.accidents ADD COLUMN IF NOT EXISTS image_url TEXT;
```

## 4. Install Requirements
Run this command in your terminal to install the necessary libraries:

```bash
pip install -r requirements.txt
```

-- ==============================================================================
-- PROJECT: AFFILIATE MARKETING SYSTEM
-- DATABASE: SUPABASE (POSTGRESQL) - OPTIMIZED VERSION
-- ==============================================================================

-- 1. TẠO CÁC ENUM TYPES 
CREATE TYPE job_status AS ENUM ('pending', 'processing', 'completed', 'failed');
CREATE TYPE post_status AS ENUM ('idle', 'posting', 'posted', 'failed');
CREATE TYPE platform_type AS ENUM ('instagram', 'facebook', 'tiktok', 'douyin', 'xiaohongshu');

-- ==========================================
-- 2. TẠO BẢNG CRAWL_JOBS
-- ==========================================
CREATE TABLE public.crawl_jobs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    keyword VARCHAR(255) NOT NULL,
    platform platform_type DEFAULT 'instagram' NOT NULL,
    
    status job_status DEFAULT 'pending' NOT NULL,
    
    target_count INT DEFAULT 5, 
    found_count INT DEFAULT 0,  
    saved_count INT DEFAULT 0,  
    error_message TEXT,         
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ==========================================
-- 3. TẠO BẢNG VIDEOS
-- ==========================================
CREATE TABLE public.videos (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    job_id UUID REFERENCES public.crawl_jobs(id) ON DELETE CASCADE,
    
    keyword VARCHAR(255) NOT NULL,
    platform platform_type NOT NULL,
    
    source_id VARCHAR(255) NOT NULL, 
    source_url TEXT NOT NULL,        
    author_username VARCHAR(255),    
    original_caption TEXT,           
    
    storage_url TEXT NOT NULL,       
    thumbnail_url TEXT,              
    duration INT,                    
    
    post_status post_status DEFAULT 'idle' NOT NULL,
    affiliate_link TEXT,             
    posted_url TEXT,                 
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    CONSTRAINT unique_platform_source UNIQUE (platform, source_id)
);

-- Tạo Index để tăng tốc độ query cho Supabase
CREATE INDEX idx_crawl_jobs_status ON public.crawl_jobs(status);
CREATE INDEX idx_videos_job_id ON public.videos(job_id);
CREATE INDEX idx_videos_post_status ON public.videos(post_status);

-- ==========================================
-- 4. TẠO TRIGGER TỰ ĐỘNG UPDATE THỜI GIAN
-- ==========================================
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER set_updated_at_crawl_jobs
BEFORE UPDATE ON public.crawl_jobs
FOR EACH ROW EXECUTE PROCEDURE public.handle_updated_at();

CREATE TRIGGER set_updated_at_videos
BEFORE UPDATE ON public.videos
FOR EACH ROW EXECUTE PROCEDURE public.handle_updated_at();

-- ==========================================
-- 5. SUPABASE REALTIME CONFIGURATION
-- (Cho phép Next.js lắng nghe sự thay đổi data mà không cần load lại trang)
-- ==========================================
DO $$ 
BEGIN 
  IF NOT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
    CREATE PUBLICATION supabase_realtime;
  END IF;
END $$;

ALTER PUBLICATION supabase_realtime ADD TABLE public.crawl_jobs;
ALTER PUBLICATION supabase_realtime ADD TABLE public.videos;

-- ==========================================
-- 6. ROW LEVEL SECURITY (RLS) POLICIES
-- ==========================================
-- Bật tính năng bảo mật dòng (Bắt buộc trong Supabase)
ALTER TABLE public.crawl_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.videos ENABLE ROW LEVEL SECURITY;

-- Tạo Policy cho phép Đọc/Ghi thoải mái trong giai đoạn Test (Có thể siết lại sau)
-- Policy cho crawl_jobs
CREATE POLICY "Allow ALL on crawl_jobs" ON public.crawl_jobs
    FOR ALL
    USING (true)
    WITH CHECK (true);

-- Policy cho videos
CREATE POLICY "Allow ALL on videos" ON public.videos
    FOR ALL
    USING (true)
    WITH CHECK (true);
#This # 01. Project Overview - AM

**Tên dự án:** Affiliate Marketing Data Engine (Internal Name: AM)  
**Phiên bản hiện tại:** 1.0.0  
**Ngày cập nhật:** 04/05/2026  
**Owner:** AM Team

## Giới thiệu về AM

### AM là gì?

AM là 1 nền tảng về marketing chuyên về affiliate marketing. Workflow sẽ tập trung vào việc crawl các video sản phẩm trên social media, sau đó tích hợp gắn link shopee để thúc đẩy doanh thu, nhận tiền hoa hồng.

### Đối tượng của AM là ai?

Người dùng muốn thúc đẩy doanh số bán hàng từ các sản phẩm.

### Nhiệm vụ của AM là gì?

Chuyên về Affiliate Marketing. Nhưng ở phase đầu tiên có thể tập trung vào việc crawl các video sản phẩm trên social media ( instagram, facebook, xiaohongshu, douyin, tiktok ...), sau đó tích hợp gắn link shopee để thúc đẩy doanh thu, nhận tiền hoa hồng.

## 1. Mục tiêu kinh doanh (Business Objectives)

Tất cả các video được crawl về sẽ được gắn link shopee để thúc đẩy doanh thu, nhận tiền hoa hồng.

## 2. Stakeholders & User Persona

## 3. Phạm vi hiện tại (In-Scope / Out-of-Scope)

## 4. High-level Architecture (Tóm tắt)

Sourcecode này sử dụng Python technical stack chính cho AM.

- Dùng để viết script và sử dụng các thư viện để crawl video từ các từ khóa cho sẵn.
- Ở phase đầu tiên có thể sử dụng các nguồn đơn giản trước như instagram, có thể phát triển crawl các nguồn phức tạp sau như douyin, xiaohongshu, ...
- Trong thư mục database/db-schema.sql có chứa đoạn SQL để tạo database cho AM, hãy kiểm tra kỹ schema trước khi thực hiện bất kỳ tác vụ nào liên quan đến database.

- **Hướng dẫn sử dụng cho Agent:**

- Bạn là 1 Senior Data Engineer đang làm việc tại AM, bạn sẽ thực thi các tác vụ liên quan đến data engineering về affiliate marketing.
- Nhiệm vụ của bạn là crawl data từ các nguồn data social media và ghi chép vào Supabase.
- File này là “single source of truth” về tổng quan dự án.
- Trước khi làm bất kỳ task nào liên quan đến feature mới hoặc thay đổi architecture, phải đọc file này.
- Nếu phát hiện thông tin trong file này đã lỗi thời → báo cáo ngay và đề xuất cập nhật.

# PHASE 1

# Project Overview: Affiliate Marketing System - Data Engine (am-de)

## 1. AI Persona & Role

- **Role:** Senior Data Engineer & Web Scraping Expert (Python).
- **Task:** Xây dựng một engine crawler độc lập, chịu trách nhiệm nhận keyword, cào video từ mạng xã hội, lưu trữ và trả về kết quả.
- **Mindset:** Xử lý anti-scraping thông minh, tối ưu resource (memory/CPU), thiết kế background job queue (không block API), và handle retry/rate-limit.

## 2. Project Context & Workflow (Phase 1: Instagram)

1. Nhận yêu cầu chứa `keyword` từ hệ thống `am-fe`.
2. Khởi tạo Background Job đi tìm kiếm các Reels/Video trên Instagram theo `keyword` hoặc `hashtag`.
3. Tải video `.mp4` xuống local temp.
4. Upload video lên **Cloudinary** (lấy public URL).
5. Lưu thông tin (metadata, keyword, Cloudinary URL) vào Database (Supabase PostgreSQL) hoặc gọi Webhook trả về `am-fe`.
6. Xóa file temp ở local.

## 3. Tech Stack

- **Core Language:** Python 3.10+
- **API Framework:** FastAPI (để tạo endpoint nhận request từ `am-fe`).
- **Scraping Tools:** `Instaloader` (chính), `Playwright` (dự phòng).
- **Job Queue:** `Celery` + `Redis` (hoặc `RQ` nếu muốn setup nhẹ nhàng hơn lúc đầu).
- **Cloud Storage:** `cloudinary` python SDK.
- **Database/ORM:** `SQLAlchemy` (để update trạng thái job và lưu video link).

## 4. Phase 1 - Core Features (To-Do)

- **Feature 1: FastAPI Endpoint.** Tạo route `POST /api/jobs/crawl` nhận payload `{"keyword": "...", "platform": "instagram", "limit": 5}`.
- **Feature 2: Scraper Module.** Xây dựng class/service dùng `Instaloader` để lấy danh sách top posts theo hashtag/keyword. Cần có cơ chế load session/cookie từ clone accounts để tránh block.
- **Feature 3: Storage Module.** Tích hợp Cloudinary SDK để đẩy file video local lên cloud mượt mà.
- **Feature 4: Anti-ban Strategies.** Implement random delays (`time.sleep`), user-agent rotation, và error handling khi bị Instagram challenge (HTTP 429 / 400).

## 5. System Architecture Note

- Đây là một Worker Service. Nó phải có khả năng tự phục hồi (retry) nếu mạng lỗi hoặc bị rate limit.
- Tuyệt đối không dùng request đồng bộ chờ scrape xong mới trả response về FastAPI. Phải trả về `job_id` ngay lập tức, và worker chạy ngầm phía sau.

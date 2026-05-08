import sqlite3
import os
from instaloader import Instaloader

def import_session_from_path(username, profile_path, session_file_path):
    cookie_file = os.path.join(profile_path, 'cookies.sqlite')
    
    if not os.path.exists(cookie_file):
        print(f"[-] LỖI: Không tìm thấy file cookies.sqlite tại {cookie_file}")
        return

    try:
        print(f"[*] Đang đọc cookie từ: {cookie_file}")

        uri_path = cookie_file.replace('\\', '/')
        conn = sqlite3.connect(f"file:{uri_path}?immutable=1", uri=True)
        
        # SỬA LỖI Ở ĐÂY: Dùng host LIKE '%instagram.com' thay vì baseDomain
        cursor = conn.execute("SELECT name, value FROM moz_cookies WHERE host LIKE '%instagram.com'")
        cookie_data = dict(cursor)
        
        if not cookie_data:
            print("[-] LỖI: Không tìm thấy cookie Instagram! Hãy chắc chắn bạn ĐÃ ĐĂNG NHẬP Instagram trên Firefox.")
            return

        L = Instaloader()
        L.context._session.cookies.update(cookie_data)
        L.context.username = username
        L.save_session_to_file(session_file_path)
        print(f"\n[+] THÀNH CÔNG! Đã lưu session vào file: {session_file_path}")

    except Exception as e:
        print(f"\n[-] ĐÃ XẢY RA LỖI: {e}")

if __name__ == "__main__":
    print("=== CÔNG CỤ LẤY SESSION (PHIÊN BẢN FIREFOX MỚI) ===")
    USER = input("1. Nhập username Instagram: ").strip()
    
    print("\n2. Dán đường dẫn thư mục Profile Firefox")
    PROFILE_PATH = input("=> Đường dẫn: ").strip()
    
    PROFILE_PATH = PROFILE_PATH.strip('"').strip("'")
    SESSION_FILE = "instaloader_session"
        
    import_session_from_path(USER, PROFILE_PATH, SESSION_FILE)
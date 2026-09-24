import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.services import run_backup


app = create_app()
with app.app_context():
    location, manifest = run_backup()
    print(f"备份完成：{location}")
    print(f"数据库 SHA256：{manifest['database_sha256']}")
    print(f"附件文件数：{manifest['attachment_files']}")

import os
import sqlite3
import openpyxl
from PIL import Image

IMAGE_DIR = "/Users/okudasae/Documents/de-ta-base/static/images"
DB_FILE = "/Users/okudasae/Documents/de-ta-base/fe_study.db"
EXCEL_FILE = "/Users/okudasae/Documents/de-ta-base/fe_study_master_23sheets.xlsx"

MAX_SIZE_BYTES = 2 * 1024 * 1024  # 2MB
MAX_WIDTH = 1920                   # フルHD基準の最大幅

if not os.path.exists(IMAGE_DIR):
    print(f"❌ 画像フォルダが見つかりません: {IMAGE_DIR}")
    exit(1)

path_replacement_map = {}

print("==========================================")
print("🖼️ 1. .jpeg/.jpg から .png への変換処理")
print("==========================================")

all_files = os.listdir(IMAGE_DIR)
for filename in all_files:
    file_path = os.path.join(IMAGE_DIR, filename)
    if not os.path.isfile(file_path):
        continue

    base, ext = os.path.splitext(filename)
    ext_lower = ext.lower()

    if ext_lower in [".jpeg", ".jpg"]:
        new_filename = f"{base}.png"
        new_file_path = os.path.join(IMAGE_DIR, new_filename)

        try:
            with Image.open(file_path) as img:
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGBA")
                else:
                    img = img.convert("RGB")
                img.save(new_file_path, "PNG", optimize=True)

            os.remove(file_path)
            print(f"🔄 変換完了: {filename} -> {new_filename}")
            path_replacement_map[file_path] = new_file_path
            path_replacement_map[os.path.join("static/images", filename)] = os.path.join("static/images", new_filename)
        except Exception as e:
            print(f"⚠️ 変換エラー ({filename}): {e}")

print("\n==========================================")
print("📦 2. 2MB以上の画像ファイル圧縮処理")
print("==========================================")

compressed_count = 0
current_files = os.listdir(IMAGE_DIR)

for filename in current_files:
    file_path = os.path.join(IMAGE_DIR, filename)
    if not os.path.isfile(file_path):
        continue

    base, ext = os.path.splitext(filename)
    if ext.lower() not in [".png", ".jpg", ".jpeg", ".webp"]:
        continue

    file_size = os.path.getsize(file_path)

    # 2MB以上の場合のみ圧縮
    if file_size >= MAX_SIZE_BYTES:
        size_mb_before = file_size / (1024 * 1024)
        print(f"🔍 圧縮対象検出: {filename} ({size_mb_before:.2f} MB)")

        try:
            with Image.open(file_path) as img:
                w, h = img.size
                
                # 横幅が大きすぎる場合はリサイズ（LANCZOSリサンプリング）
                if w > MAX_WIDTH:
                    new_h = int(h * (MAX_WIDTH / w))
                    resample_filter = getattr(Image, 'Resampling', Image).LANCZOS
                    img = img.resize((MAX_WIDTH, new_h), resample_filter)

                # パレット減色（256色パレット化でPNG容量を激減、method引数は指定せずデフォルト最適値を使用）
                if img.mode != "RGB" and img.mode != "RGBA":
                    img = img.convert("RGBA")
                
                # quantizeで256色に圧縮（文字やアイコンの見た目はそのまま維持されます）
                img_opt = img.quantize(colors=256)
                img_opt.save(file_path, "PNG", optimize=True)

            size_mb_after = os.path.getsize(file_path) / (1024 * 1024)
            print(f"  ✅ 圧縮完了: {size_mb_before:.2f} MB -> {size_mb_after:.2f} MB")
            compressed_count += 1
        except Exception as e:
            print(f"  ⚠️ 圧縮エラー ({filename}): {e}")

print(f"\n🎉 2MB以上の圧縮完了: {compressed_count} 件")

# 3. データベースおよびExcel内の画像パス更新
if path_replacement_map:
    print("\n==========================================")
    print("🔄 3. DB & Excel 内の拡張子（.png）自動更新")
    print("==========================================")

    # DBの更新
    if os.path.exists(DB_FILE):
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        for old_p, new_p in path_replacement_map.items():
            cur.execute("UPDATE terms SET image_path = ? WHERE image_path = ?;", (new_p, old_p))
            old_name = os.path.basename(old_p)
            new_name = os.path.basename(new_p)
            cur.execute("UPDATE terms SET image_path = ? WHERE image_path LIKE ?;", (new_p, f"%{old_name}"))
        conn.commit()
        conn.close()
        print("✅ fe_study.db の画像パスを更新しました。")

    # Excelの更新
    if os.path.exists(EXCEL_FILE):
        wb = openpyxl.load_workbook(EXCEL_FILE)
        excel_updates = 0
        for sname in wb.sheetnames:
            ws = wb[sname]
            headers = [c.value for c in ws[1] if c.value]
            if "image_path" in headers:
                col_idx = headers.index("image_path") + 1
                for r in range(2, ws.max_row + 1):
                    val = str(ws.cell(row=r, column=col_idx).value or "")
                    for old_p, new_p in path_replacement_map.items():
                        old_name = os.path.basename(old_p)
                        if old_name in val:
                            ws.cell(row=r, column=col_idx, value=new_p)
                            excel_updates += 1
        wb.save(EXCEL_FILE)
        print(f"✅ Excelマスターの画像パスを更新しました（{excel_updates} 箇所）。")

print("\n✨ 全ての処理が正常に完了しました！")

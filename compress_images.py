import os
import glob
from PIL import Image

IMAGE_DIR = "static/images"
TARGET_WIDTH = 1280  # Web表示に十分な高解像度（横幅）
HISTORY_FILE = "compressed_images.txt"

if not os.path.exists(IMAGE_DIR):
    print(f"❌ フォルダが見つかりません: {IMAGE_DIR}")
    exit(1)

# 圧縮済み履歴の読み込み {ファイル名: 圧縮後のバイト数}
compressed_history = {}
if os.path.exists(HISTORY_FILE):
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) == 2:
                fname, fsize = parts
                compressed_history[fname] = int(fsize)

image_files = glob.glob(os.path.join(IMAGE_DIR, "*.png")) + \
              glob.glob(os.path.join(IMAGE_DIR, "*.jpg")) + \
              glob.glob(os.path.join(IMAGE_DIR, "*.jpeg"))

print(f"🔍 対象画像数: {len(image_files)} 枚（履歴登録済み: {len(compressed_history)} 枚）")
total_before = 0
total_after = 0
newly_compressed = 0
skipped_count = 0

for img_path in image_files:
    fname = os.path.basename(img_path)
    current_bytes = os.path.getsize(img_path)

    # すでに圧縮済みかつファイルサイズが変わっていなければスキップ
    if fname in compressed_history and compressed_history[fname] == current_bytes:
        skipped_count += 1
        continue

    file_size_before = current_bytes / (1024 * 1024)  # MB
    total_before += file_size_before

    try:
        with Image.open(img_path) as im:
            # RGBAの場合はRGBに変換（白背景）
            if im.mode in ("RGBA", "P"):
                im = im.convert("RGB")

            # リサイズ（横幅が1280pxより大きい場合のみ縮小）
            w, h = im.size
            if w > TARGET_WIDTH:
                new_h = int(h * (TARGET_WIDTH / w))
                im = im.resize((TARGET_WIDTH, new_h), Image.Resampling.LANCZOS)

            # 最適化して上書き保存
            im.save(img_path, format="PNG", optimize=True)

        after_bytes = os.path.getsize(img_path)
        file_size_after = after_bytes / (1024 * 1024)
        total_after += file_size_after
        newly_compressed += 1

        # 履歴を更新して即座に保存
        compressed_history[fname] = after_bytes
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            for k, v in sorted(compressed_history.items()):
                f.write(f"{k}\t{v}\n")

        print(f"✅ {fname}: {file_size_before:.2f} MB → {file_size_after:.2f} MB")
    except Exception as e:
        print(f"⚠️ スキップ ({fname}): {e}")

print("-" * 50)
print(f"🎉 処理完了！ 新規圧縮: {newly_compressed} 枚 / スキップ: {skipped_count} 枚")
if newly_compressed > 0:
    print(f"📦 新規圧縮分のサイズ変化: {total_before:.1f} MB → {total_after:.1f} MB")
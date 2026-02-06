import os

from PIL import Image


def remove_black_background(input_path, output_path, threshold=15):
    print(f"Processing {input_path}...")
    try:
        img = Image.open(input_path).convert("RGBA")
        datas = img.getdata()

        new_data = []
        for item in datas:
            # item is (R, G, B, A)
            # Check if pixel is close to black
            # We use a simple brightness sum or max component check
            if item[0] <= threshold and item[1] <= threshold and item[2] <= threshold:
                new_data.append((0, 0, 0, 0))  # Transparent
            else:
                new_data.append(item)

        img.putdata(new_data)
        img.save(output_path, "PNG")
        print(f"Saved to {output_path}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    # Hardcoded paths for the task
    input_file = r"c:\dev\guild_queue_bot\static\img\spider_arcane_ruby.png"
    output_file = r"c:\dev\guild_queue_bot\static\img\spider_arcane_ruby_transparent.png"

    if os.path.exists(input_file):
        remove_black_background(input_file, output_file)
    else:
        print(f"File not found: {input_file}")

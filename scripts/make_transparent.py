from PIL import Image


def make_transparent(input_path, output_path, tolerance=30):
    img = Image.open(input_path).convert("RGBA")
    datas = img.getdata()

    new_data = []

    # Get background color from top-left pixel
    bg_color = datas[0][:3]  # RGB
    print(f"Background color detected: {bg_color}")

    for item in datas:
        # Check if pixel is close to background color
        if all(abs(item[i] - bg_color[i]) < tolerance for i in range(3)):
            new_data.append((255, 255, 255, 0))  # Transparent
        else:
            new_data.append(item)

    img.putdata(new_data)

    # Resize to small icon size (e.g. 64x64) to save space, but keep quality high enough
    img.thumbnail((128, 128), Image.Resampling.LANCZOS)

    img.save(output_path, "PNG")
    print(f"Saved transparent image to {output_path}")


if __name__ == "__main__":
    input_file = r"C:/Users/Анастасия/.gemini/antigravity/brain/6cee865f-696c-4074-a7e9-65a932667ced/uploaded_media_1769599675216.jpg"
    output_file = r"c:/dev/guild_queue_bot/static/img/spider_obs.png"
    make_transparent(input_file, output_file)

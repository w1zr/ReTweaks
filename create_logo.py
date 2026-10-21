import os
from PIL import Image, ImageDraw, ImageFont

def generate_icon():
    os.makedirs("assets", exist_ok=True)
    size = (512, 512)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Clean dark rounded card base
    draw.rounded_rectangle([32, 32, 480, 480], radius=96, fill=(18, 18, 20, 255), outline=(60, 60, 65, 255), width=8)

    # Load system font for bold 'R'
    font = None
    for font_name in ["Segoe UI", "Arial", "Verdana"]:
        try:
            font = ImageFont.truetype(f"C:\\Windows\\Fonts\\{font_name.lower().replace(' ', '')}.ttf", 300)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()

    text = "R"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (size[0] - tw) // 2 - bbox[0]
    y = (size[1] - th) // 2 - bbox[1]

    draw.text((x, y), text, font=font, fill=(240, 240, 245, 255))

    ico_path = os.path.join("assets", "icon.ico")
    img.save(ico_path, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print(f"Proper multi-resolution Windows ICO saved to: {ico_path}")

if __name__ == "__main__":
    generate_icon()
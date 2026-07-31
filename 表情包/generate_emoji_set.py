import os
import argparse
from PIL import Image, ImageDraw, ImageFont

# Default texts for the 12 scenarios
DEFAULT_CAPTIONS = [
    "加个小需求",
    "求排期",
    "问题不大",
    "疯狂输出中",
    "这不科学啊",
    "收到，马上办",
    "我太难了",
    "大佬牛逼",
    "偷偷摸鱼",
    "顺利上线！",
    "还能再写两行",
    "下班，溜了！"
]

def find_font():
    # Candidates for bold Chinese fonts on macOS
    font_paths = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/Cache/PingFang.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    ]
    for fp in font_paths:
        if os.path.exists(fp):
            return fp
    return None

def process_single_emoji(input_path, text, output_path, target_size=1024, font_path=None):
    if not os.path.exists(input_path):
        print(f"Error: Source image {input_path} not found.")
        return False
        
    img = Image.open(input_path)
    width, height = img.size
    
    # Ensure square aspect ratio
    if width != height:
        size = min(width, height)
        img = img.crop(((width - size) // 2, (height - size) // 2, (width + size) // 2, (height + size) // 2))
        width, height = size, size
        
    # High-resolution work (we process at target_size, e.g. 1024x1024)
    img_large = img.resize((target_size, target_size), Image.Resampling.LANCZOS)
    
    # Bottom 20% calculation
    char_height = int(target_size * 0.8)
    text_height = target_size - char_height
    
    # Crop top 80% to preserve original proportions and cut off AI watermarks at the bottom
    char_img = img_large.crop((0, 0, target_size, char_height))
    
    # Sample background color (top-left corner)
    bg_color = char_img.getpixel((10, 10))
    
    # Create canvas with sampled background color
    canvas = Image.new("RGBA", (target_size, target_size), bg_color)
    canvas.paste(char_img, (0, 0))
    
    draw = ImageDraw.Draw(canvas)
    
    # Load Font
    font = None
    if font_path and os.path.exists(font_path):
        try:
            font_size = int(text_height * 0.45)
            font = ImageFont.truetype(font_path, font_size)
        except:
            pass
            
    if font is None:
        system_font = find_font()
        if system_font:
            try:
                font_size = int(text_height * 0.45)
                font = ImageFont.truetype(system_font, font_size)
            except:
                pass
                
    if font is None:
        font = ImageFont.load_default()
        
    # Text bounds and position
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
    except AttributeError:
        text_w, text_h = draw.textsize(text, font=font)
        
    text_x = (target_size - text_w) // 2
    text_y = char_height + (text_height - text_h) // 2 - int(text_height * 0.05)
    
    # Drawing outline text
    stroke_width = int(text_height * 0.06)
    draw.text(
        (text_x, text_y),
        text,
        font=font,
        fill=(0, 0, 0, 255),
        stroke_width=stroke_width,
        stroke_fill=(255, 255, 255, 255)
    )
    
    # Save as JPEG (revert to original format)
    canvas.convert("RGB").save(output_path, "JPEG", quality=95)
    
    file_size_kb = os.path.getsize(output_path) / 1024.0
    print(f"Processed: {os.path.basename(input_path)} -> {os.path.basename(output_path)} ({file_size_kb:.2f} KB, Size: {target_size}x{target_size})")
    return True

def process_directory(input_dir, output_dir, target_size=1024):
    os.makedirs(output_dir, exist_ok=True)
    
    # Find all image files in input directory
    valid_extensions = ('.png', '.jpg', '.jpeg', '.webp')
    image_files = sorted([
        f for f in os.listdir(input_dir)
        if f.lower().endswith(valid_extensions) and not f.startswith('.')
    ])
    
    if not image_files:
        print(f"Error: No images found in {input_dir}")
        return
        
    print(f"Found {len(image_files)} source images. Commencing processing pipeline at {target_size}x{target_size} px...")
    
    for i, img_file in enumerate(image_files):
        # Determine caption
        caption = DEFAULT_CAPTIONS[i % len(DEFAULT_CAPTIONS)]
        input_path = os.path.join(input_dir, img_file)
        
        # Name output sequentially (saved as jpg)
        output_name = f"emoji_{i + 1}.jpg"
        output_path = os.path.join(output_dir, output_name)
        
        process_single_emoji(input_path, caption, output_path, target_size=target_size)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="3D Clay Emoji Pipeline - Post Processing Script")
    parser.add_argument("--input_dir", type=str, required=True, help="Directory containing raw generated images")
    parser.add_argument("--output_dir", type=str, required=True, help="Output directory to save processed JPEG emojis")
    parser.add_argument("--size", type=int, default=1024, help="Target width and height of the output JPEG emoji (default: 1024)")
    
    args = parser.parse_args()
    process_directory(args.input_dir, args.output_dir, target_size=args.size)

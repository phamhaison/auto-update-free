#!/usr/bin/env python3
"""Create application icon for Auto-Update-Free"""
from PIL import Image, ImageDraw, ImageFont
import os

# Create a 256x256 icon
size = 256
img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Background - rounded rectangle with gradient-like effect
margin = 16
radius = 24
# Main background
draw.rounded_rectangle([margin, margin, size-margin, size-margin], radius=radius, 
                       fill=(25, 118, 210, 255))  # Blue primary

# Inner glow
draw.rounded_rectangle([margin+4, margin+4, size-margin-4, size-margin-4], radius=radius-4,
                       outline=(66, 165, 245, 180), width=2)

# Central icon - router/network symbol
cx, cy = size // 2, size // 2 - 10

# Draw network nodes (3 circles connected)
node_r = 18
node_color = (255, 255, 255, 230)
node_border = (25, 118, 210, 255)

# Left node (9router)
x1 = cx - 55
draw.ellipse([x1-node_r, cy-node_r, x1+node_r, cy+node_r], fill=node_color, outline=node_border, width=3)
# Label 9
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20)
except:
    font = ImageFont.load_default()
draw.text((x1, cy), "9", fill=node_border, font=font, anchor="mm")

# Center node (OmniRouter)
x2 = cx
draw.ellipse([x2-node_r, cy-node_r, x2+node_r, cy+node_r], fill=node_color, outline=node_border, width=3)
draw.text((x2, cy), "∞", fill=node_border, font=font, anchor="mm")

# Right node (OpenCode)
x3 = cx + 55
draw.ellipse([x3-node_r, cy-node_r, x3+node_r, cy+node_r], fill=node_color, outline=node_border, width=3)
# Draw code brackets
draw.text((x3, cy), "</>", fill=node_border, font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16) if os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf") else font, anchor="mm")

# Connection lines with arrows
line_color = (255, 255, 255, 200)
line_w = 4
# Left to center
draw.line([x1+node_r, cy, x2-node_r, cy], fill=line_color, width=line_w)
# Center to right
draw.line([x2+node_r, cy, x3-node_r, cy], fill=line_color, width=line_w)

# Arrow heads
arrow_size = 8
# Arrow from 9router to OmniRouter
ax = x2 - node_r
draw.polygon([(ax, cy), (ax+arrow_size, cy-arrow_size//2), (ax+arrow_size, cy+arrow_size//2)], fill=line_color)
# Arrow from OmniRouter to OpenCode
ax = x3 - node_r
draw.polygon([(ax, cy), (ax+arrow_size, cy-arrow_size//2), (ax+arrow_size, cy+arrow_size//2)], fill=line_color)

# Bottom text "FREE"
try:
    font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
except:
    font_small = ImageFont.load_default()
draw.text((cx, cy + 70), "FREE", fill=(255, 255, 255, 230), font=font_small, anchor="mm")
draw.text((cx, cy + 100), "MODELS", fill=(255, 255, 255, 180), font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16) if os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf") else font_small, anchor="mm")

# Save as PNG
png_path = os.path.join(os.path.dirname(__file__), "icon.png")
img.save(png_path, "PNG")
print(f"Saved icon.png: {png_path}")

# Also save as ICO for Windows compatibility
ico_path = os.path.join(os.path.dirname(__file__), "icon.ico")
img.save(ico_path, format='ICO', sizes=[(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)])
print(f"Saved icon.ico: {ico_path}")
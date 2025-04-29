from PIL import Image
from pathlib import Path

root_path = Path(r'C:\Program Files (x86)\SogouInput')


def fix_image_srgb_profile(file_path):
    img = Image.open(file_path)
    img.save(file_path, icc_profile=None)


png_list = list(root_path.glob("**/*.png"))
for png in png_list:
    fix_image_srgb_profile(png)

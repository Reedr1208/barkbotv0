import urllib.request
from PIL import Image
import os

url = "https://yiqiotjoyiedrwznmhgh.supabase.co/storage/v1/object/public/assets/chattyhound_logo.png"
logo_path = "public/chattyhound_logo.png"
favicon_path = "public/favicon_dog.png"

# Download the image
urllib.request.urlretrieve(url, logo_path)

# Open and crop the dog head
img = Image.open(logo_path)
width, height = img.size

# The logo is 1024x1024. The dog head is roughly in the top middle.
# Let's crop an area that contains just the head.
# By looking at the image, the dog head is roughly between x=250 to 750, y=100 to 600.
# We'll make it a square for a favicon.
# Let's crop from 230, 150 to 770, 690 to get a 540x540 square.
left = 230
top = 150
right = 770
bottom = 690
cropped = img.crop((left, top, right, bottom))
cropped.save(favicon_path)
print("Cropped favicon saved to", favicon_path)

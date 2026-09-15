"""Login-only tokens mirrored from the Verisade website's .dark CSS and brand.js."""
import colorsys
from pathlib import Path
import sys
import customtkinter as ctk
from PIL import Image, ImageDraw


def hsl(h, s, l):
    return '#' + ''.join(f'{round(c*255):02X}' for c in colorsys.hls_to_rgb(h/360,l/100,s/100))

BG = hsl(200,30,8)
CARD = hsl(200,28,11)
BORDER = hsl(200,22,20)
PRIMARY = hsl(243,75,68)
PRIMARY_INK = hsl(243,60,12)
HOVER = hsl(243,75,76)
WHITE = '#FFFFFF'

def white_on(background, opacity):
    return '#' + ''.join(f'{round(int(background[i:i+2],16)*(1-opacity)+255*opacity):02X}' for i in (1,3,5))

SECONDARY = white_on(CARD,.74)
QUIET = white_on(CARD,.58)
_loaded = False

def load_fonts():
    global _loaded
    if _loaded:
        return
    root = Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
    for path in (root/'assets/fonts').glob('*.ttf'):
        ctk.FontManager.load_font(str(path))
    _loaded = True

def face(size=14, bold=False, display=False):
    return ctk.CTkFont(family='Space Grotesk' if display else 'Inter', size=size,
                       weight='bold' if bold else 'normal')

def logo(size=36):
    # Exact 32-unit tile/check geometry from website components/brand/brand.js.
    scale=8
    image=Image.new('RGBA',(32*scale,32*scale))
    draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((0,0,32*scale-1,32*scale-1),radius=8*scale,fill=PRIMARY)
    points=[(round(x*scale),round(y*scale)) for x,y in [(9.1,15.1),(14.7,23.4),(22.9,8.6)]]
    draw.line(points,fill=(0,0,0,0),width=36,joint='curve')
    for x,y in points:
        draw.ellipse((x-18,y-18,x+18,y+18),fill=(0,0,0,0))
    image=image.resize((size*2,size*2),Image.Resampling.LANCZOS)
    return ctk.CTkImage(light_image=image,dark_image=image,size=(size,size))

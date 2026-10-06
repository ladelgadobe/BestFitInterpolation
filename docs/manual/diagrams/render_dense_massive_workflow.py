"""Render the dataset diagram with the original Quick Start visual style.

Requires Pillow and Arial. Run from any directory; it writes the referenced
PNG and an editable SVG alongside this script. The original workflow is untouched.
"""
from pathlib import Path
from html import escape
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SCALE = 2
WIDTH, HEIGHT = 1440, 1022
BLUE, GREEN, GOLD = '#1c3c88', '#00682e', '#a66b00'
INK, MUTED, LINE, ARROW = '#20242b', '#68707c', '#cfd5dc', '#8a929d'
GOLD_SOFT, PANEL = '#fff8e1', '#fafbfc'
image = Image.new('RGB', (WIDTH*SCALE, HEIGHT*SCALE), 'white')
draw = ImageDraw.Draw(image)
svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
       f'<rect width="{WIDTH}" height="{HEIGHT}" fill="white"/>']


def rect(x, y, w, h, fill='white', stroke=None, lw=1, radius=0):
    coords = tuple(round(v*SCALE) for v in (x, y, x+w, y+h))
    draw.rounded_rectangle(coords, radius=radius*SCALE, fill=fill,
                           outline=stroke, width=lw*SCALE)
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke or "none"}" stroke-width="{lw}"/>')


def line(points, color=LINE, lw=2):
    draw.line([(x*SCALE, y*SCALE) for x, y in points], fill=color, width=lw*SCALE)
    svg.append(f'<polyline points="{" ".join(f"{x},{y}" for x,y in points)}" fill="none" stroke="{color}" stroke-width="{lw}"/>')


def text(x, y, label, size=17, color=INK, bold=False, align='left'):
    font_path = Path('C:/Windows/Fonts') / ('arialbd.ttf' if bold else 'arial.ttf')
    font = ImageFont.truetype(str(font_path), size*SCALE)
    anchor = 'mt' if align == 'center' else 'lt'
    draw.text((x*SCALE, y*SCALE), label, font=font, fill=color, anchor=anchor)
    svg.append(f'<text x="{x}" y="{y}" font-family="Arial, Helvetica, sans-serif" font-size="{size}" font-weight="{"bold" if bold else "normal"}" fill="{color}" dominant-baseline="text-before-edge" text-anchor="{"middle" if align == "center" else "start"}">{escape(label)}</text>')


def circle_number(x, y, n, color):
    draw.ellipse(((x-15)*SCALE, (y-15)*SCALE, (x+15)*SCALE, (y+15)*SCALE), fill=color)
    svg.append(f'<circle cx="{x}" cy="{y}" r="15" fill="{color}"/>')
    text(x, y-8, str(n), size=16, color='white', bold=True, align='center')


def step(x, y, number, label, color, border, detail=None, conditional=False):
    rect(x, y, 590, 61, GOLD_SOFT if conditional else 'white',
         '#d7b96f' if conditional else border, radius=6)
    circle_number(x+32, y+28, number, color)
    text(x+59, y+13 if detail else y+21, label)
    if detail:
        text(x+59, y+36, detail, size=14,
             color=GOLD if conditional else MUTED, bold=conditional)


text(720, 46, 'Best Fit Interpolator: Dense and Massive Data', 34, BLUE, True, 'center')
text(720, 91, 'Keep parameter search, validation and final fitting distinct', 18, MUTED, align='center')

# Three profile cards use the same compact outlined nodes as Quick Start.
for x, label, bounds, color, fill in (
    (201, 'Normal', 'n ≤ 500', BLUE, 'white'),
    (533, 'Dense', '500 < n ≤ 10,000', BLUE, 'white'),
    (963, 'Massive', 'n > 10,000', GOLD, GOLD_SOFT),
):
    width = 374 if label == 'Dense' else 276
    rect(x, 141, width, 103, fill, color, lw=2, radius=6)
    text(x+width/2, 160, label, 19, color, True, 'center')
    text(x+width/2, 194, bounds, 17, MUTED, align='center')

for center in (339, 720, 1101):
    line([(center, 244), (center, 273)])
line([(339, 273), (1101, 273)])
line([(720, 273), (720, 302)])
text(720, 287, '↓', 25, ARROW, align='center')

rect(201, 322, 1038, 79, 'white', BLUE, lw=2, radius=6)
text(720, 337, 'Prepare and review the full valid population', 19, BLUE, True, 'center')
text(720, 368, 'Check CRS, predictor coverage, duplicates and explicit exclusions', 16, MUTED, align='center')
line([(720, 401), (720, 421), (381, 421), (381, 440)])
line([(720, 421), (1060, 421), (1060, 440)])

# Preserve the original blue/green branches, circular numbers and yellow notes.
for x, center, color, title, intro, border in (
    (64, 381, BLUE, 'Model Search', 'Bound tuning and review the resolved parameters.', '#9fb2df'),
    (742, 1059, GREEN, 'Validation', 'Read the actual strategy and test population.', '#9bc4ab'),
):
    rect(x, 440, 634, 333, PANEL)
    rect(x, 440, 634, 5, color)
    text(center, 461, title, 24, color, True, 'center')
    text(center, 495, intro, 16, MUTED, align='center')

step(86, 526, 1, 'Configure a bounded model search', BLUE, '#9fb2df')
text(381, 590, '↓', 25, ARROW, align='center')
step(86, 611, 2, 'Use up to 2,000 valid rows for tuning', BLUE, '#9fb2df',
     'A tuning subset supports the parameter search', True)
text(381, 675, '↓', 25, ARROW, align='center')
step(86, 696, 3, 'Review the resolved model parameters', BLUE, '#9fb2df')

step(764, 526, 1, 'Read the validation strategy and sample count', GREEN, '#9bc4ab')
text(1059, 590, '↓', 25, ARROW, align='center')
step(764, 611, 2, 'Massive data: hold out about 20%', GREEN, '#9bc4ab',
     'Up to 10,000 test observations', True)
text(1059, 675, '↓', 25, ARROW, align='center')
step(764, 696, 3, 'Review validation before accepting the result', GREEN, '#9bc4ab')

line([(381, 773), (381, 798), (1059, 798), (1059, 773)])
line([(720, 798), (720, 820)])
text(720, 811, '↓', 25, ARROW, align='center')
rect(201, 847, 1038, 79, 'white', BLUE, lw=2, radius=6)
text(720, 863, "Final fit uses the model's full valid population", 19, BLUE, True, 'center')
text(720, 894, 'Predict in blocks → compare aligned maps → export', 17, MUTED, align='center')

rect(64, 942, 1312, 38, GOLD_SOFT)
rect(64, 942, 5, 38, GOLD)
text(720, 954, 'Important: A preview sample does not define the fitting population.', 17, INK, align='center')

svg.append('</svg>')
(HERE/'dense_massive_workflow.svg').write_text('\n'.join(svg)+'\n', encoding='utf-8')
output = HERE.parent/'figures/dense_massive_workflow.png'
image.save(output, dpi=(192, 192))
print(output)

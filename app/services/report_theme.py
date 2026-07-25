import matplotlib

# Use a non-interactive backend for matplotlib
matplotlib.use('Agg')

from matplotlib.colors import LinearSegmentedColormap, to_rgb
from matplotlib.patches import Rectangle
import matplotlib.patches as patches

baseball_width = 0.24  # Approximate width of a baseball in feet

THEME_COLORS = {
    'light': {
        'figure.facecolor': 'none',
        'figure.edgecolor': 'none',
        'axes.facecolor':   'none',
        'text.color':       '#111111',
        'axes.edgecolor':   '#111111',
        'axes.titlecolor':  '#111111',
        'axes.labelcolor':  '#111111',
        'xtick.color':      '#444444',
        'ytick.color':      '#444444',
        'grid.color':       '#444444',
        'grid.alpha':       0.3,
    },
    'dark': {
        'figure.facecolor': 'none',
        'figure.edgecolor': 'none',
        'axes.facecolor':   'none',
        'text.color':       '#e0e0e0',
        'axes.edgecolor':   '#e0e0e0',
        'axes.titlecolor':  '#e0e0e0',
        'axes.labelcolor':  '#e0e0e0',
        'xtick.color':      '#aaaaaa',
        'ytick.color':      '#aaaaaa',
        'grid.color':       '#aaaaaa',
        'grid.alpha':       0.3,
    },
}

matplotlib.rcParams.update({
    'font.family': 'Cambria',
    'font.size': 18,
    'font.weight': 'bold',
})

# Order to display pitch types in tables and plots
pitch_order = {
    'Fastball': 'FB',
    'Curveball': 'CB',
    'Slider': 'SL',
    'ChangeUp': 'CH',
    'Splitter': 'SP',
    'Knuckleball': 'KB',
    'Cutter': 'CT',
    'Sinker': 'SK',
    'Four-Seam': 'FF',
    'Undefined': 'UN'
}
    
pitch_point_colors = {
    'Fastball': '#d22d49',
    'Curveball': '#00d1ed',
    'Slider': '#004400',
    'ChangeUp': '#1dbe3a',
    'Splitter': '#4f0010',
    'Knuckleball': '#472cee',
    'Cutter': '#933f2c',
    'Sinker': '#fe9d00',
    'Four-Seam': '#FF0088',
    'Undefined': '#888888'
}

def make_strike_zone():
    return Rectangle((-0.83, 1.5), 1.66, 2.0,
        linewidth=2, edgecolor=matplotlib.rcParams['text.color'], facecolor='none', linestyle='--')

def make_shadow_zone():
    return Rectangle(
        (-0.83 - baseball_width, 1.5 - baseball_width),
        1.66 + 2 * baseball_width, 2.0 + 2 * baseball_width,
        linewidth=1, edgecolor=matplotlib.rcParams['xtick.color'], facecolor='none', linestyle=(0, (1, 10)))

def make_homeplate():
    return patches.Polygon([(-0.35, 0.025), (0.35, 0.025), (0.35, 0.45), (0, 0.8), (-0.35, 0.45)],
        linewidth=1, edgecolor=matplotlib.rcParams['xtick.color'], facecolor='none', linestyle='-')

def cmap(hex_color, name):
    # Build a transparency gradient from fully transparent to the pitch color,
    # so overlapping KDE fills blend cleanly on the white plot background
    r, g, b = to_rgb(hex_color)
    return LinearSegmentedColormap.from_list(name, [(r, g, b, 0), (r, g, b, 1)])

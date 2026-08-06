#!/usr/bin/env python3
"""Generate docs/logo.svg and docs/banner.svg.

The mark is a manifest read by a cephalopod whose arms each end in an Application: one values file, an
orchestrator, N objects. The arms are TAPERED, which is what makes them read as tentacles rather than as
wires — and a taper cannot be a stroke in SVG, so each arm is a filled polygon offset from a Bezier
centreline. Those polygons are ~60 points; editing them by hand is not realistic, hence this script.

    python3 docs/build-logo.py

The cephalopod is an original drawing, NOT the Argo mark. Argo is a CNCF project and its logo is a Linux
Foundation trademark: referring to the project is fine, incorporating its logo into another project's
branding is not.

The GitLab project avatar has to be a raster (SVG is not in GitLab's avatar allowlist):

    rsvg-convert -w 512 -h 512 docs/logo.svg -o docs/logo.png    # brew install librsvg
"""

import math
import pathlib

PLATE = "#14213D"   # avatar backplate — an avatar needs its own background to read on any theme
PAPER = "#F8FAFC"   # the manifest
SLATE = "#94A3B8"   # its fold and its lines
ORANGE = "#EF7B4D"  # the cephalopod and the Applications: one continuous system

DOCS = pathlib.Path(__file__).resolve().parent

# --- Geometry, in a 96x96 viewBox --------------------------------------------------------------------
# Ink spans x 12..86 and y 16..80, centred on (49, 48). Everything below is expressed in these units.
# (cubic centreline, base half-width, tip half-width). Keep the control points MONOTONIC in x: a second
# control point left of the first folds the curve back on itself and the offset outline shows a cusp.
ARMS = [
    (((55, 44), (63, 38), (67, 28), (73, 23)), 3.4, 1.3),
    (((57, 49), (63, 50), (68, 46), (73, 48)), 3.6, 1.4),
    (((54, 55), (63, 62), (68, 70), (73, 73)), 3.4, 1.3),
]
MANTLE = (50, 48, 9.5, 13.5)          # cx, cy, rx, ry
EYES = ((46.5, 49), (53.5, 49), 2.6)  # left, right, radius
OUTPUTS = (74, (23, 48, 73), 13)      # x, centres, side


def _bezier(pts, t):
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = pts
    u = 1 - t
    return (
        u**3 * x0 + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t**3 * x3,
        u**3 * y0 + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t**3 * y3,
        3 * u * u * (x1 - x0) + 6 * u * t * (x2 - x1) + 3 * t * t * (x3 - x2),
        3 * u * u * (y1 - y0) + 6 * u * t * (y2 - y1) + 3 * t * t * (y3 - y2),
    )


def arm_path(pts, w0, w1, steps=28):
    """Offset the centreline by a half-width that shrinks towards the tip, then close with a round cap."""
    left, right = [], []
    for i in range(steps + 1):
        t = i / steps
        x, y, dx, dy = _bezier(pts, t)
        norm = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / norm, dx / norm
        w = w0 + (w1 - w0) * (t**0.7)   # fast taper first, easing towards the tip
        left.append((x + nx * w, y + ny * w))
        right.append((x - nx * w, y - ny * w))
    # The cap sweeps from the left offset point THROUGH the tangent direction to the right one. The left
    # normal is the tangent rotated +90 degrees, so that path decreases the angle — sweep-flag 0 in SVG's
    # y-down frame. Flag 1 bulges the cap backwards and leaves a nub on one edge of the tip.
    d = "M%.2f %.2f" % left[0] + "".join(" L%.2f %.2f" % p for p in left[1:])
    d += " A%.2f %.2f 0 0 0 %.2f %.2f" % (w1, w1, right[-1][0], right[-1][1])
    return d + "".join(" L%.2f %.2f" % p for p in reversed(right[:-1])) + " Z"


def mantle_path(cx, cy, rx, ry):
    """Egg rather than dome: a pale dome with two dark eyes reads as a skull, an egg reads as a head."""
    return (
        f"M{cx} {cy - ry}"
        f"C{cx + rx} {cy - ry} {cx + rx} {cy - ry * 0.1:.2f} {cx + rx * 0.82:.2f} {cy + ry * 0.55:.2f}"
        f"C{cx + rx * 0.6:.2f} {cy + ry} {cx - rx * 0.6:.2f} {cy + ry} {cx - rx * 0.82:.2f} {cy + ry * 0.55:.2f}"
        f"C{cx - rx} {cy - ry * 0.1:.2f} {cx - rx} {cy - ry} {cx} {cy - ry}Z"
    )


def mark(paper, fold, rule, creature, eye_iris, eye_glint):
    """The mark, unindented, without a backplate. Colours are passed in so the banner can invert."""
    (lx, ly), (rx_, ry_), er = EYES
    ox, ocs, os_ = OUTPUTS
    out = [
        "  <!-- One manifest. The folded corner is what still reads as a document once the lines are",
        "       too small to see. -->",
        f'  <path d="M16 22h16l8 8v40a4 4 0 0 1-4 4H16a4 4 0 0 1-4-4V26a4 4 0 0 1 4-4z" fill="{paper}"/>',
        f'  <path d="M32 22l8 8h-8z" fill="{fold}"/>',
        f'  <g fill="{rule}">',
        '    <rect x="18" y="40" width="14" height="3" rx="1.5"/>',
        '    <rect x="18" y="47" width="9" height="3" rx="1.5"/>',
        '    <rect x="18" y="54" width="11" height="3" rx="1.5"/>',
        "  </g>",
        "",
        "  <!-- Read by a cephalopod whose arms each end in an Application. The fan-out an ApplicationSet",
        "       performs, drawn rather than described. -->",
        f'  <path d="{mantle_path(*MANTLE)}" fill="{creature}"/>',
    ]
    for pts, w0, w1 in ARMS:
        out.append(f'  <path d="{arm_path(pts, w0, w1)}" fill="{creature}"/>')
    for cx, cy in ((lx, ly), (rx_, ry_)):
        out.append(f'  <circle cx="{cx}" cy="{cy}" r="{er}" fill="{eye_iris}"/>')
        out.append(
            f'  <circle cx="{cx - er * 0.3:.2f}" cy="{cy - er * 0.34:.2f}" '
            f'r="{er * 0.36:.2f}" fill="{eye_glint}"/>'
        )
    out += ["", "  <!-- The generated Applications. -->", f'  <g fill="{ORANGE}">']
    for cy in ocs:
        out.append(f'    <rect x="{ox}" y="{cy - os_ / 2:.1f}" width="{os_}" height="{os_}" rx="{os_ / 4:.2f}"/>')
    out.append("  </g>")
    return "\n".join(out)


HEADER = "<!-- Generated by docs/build-logo.py — edit that, not this. -->"


def logo_svg():
    body = mark(PAPER, SLATE, SLATE, ORANGE, PLATE, PAPER)
    return f"""{HEADER}
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96" width="512" height="512" role="img"
     aria-label="chargo">
  <title>chargo</title>
  <desc>A manifest read by a cephalopod whose arms each end in an application.</desc>
  <rect width="96" height="96" rx="20" fill="{PLATE}"/>
{body}
</svg>
"""


def banner_svg():
    # No backplate: a README banner sits on the page background, so the manifest inverts with the theme
    # instead of carrying its own. The CREATURE does not — orange mantle, navy eyes, white glint in both
    # themes, exactly as on the avatar. A mark that changed treatment between themes would be two marks.
    body = mark("var(--paper)", "var(--fold)", "var(--rule)", ORANGE, PLATE, PAPER)
    body = "\n".join("  " + line if line else line for line in body.splitlines())
    return f"""{HEADER}
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 168" width="640" height="168" role="img"
     aria-label="chargo — one values file, every ArgoCD object of a platform">
  <title>chargo</title>
  <style>
    :root {{
      --paper: #1E293B; --fold: #475569; --rule: #94A3B8;
      --word: #0F172A; --tag: #64748B;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --paper: #E2E8F0; --fold: #94A3B8; --rule: #475569;
        --word: #F1F5F9; --tag: #94A3B8;
      }}
    }}
    .word {{ fill: var(--word) }}
    .tag {{ fill: var(--tag) }}
  </style>

  <g transform="translate(24 36)">
{body}
  </g>

  <!-- System font stack: an SVG loaded through <img> cannot fetch a webfont, and embedding one would put
       a few hundred kB in the repo for two lines of text. -->
  <g font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, Roboto, Helvetica, Arial, sans-serif">
    <text class="word" x="146" y="88" font-size="56" font-weight="700" letter-spacing="-1.5">chargo</text>
    <text class="tag" x="148" y="120" font-size="16">One values file → every ArgoCD object of a platform</text>
  </g>
</svg>
"""


if __name__ == "__main__":
    (DOCS / "logo.svg").write_text(logo_svg())
    (DOCS / "banner.svg").write_text(banner_svg())
    print("wrote docs/logo.svg and docs/banner.svg")

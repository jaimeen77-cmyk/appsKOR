#!/usr/bin/env python3
"""render_cars.py - the car Modern wide's road draws (the driving-assistant view), rendered once here and shipped
as a small texture atlas (apps/cluster_layouts/car_sprite.js); the cluster only samples it.

A generic modern SUV of our own (no maker's design): a signed distance field of rounded boxes (a lower body with
wheel arches, a cabin narrowing to the roof, the wheels), seen from behind and above as the road's camera sees
it, ray marched with soft lighting (a key light, the sky, ambient occlusion, a clear-coat highlight and a rim of
light) and its contact shadow on the road. The channels are kept apart so the cluster can colour each car:
  R  the shading (light on a white body), G  the tail lights, B  the glass, A  coverage (body and shadow)
Each level is half the one before (for cars further away), packed in one atlas row.

  python3 tools/render_cars.py [--preview out.png]
"""
import base64, json, math, os, sys, zlib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'apps', 'cluster_layouts', 'car_sprite.js')

W0, H0 = 256, 192          # the largest level's size in the atlas
SS = int(os.environ.get('SS', 3))   # supersampling


def rbox(p, c, b, r):
    q = np.abs(p - c) - (b - r)
    return np.linalg.norm(np.maximum(q, 0.0), axis=-1) + np.minimum(np.max(q, axis=-1), 0.0) - r


def smin(a, b, k):
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


def smax(a, b, k):
    return -smin(-a, -b, k)


def cyl_x(p, c, r, hw):
    """a cylinder along x (a wheel): radius r, half width hw"""
    q = p - c
    d = np.stack([np.sqrt(q[..., 1] ** 2 + q[..., 2] ** 2) - r, np.abs(q[..., 0]) - hw], -1)
    return np.minimum(np.max(d, -1), 0.0) + np.linalg.norm(np.maximum(d, 0.0), axis=-1)


AX = np.array([1.0, 0.0, 0.0])


def body_sdf(p):
    """metres: x across (+ right), y up, z forward. An SUV 4.9 long, 1.95 wide, 1.72 high."""
    pl = p.copy()
    pl[..., 0] = p[..., 0] * (1.0 + np.clip(0.62 - p[..., 1], 0.0, 1.0) * 0.18)
    lower = rbox(pl, np.array([0.0, 0.7, 0.0]), np.array([0.975, 0.36, 2.45]), 0.28)
    # the cabin narrows towards the roof (tumblehome) and its back slopes
    pc = p.copy()
    pc[..., 0] = p[..., 0] * (1.0 + np.clip(p[..., 1] - 1.0, 0.0, 1.0) * 0.32)
    pc[..., 2] = p[..., 2] - np.clip(p[..., 1] - 1.05, 0.0, 1.0) * 0.55
    cabin = rbox(pc, np.array([0.0, 1.3, -0.1]), np.array([0.84, 0.34, 1.5]), 0.3)
    d = smin(lower, cabin, 0.2)
    # wheel arches
    for sx in (-1, 1):
        for sz in (-1, 1):
            arch = cyl_x(p, np.array([sx * 0.98, 0.4, sz * 1.5]), 0.47, 0.2)
            d = smax(d, -arch, 0.05)
    return d


def wheels_sdf(p):
    d = np.full(p.shape[:-1], 1e3)
    for sx in (-1, 1):
        for sz in (-1, 1):
            d = np.minimum(d, cyl_x(p, np.array([sx * 0.84, 0.4, sz * 1.5]), 0.39, 0.12) - 0.03)
    return d


def scene(p):
    b, w = body_sdf(p), wheels_sdf(p)
    return np.minimum(b, w), b, w


def normal(p):
    e = 1e-3
    n = np.stack([scene(p + e * np.eye(3)[i])[0] - scene(p - e * np.eye(3)[i])[0] for i in range(3)], -1)
    return n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-9)


def render(w, h):
    # the road's camera: behind and above, a long lens (little distortion)
    cam = np.array([0.0, 3.0, -10.5])
    look = np.array([0.0, 0.8, 0.5])
    fwd = (look - cam) / np.linalg.norm(look - cam)
    right = np.cross(np.array([0.0, 1.0, 0.0]), fwd); right /= np.linalg.norm(right)
    up = np.cross(fwd, right)
    fov = math.radians(19.0)
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
    u = ((xs + 0.5) / w - 0.5) * 2.0 * math.tan(fov / 2) * (w / h)
    v = (0.5 - (ys + 0.5) / h) * 2.0 * math.tan(fov / 2)
    v = v - 0.04      # the car low in its frame: its shadow below, room above
    dirs = fwd + u[..., None] * right + v[..., None] * up
    dirs /= np.linalg.norm(dirs, axis=-1, keepdims=True)
    t = np.zeros((h, w)); hit = np.zeros((h, w), bool); alive = np.ones((h, w), bool)
    for _ in range(140):
        p = cam + dirs * t[..., None]
        d, _, _ = scene(p)
        hit |= alive & (d < 1e-3)
        alive &= ~hit & (t < 30)
        t = np.where(alive, t + d * 0.9, t)
    p = cam + dirs * t[..., None]
    _, db, dw = scene(p)
    isw = hit & (dw <= db)
    n = normal(p)
    # light: a key from above, ahead and to the left; the sky; ambient occlusion from the field
    L = np.array([-0.35, 0.85, 0.4]); L /= np.linalg.norm(L)
    ndl = np.clip((n * L).sum(-1), 0.0, 1.0)
    sky = np.clip(0.55 + 0.45 * n[..., 1], 0.0, 1.0)
    ao = np.ones((h, w))
    for i in range(1, 6):
        s = 0.06 * i
        ao -= (s - scene(p + n * s)[0]) / (2.0 ** i) * 2.2
    ao = np.clip(ao, 0.25, 1.0)
    vdir = -dirs
    hv = L + vdir; hv /= np.linalg.norm(hv, axis=-1, keepdims=True)
    spec = np.clip((n * hv).sum(-1), 0.0, 1.0) ** 60 * 0.9
    fres = (1.0 - np.clip((n * vdir).sum(-1), 0.0, 1.0)) ** 4
    # a broad soft reflection of the sky along the upper surfaces (clear coat)
    refl = np.clip(n[..., 1], 0.0, 1.0) ** 3 * 0.25
    # a horizon's reflection along the sides and the tailgate (a light band), a groove under the rear window
    horizon = np.exp(-((n[..., 1] - 0.05) / 0.18) ** 2) * 0.18
    shade = (0.10 + 0.40 * ndl + 0.24 * sky) * ao + spec * 0.6 + refl + 0.22 * fres + horizon
    # materials: tyres dark; the glass (the cabin above the waist, facing back or up); the tail lights (a band
    # across the back at the top of the lower body, and down the corners)
    y, z, x = p[..., 1], p[..., 2], p[..., 0]
    back = n[..., 2] < -0.35
    glass = hit & ~isw & (y > 1.06) & (y < 1.58) & (np.abs(x) < 0.82) & ((n[..., 2] < -0.25) | (np.abs(n[..., 0]) > 0.55)) & (n[..., 1] < 0.85)
    lights = hit & ~isw & back & (((y > 0.9) & (y < 0.95) & (np.abs(x) < 0.9)) | ((y > 0.82) & (y < 0.97) & (np.abs(x) > 0.66) & (np.abs(x) < 0.95)))
    shade = np.where(isw, 0.08 + 0.12 * ndl * ao + spec * 0.3, shade)
    # the contact shadow on the road (y = 0) where no car is: a soft dark pool under the body
    tg = np.where(dirs[..., 1] < 0, -cam[1] / np.minimum(dirs[..., 1], -1e-6), 1e9)
    g = cam + dirs * tg[..., None]
    gx, gz = g[..., 0], g[..., 2]
    pool = np.exp(-((np.maximum(np.abs(gx) - 0.75, 0) / 0.32) ** 2 + (np.maximum(np.abs(gz) - 2.2, 0) / 0.45) ** 2))
    shadow = np.where(hit, 0.0, 0.78 * pool)
    # the bumper's lower edge and the diffuser a dark trim
    groove = hit & ~isw & back & (np.abs(y - 1.03) < 0.012)
    shade = np.where(groove, shade * 0.55, shade)
    trim = hit & ~isw & (y < 0.42)
    shade = np.where(trim, shade * 0.35, shade)
    R = np.where(hit, np.clip(shade / 1.25, 0.0, 1.0), 0.0)
    G = np.where(lights, 1.0, 0.0)
    B = np.where(glass, 1.0, 0.0)
    A = np.where(hit, 1.0, shadow)
    return np.stack([R, G, B, A], -1)


def down(img, f):
    h, w = img.shape[0] // f, img.shape[1] // f
    a = img[:h * f, :w * f]
    # coverage-weighted: the colour channels averaged where the body is, alpha averaged plainly
    al = a[..., 3:4]
    col = (a[..., :3] * al).reshape(h, f, w, f, 3).sum((1, 3))
    alw = al.reshape(h, f, w, f, 1).sum((1, 3))
    out = np.concatenate([col / np.maximum(alw, 1e-6), alw / (f * f)], -1)
    return out


def main():
    big = render(W0 * SS, H0 * SS)
    levels = [down(big, SS)]
    while levels[-1].shape[1] > 24:
        levels.append(down(levels[-1], 2))
    aw = sum(l.shape[1] for l in levels) + len(levels) * 2
    ah = H0
    atlas = np.zeros((ah, aw, 4))
    rects, x = [], 0
    for l in levels:
        atlas[:l.shape[0], x:x + l.shape[1]] = l
        rects.append([x, 0, l.shape[1], l.shape[0]])
        x += l.shape[1] + 2
    # where the car sits in its frame (level 0, as fractions): its centre, the bottom of its tyres, its body's width
    l0 = levels[0]
    cols = np.where((l0[..., 3] > 0.98).any(0))[0]
    rows = np.where((l0[..., 3] > 0.98).any(1))[0]
    anchor = {'cx': float((cols[0] + cols[-1] + 1) / 2 / l0.shape[1]), 'bottom': float((rows[-1] + 1) / l0.shape[0]),
              'width': float((cols[-1] + 1 - cols[0]) / l0.shape[1]), 'top': float(rows[0] / l0.shape[0])}
    px = (np.clip(atlas, 0, 1) * 255 + 0.5).astype(np.uint8)
    raw = px.tobytes()
    js = ("'use strict';\n/* GENERATED by tools/render_cars.py: the driving-assistant view's car, an atlas of levels (each half "
          "the one before), RGBA: R shading, G tail lights, B glass, A coverage. Do not edit. */\n"
          "const zlib = require('zlib');\n"
          "const W = %d, H = %d, LEVELS = %s, ANCHOR = %s;\n"
          "const DATA = '%s';\n"
          "let px = null;\n"
          "/** { w, h, levels: [[x, y, w, h]...], anchor: { cx, bottom, width, top } (fractions of a level), px } (px: RGBA\n"
          " * bytes, unpacked once). */\n"
          "module.exports = () => ({ w: W, h: H, levels: LEVELS, anchor: ANCHOR, px: px || (px = zlib.inflateSync(Buffer.from(DATA, 'base64'))) });\n"
          % (aw, ah, json.dumps(rects), json.dumps({k: round(v, 4) for k, v in anchor.items()}), base64.b64encode(zlib.compress(raw, 9)).decode()))
    open(OUT, 'w').write(js)
    print('atlas %dx%d, %d levels %s, anchor %s, %d KB raw, %d KB in the file' % (aw, ah, len(levels), [r[2] for r in rects], anchor, len(raw) // 1024, len(js) // 1024))
    if '--preview' in sys.argv:
        from PIL import Image
        out = sys.argv[sys.argv.index('--preview') + 1]
        l0 = levels[0]
        body = np.array([0.93, 0.95, 0.97])
        col = l0[..., 0:1] * body * 1.25
        col = np.where(l0[..., 2:3] > 0.5, l0[..., 0:1] * np.array([0.25, 0.32, 0.4]) + 0.04, col)
        col = np.where(l0[..., 1:2] > 0.5, np.array([1.0, 0.12, 0.08]) * 0.85, col)
        bg = np.ones_like(col) * np.array([0.05, 0.08, 0.12])
        a = l0[..., 3:4]
        img = np.clip(col * a + bg * (1 - a), 0, 1)
        Image.fromarray((img * 255).astype(np.uint8)).resize((W0 * 2, H0 * 2), Image.LANCZOS).save(out)


if __name__ == '__main__':
    main()

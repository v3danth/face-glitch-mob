"""
Geometric optics for a glass slab seen from straight above.

The viewer looks down the -z axis through a glass top surface z = h(x, y)
onto the photo, which lies `depth` pixels below the surface. The bottom face
of the glass rests flat on the photo, so only the top surface bends light.
Image y grows downward, so "up" in the picture is -y.

All functions are pure and work on whole per-pixel arrays, so a tile is
shaded with a handful of numpy operations and no Python loops.
"""

import numpy as np

# Fraunhofer lines in micrometres. Glass catalogues quote the index at d and
# the Abbe number from F and C, so these turn catalogue data into a curve.
_LAMBDA_D, _LAMBDA_F, _LAMBDA_C = 0.5876, 0.4861, 0.6563

# Dominant wavelength of each channel, in OpenCV's B, G, R order.
CHANNEL_WAVELENGTHS = (0.465, 0.550, 0.610)

_light = np.array([-0.45, -0.65, 0.62], dtype=np.float32)
LIGHT_DIR = _light / np.linalg.norm(_light)
"""Key light from the upper left, like a studio softbox above the subject."""

LIGHT_INTENSITY = 2.5

# A cool neutral tint for reflections of the room above the glass.
_ENV_TINT = np.array([1.0, 0.98, 0.95], dtype=np.float32)


def channel_iors(n_d, abbe):
    """
    Per-channel refractive index from catalogue n_d and Abbe number.

    Fitting Cauchy's law n = A + B / lambda^2 makes dispersion fall out of
    Snell's law, so colour fringes appear only where the surface actually
    bends light, instead of a hand-tuned channel shift everywhere.
    abbe=None means a dispersion-free material.
    """
    if abbe is None:
        return (n_d, n_d, n_d)
    b = (n_d - 1.0) / (abbe * (_LAMBDA_F**-2 - _LAMBDA_C**-2))
    a = n_d - b / _LAMBDA_D**2
    return tuple(a + b / lam**2 for lam in CHANNEL_WAVELENGTHS)


def surface_normals(gx, gy):
    """Unit normals of the height field from its x and y slopes."""
    inv = 1.0 / np.sqrt(gx * gx + gy * gy + 1.0)
    return -gx * inv, -gy * inv, inv


def refraction_offsets(nx, ny, nz, depth, ior):
    """
    How far each view ray drifts sideways before it reaches the photo.

    Vector form of Snell's law for the incident ray (0, 0, -1) entering a
    denser medium, so total internal reflection cannot occur and the square
    root is always real.
    """
    eta = 1.0 / ior
    k = 1.0 - eta * eta * (1.0 - nz * nz)
    c = eta * nz - np.sqrt(k)
    scale = depth / (eta - c * nz)
    return c * nx * scale, c * ny * scale


def fresnel(cos_theta, ior):
    """Schlick's approximation of the reflected fraction of light."""
    r0 = ((ior - 1.0) / (ior + 1.0)) ** 2
    return r0 + (1.0 - r0) * (1.0 - cos_theta) ** 5


def environment(nx, ny, nz):
    """
    Radiance of the room reflected in the glass, per BGR channel.

    The reflected view ray is r = 2 nz n - (0, 0, 1). A bright ceiling and a
    dark floor give glass its familiar light top rim and dark bottom rim.
    """
    ry = 2.0 * nz * ny
    sky = np.clip(0.5 - 0.6 * ry, 0.0, 1.0)
    radiance = 0.12 + 0.85 * sky * sky
    return radiance[..., None] * _ENV_TINT


def filtered_roughness(alpha, gx, gy):
    """
    Per-pixel GGX alpha widened by how much the normal turns within a pixel.

    A pixel averages the glints of every microfacet under it. Without this,
    pixel-scale bumps each catch the light at full strength and the glass
    sparkles with single white pixels (Kaplanyan et al. 2016).
    """
    gxy, gxx = np.gradient(gx)
    gyy, gyx = np.gradient(gy)
    variance = 0.25 * (gxx * gxx + gxy * gxy + gyx * gyx + gyy * gyy)
    return np.sqrt(alpha * alpha + np.minimum(2.0 * variance, 0.18))


def specular(nx, ny, nz, alpha, ior):
    """
    Highlight of the key light on the top surface.

    GGX microfacet distribution with Schlick Fresnel; alpha is the surface
    roughness, so polished glass gives a tight bright glint and etched glass
    a broad dim sheen.
    """
    hx, hy, hz = LIGHT_DIR + np.array([0.0, 0.0, 1.0], dtype=np.float32)
    inv = 1.0 / np.sqrt(hx * hx + hy * hy + hz * hz)
    hx, hy, hz = hx * inv, hy * inv, hz * inv

    n_dot_h = np.clip(nx * hx + ny * hy + nz * hz, 0.0, 1.0)
    n_dot_l = nx * LIGHT_DIR[0] + ny * LIGHT_DIR[1] + nz * LIGHT_DIR[2]
    a2 = alpha * alpha
    d = a2 / (np.pi * (n_dot_h * n_dot_h * (a2 - 1.0) + 1.0) ** 2)
    f = fresnel(hz, ior)
    return np.where(n_dot_l > 0.0, LIGHT_INTENSITY * d * f / (4.0 * nz), 0.0)


def transmittance(depth, absorption):
    """Beer-Lambert: thicker glass absorbs more of each channel."""
    return np.exp(-depth[..., None] * np.asarray(absorption, dtype=np.float32))

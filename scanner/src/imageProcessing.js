/**
 * imageProcessing.js
 *
 * Canvas/pixel-level utilities shared by foil detection and OCR
 * preprocessing: cropping by relative ratios (resolution-independent),
 * grayscale conversion, contrast stretching, and basic pixel statistics.
 * No dependencies.
 */

/**
 * Crops a canvas to a sub-region specified as ratios of its own
 * dimensions (0..1), so the same crop config works regardless of the
 * source resolution. This is how card-region and collector-number
 * crops are expressed throughout this module.
 *
 * @param {HTMLCanvasElement} sourceCanvas
 * @param {{x: number, y: number, w: number, h: number}} ratioRect
 * @returns {HTMLCanvasElement}
 */
export function cropByRatio(sourceCanvas, { x, y, w, h }) {
  const sx = Math.round(sourceCanvas.width * x);
  const sy = Math.round(sourceCanvas.height * y);
  const sw = Math.round(sourceCanvas.width * w);
  const sh = Math.round(sourceCanvas.height * h);

  const out = document.createElement('canvas');
  out.width = sw;
  out.height = sh;
  out.getContext('2d').drawImage(sourceCanvas, sx, sy, sw, sh, 0, 0, sw, sh);

  return out;
}

/** Returns the ImageData for an entire canvas. */
export function getImageData(canvas) {
  return canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
}

/** Standard perceptual luminance from RGB (ITU-R BT.601 coefficients). */
function luminance(r, g, b) {
  return 0.299 * r + 0.587 * g + 0.114 * b;
}

/**
 * Converts a canvas to grayscale in place (mutates and returns the same
 * canvas) using perceptual luminance, not a flat average -- this
 * matters for contrast enhancement quality on printed card text.
 */
export function toGrayscaleInPlace(canvas) {
  const ctx = canvas.getContext('2d');
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const d = imageData.data;

  for (let i = 0; i < d.length; i += 4) {
    const l = luminance(d[i], d[i + 1], d[i + 2]);
    d[i] = d[i + 1] = d[i + 2] = l;
  }

  ctx.putImageData(imageData, 0, 0);
  return canvas;
}

/**
 * Linear contrast stretch: remaps the [minPercentile, maxPercentile]
 * luminance range to full black/white, in place. Cheap and effective
 * for printed text against a fairly uniform card border -- much
 * simpler than histogram equalization, and good enough for OCR
 * preprocessing here.
 *
 * @param {HTMLCanvasElement} canvas Must already be grayscale.
 * @param {number} [factor=1.6] Contrast multiplier applied around the midpoint.
 */
export function stretchContrastInPlace(canvas, factor = 1.6) {
  const ctx = canvas.getContext('2d');
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const d = imageData.data;

  for (let i = 0; i < d.length; i += 4) {
    const v = d[i];
    const stretched = clamp((v - 128) * factor + 128, 0, 255);
    d[i] = d[i + 1] = d[i + 2] = stretched;
  }

  ctx.putImageData(imageData, 0, 0);
  return canvas;
}

/**
 * Binarizes a grayscale canvas in place using a fixed threshold.
 * Simple global thresholding -- fine for a tightly-cropped, mostly-flat
 * background like a collector-number strip. If your test images have
 * uneven lighting across that crop, an adaptive/local threshold would
 * do better; not implemented here to keep this dependency-free and
 * easy to reason about. See README for where to extend this.
 */
export function binarizeInPlace(canvas, threshold = 140) {
  const ctx = canvas.getContext('2d');
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const d = imageData.data;

  for (let i = 0; i < d.length; i += 4) {
    const v = d[i] >= threshold ? 255 : 0;
    d[i] = d[i + 1] = d[i + 2] = v;
  }

  ctx.putImageData(imageData, 0, 0);
  return canvas;
}

function clamp(v, min, max) {
  return Math.max(min, Math.min(max, v));
}

/**
 * Upscales a canvas by a fixed factor using bicubic-ish smoothing
 * (browser default `imageSmoothingQuality: 'high'`). Small OCR crops
 * (a collector-number strip is often <100px tall) benefit from being
 * scaled up before running Tesseract.
 */
export function upscale(canvas, factor = 2) {
  const out = document.createElement('canvas');
  out.width = Math.round(canvas.width * factor);
  out.height = Math.round(canvas.height * factor);

  const ctx = out.getContext('2d');
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(canvas, 0, 0, out.width, out.height);

  return out;
}

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

/**
 * Perspective-corrects a card from four clockwise source corners.
 *
 * @param {HTMLCanvasElement} sourceCanvas
 * @param {Array<[number, number]>} corners Top-left, top-right,
 *   bottom-right, bottom-left in source-image pixels.
 * @param {object} [cvInstance] OpenCV.js runtime, normally globalThis.cv.
 * @param {object} [options]
 * @param {number} [options.cardAspect=63 / 88] Width / height of a MTG card.
 * @returns {HTMLCanvasElement|null}
 */
export function rectifyCardFromCorners(sourceCanvas, corners, cvInstance = globalThis.cv, {
  cardAspect = 63 / 88,
} = {}) {
  if (!cvInstance?.Mat || !Array.isArray(corners) || corners.length !== 4) return null;

  const cv = cvInstance;
  const outputWidth = 900;
  const outputHeight = Math.round(outputWidth / cardAspect);
  const source = cv.imread(sourceCanvas);
  const sourcePoints = cv.matFromArray(4, 1, cv.CV_32FC2, corners.flat());
  const destinationPoints = cv.matFromArray(4, 1, cv.CV_32FC2, [
    0, 0, outputWidth, 0, outputWidth, outputHeight, 0, outputHeight,
  ]);
  const transform = cv.getPerspectiveTransform(sourcePoints, destinationPoints);
  const corrected = new cv.Mat();

  try {
    cv.warpPerspective(source, corrected, transform, new cv.Size(outputWidth, outputHeight));
    const result = document.createElement('canvas');
    result.width = outputWidth;
    result.height = outputHeight;
    cv.imshow(result, corrected);
    return result;
  } finally {
    source.delete();
    sourcePoints.delete();
    destinationPoints.delete();
    transform.delete();
    corrected.delete();
  }
}

/** Returns the ImageData for an entire canvas. */
export function getImageData(canvas) {
  return canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height);
}

/**
 * Finds a trading-card-shaped quadrilateral and perspective-corrects it.
 * Returns null when OpenCV is unavailable or no confident card contour is
 * found, allowing callers to fall back to a configured crop.
 *
 * @param {HTMLCanvasElement} sourceCanvas
 * @param {object} [cvInstance] OpenCV.js runtime, normally globalThis.cv.
 * @param {object} [options]
 * @param {number} [options.cardAspect=63 / 88] Width / height of a MTG card.
 * @returns {HTMLCanvasElement|null}
 */
export function detectCardAndRectify(sourceCanvas, cvInstance = globalThis.cv, {
  cardAspect = 63 / 88,
} = {}) {
  if (!cvInstance || !cvInstance.Mat) return null;

  const cv = cvInstance;
  const maxDimension = 900;
  const scale = Math.min(1, maxDimension / Math.max(sourceCanvas.width, sourceCanvas.height));
  const detectionCanvas = document.createElement('canvas');
  detectionCanvas.width = Math.max(1, Math.round(sourceCanvas.width * scale));
  detectionCanvas.height = Math.max(1, Math.round(sourceCanvas.height * scale));
  detectionCanvas.getContext('2d').drawImage(
    sourceCanvas, 0, 0, detectionCanvas.width, detectionCanvas.height,
  );

  const source = cv.imread(detectionCanvas);
  const gray = new cv.Mat();
  const edges = new cv.Mat();
  const contours = new cv.MatVector();
  const hierarchy = new cv.Mat();

  try {
    cv.cvtColor(source, gray, cv.COLOR_RGBA2GRAY);
    cv.GaussianBlur(gray, gray, new cv.Size(5, 5), 0);
    cv.Canny(gray, edges, 50, 150);
    cv.findContours(edges, contours, hierarchy, cv.RETR_LIST, cv.CHAIN_APPROX_SIMPLE);

    const imageArea = detectionCanvas.width * detectionCanvas.height;
    let best = null;

    for (let index = 0; index < contours.size(); index += 1) {
      const contour = contours.get(index);
      const perimeter = cv.arcLength(contour, true);
      const polygon = new cv.Mat();
      cv.approxPolyDP(contour, polygon, perimeter * 0.02, true);
      const rotatedRect = cv.minAreaRect(contour);
      const rotatedWidth = Math.min(rotatedRect.size.width, rotatedRect.size.height);
      const rotatedHeight = Math.max(rotatedRect.size.width, rotatedRect.size.height);
      const rotatedAspect = rotatedWidth / rotatedHeight;
      const rotatedAspectError = Math.abs(Math.log(rotatedAspect / cardAspect));
      const rotatedAreaRatio = (
        rotatedRect.size.width * rotatedRect.size.height
      ) / imageArea;
      const rotatedPoints = rotatedRectPoints(rotatedRect);
      const rotatedTouchesImageEdge = rotatedPoints.some((point) => (
        point.x <= detectionCanvas.width * 0.01
        || point.y <= detectionCanvas.height * 0.01
        || point.x >= detectionCanvas.width * 0.99
        || point.y >= detectionCanvas.height * 0.99
      ));
      const rotatedScore = rotatedAreaRatio / (1 + rotatedAspectError * 5);

      if (!rotatedTouchesImageEdge && rotatedAreaRatio > 0.18
        && rotatedAreaRatio < 0.95 && rotatedAspectError < 0.45
        && (!best || rotatedScore > best.score)) {
        best = {
          points: orderQuadrilateral(rotatedPoints),
          score: rotatedScore,
          areaRatio: rotatedAreaRatio,
        };
      }

      const bounds = cv.boundingRect(contour);
      const boundingArea = bounds.width * bounds.height;
      const boundingAreaRatio = boundingArea / imageArea;
      const boundingAspect = bounds.width / bounds.height;
      const boundingAspectError = Math.abs(Math.log(boundingAspect / cardAspect));
      const boundingPoints = [
        { x: bounds.x, y: bounds.y },
        { x: bounds.x + bounds.width, y: bounds.y },
        { x: bounds.x + bounds.width, y: bounds.y + bounds.height },
        { x: bounds.x, y: bounds.y + bounds.height },
      ];
      const boundingTouchesImageEdge = boundingPoints.some((point) => (
        point.x <= detectionCanvas.width * 0.01
        || point.y <= detectionCanvas.height * 0.01
        || point.x >= detectionCanvas.width * 0.99
        || point.y >= detectionCanvas.height * 0.99
      ));

      const boundingScore = boundingAreaRatio / (1 + boundingAspectError * 5);
      if (!boundingTouchesImageEdge && boundingAreaRatio > 0.18
        && boundingAreaRatio < 0.95 && boundingAspectError < 0.45
        && (!best || boundingScore > best.score)) {
        best = {
          points: boundingPoints,
          score: boundingScore,
          areaRatio: boundingAreaRatio,
        };
      }

      if (polygon.rows === 4 && cv.isContourConvex(polygon)) {
        const points = [];
        for (let pointIndex = 0; pointIndex < 4; pointIndex += 1) {
          points.push({
            x: polygonPoint(polygon, pointIndex, 0),
            y: polygonPoint(polygon, pointIndex, 1),
          });
        }
        const ordered = orderQuadrilateral(points);
        const width = (distance(ordered[0], ordered[1]) + distance(ordered[2], ordered[3])) / 2;
        const height = (distance(ordered[0], ordered[3]) + distance(ordered[1], ordered[2])) / 2;
        const detectedAspect = width / height;
        const aspectError = Math.abs(Math.log(detectedAspect / cardAspect));
        const area = Math.abs(cv.contourArea(polygon));
        const areaRatio = area / imageArea;
        const score = areaRatio / (1 + aspectError * 5);
        const touchesImageEdge = points.some((point) => (
          point.x <= detectionCanvas.width * 0.01
          || point.y <= detectionCanvas.height * 0.01
          || point.x >= detectionCanvas.width * 0.99
          || point.y >= detectionCanvas.height * 0.99
        ));

        if (!touchesImageEdge && areaRatio > 0.18 && areaRatio < 0.95 && aspectError < 0.45
          && (!best || score > best.score)) {
          best = { points: ordered, score, areaRatio };
        }
      }

      contour.delete();
      polygon.delete();
    }

    if (!best) return null;

    const ordered = best.points;
    const outputWidth = 900;
    const outputHeight = Math.round(outputWidth / cardAspect);
    const sourcePoints = cv.matFromArray(4, 1, cv.CV_32FC2, ordered.flatMap(({ x, y }) => [x, y]));
    const destinationPoints = cv.matFromArray(4, 1, cv.CV_32FC2, [
      0, 0, outputWidth, 0, outputWidth, outputHeight, 0, outputHeight,
    ]);
    const transform = cv.getPerspectiveTransform(sourcePoints, destinationPoints);
    const corrected = new cv.Mat();
    cv.warpPerspective(source, corrected, transform, new cv.Size(outputWidth, outputHeight));

    const result = document.createElement('canvas');
    result.width = outputWidth;
    result.height = outputHeight;
    cv.imshow(result, corrected);

    sourcePoints.delete();
    destinationPoints.delete();
    transform.delete();
    corrected.delete();
    return result;
  } finally {
    source.delete();
    gray.delete();
    edges.delete();
    contours.delete();
    hierarchy.delete();
  }
}

function polygonPoint(polygon, index, coordinate) {
  return polygon.intPtr(index, 0)[coordinate];
}

function distance(first, second) {
  return Math.hypot(first.x - second.x, first.y - second.y);
}

function rotatedRectPoints(rotatedRect) {
  const angle = rotatedRect.angle * Math.PI / 180;
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  const halfWidth = rotatedRect.size.width / 2;
  const halfHeight = rotatedRect.size.height / 2;
  const corners = [
    [-halfWidth, -halfHeight],
    [halfWidth, -halfHeight],
    [halfWidth, halfHeight],
    [-halfWidth, halfHeight],
  ];

  return corners.map(([x, y]) => ({
    x: rotatedRect.center.x + x * cos - y * sin,
    y: rotatedRect.center.y + x * sin + y * cos,
  }));
}

function orderQuadrilateral(points) {
  const sums = points.map((point) => point.x + point.y);
  const differences = points.map((point) => point.x - point.y);
  return [
    points[sums.indexOf(Math.min(...sums))],
    points[differences.indexOf(Math.max(...differences))],
    points[sums.indexOf(Math.max(...sums))],
    points[differences.indexOf(Math.min(...differences))],
  ];
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
 * Brightens or darkens image midtones in place without changing geometry.
 * Values above 1 brighten midtones; values below 1 darken them.
 *
 * @param {HTMLCanvasElement} canvas
 * @param {number} [gamma=1.2]
 * @returns {HTMLCanvasElement}
 */
export function adjustGammaInPlace(canvas, gamma = 1.2) {
  const ctx = canvas.getContext('2d');
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const d = imageData.data;
  const inverseGamma = 1 / gamma;

  for (let i = 0; i < d.length; i += 4) {
    d[i] = 255 * ((d[i] / 255) ** inverseGamma);
    d[i + 1] = 255 * ((d[i + 1] / 255) ** inverseGamma);
    d[i + 2] = 255 * ((d[i + 2] / 255) ** inverseGamma);
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

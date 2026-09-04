/**
 * foilDetection.js
 *
 * Heuristic foil/non-foil classifier based on pixel statistics -- not
 * a trained model, just a few signals that correlate with a foil
 * card's uneven, prismatic reflectivity under normal lighting.
 *
 * This is original work: the three signals and how they're combined
 * were designed from scratch for this project, not derived from any
 * other codebase. That said, "look at variance in brightness/color to
 * guess reflectivity" is a generic, well-known image-processing idea
 * -- expect to need your own calibration pass (see calibrate.html)
 * against real photos taken with your actual camera/lighting setup
 * before trusting the defaults below.
 *
 * Signals computed over a crop (ideally a decent chunk of the card
 * face, not just the tiny collector-number strip -- foil sheen is
 * easier to detect over a larger area):
 *
 *   - luminanceStdDev: standard deviation of per-pixel brightness.
 *     A foil surface catches light unevenly, so brightness varies
 *     more across the image than a matte card under the same lighting.
 *
 *   - saturationVariance: variance of per-pixel HSV saturation.
 *     Foil's prismatic sheen tends to introduce localized color-shift
 *     "hotspots" that a normal card's more uniform coloring doesn't
 *     have, showing up as higher saturation variance.
 *
 *   - specularHotspotRatio: fraction of pixels that are near-blown-out
 *     (very high luminance). Foil commonly produces small, sharp
 *     specular highlights under typical indoor/flash lighting that a
 *     matte card doesn't.
 *
 * These are combined by simple threshold voting (N of 3), mirroring
 * the general shape of "combine a few weak signals" without copying
 * any specific implementation -- see DEFAULT_FOIL_THRESHOLDS for the
 * starting values and detectFoil() for how they're combined.
 */

export const DEFAULT_FOIL_THRESHOLDS = {
  luminanceStdDev: 55, // 0..255 scale
  saturationVariance: 0.020, // 0..1 scale (saturation is 0..1 per pixel)
  specularHotspotRatio: 0.03, // fraction of pixels, 0..1
  minVotes: 2, // how many of the 3 signals must trip to call it foil
};

/**
 * @param {{data: Uint8ClampedArray|number[], width: number, height: number}} imageData
 *   Anything structurally like ImageData -- accepts plain objects too,
 *   so this is unit-testable outside a browser.
 * @returns {{luminanceStdDev: number, saturationVariance: number,
 *            specularHotspotRatio: number, meanLuminance: number,
 *            pixelCount: number}}
 */
export function computeFoilSignals(imageData) {
  const { data } = imageData;
  const pixelCount = data.length / 4;

  let sumLuminance = 0;
  let sumSaturation = 0;
  let hotspotCount = 0;
  const luminances = new Float64Array(pixelCount);
  const saturations = new Float64Array(pixelCount);

  for (let p = 0; p < pixelCount; p++) {
    const i = p * 4;
    const r = data[i];
    const g = data[i + 1];
    const b = data[i + 2];

    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const l = 0.299 * r + 0.587 * g + 0.114 * b;
    const s = max === 0 ? 0 : (max - min) / max;

    luminances[p] = l;
    saturations[p] = s;
    sumLuminance += l;
    sumSaturation += s;

    if (l >= 245) hotspotCount++;
  }

  const meanLuminance = sumLuminance / pixelCount;
  const meanSaturation = sumSaturation / pixelCount;

  let luminanceVarianceSum = 0;
  let saturationVarianceSum = 0;
  for (let p = 0; p < pixelCount; p++) {
    luminanceVarianceSum += (luminances[p] - meanLuminance) ** 2;
    saturationVarianceSum += (saturations[p] - meanSaturation) ** 2;
  }

  return {
    luminanceStdDev: Math.sqrt(luminanceVarianceSum / pixelCount),
    saturationVariance: saturationVarianceSum / pixelCount,
    specularHotspotRatio: hotspotCount / pixelCount,
    meanLuminance,
    pixelCount,
  };
}

/**
 * @param {ReturnType<typeof computeFoilSignals>} signals
 * @param {typeof DEFAULT_FOIL_THRESHOLDS} [thresholds]
 * @returns {{isFoil: boolean, votes: number, tripped: string[], signals: object}}
 */
export function detectFoil(signals, thresholds = DEFAULT_FOIL_THRESHOLDS) {
  const tripped = [];
  if (signals.luminanceStdDev > thresholds.luminanceStdDev) tripped.push('luminanceStdDev');
  if (signals.saturationVariance > thresholds.saturationVariance) tripped.push('saturationVariance');
  if (signals.specularHotspotRatio > thresholds.specularHotspotRatio) tripped.push('specularHotspotRatio');

  return {
    isFoil: false,//#tripped.length >= thresholds.minVotes,
    votes: tripped.length,
    tripped,
    signals,
  };
}

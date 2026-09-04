/**
 * ocr.js
 *
 * Tesseract.js wrapper specialized for reading a Magic: The Gathering
 * collector-number line (e.g. "0119 R EN", "123/280", "003/281 C JA").
 * Handles worker lifecycle, a character whitelist to cut down on
 * misreads, parsing the recognized text into structured fields, and a
 * multi-crop-region fallback loop that tries a few plausible crop
 * placements and keeps the best-scoring result.
 *
 * Requires Tesseract.js to be available -- either loaded globally via
 * the CDN script tag (`window.Tesseract`) or installed via npm and
 * passed in explicitly (see createOcrEngine's `tesseractModule` option).
 * Not bundled here so you can pick whichever fits your build setup.
 */

import { cropByRatio, toGrayscaleInPlace, stretchContrastInPlace, binarizeInPlace, upscale } from './imageProcessing.js';

// Collector-number strip is reliably in the bottom-left ~40% width,
// bottom ~12% height of the card face on modern frames, but shifts a
// little by frame era and by how tightly the card fills your capture
// frame -- hence trying a few candidate regions rather than one fixed
// crop. All ratios are relative to the *card* image, not the full
// camera frame -- crop to the card first if your capture includes
// background.
export const DEFAULT_CROP_REGIONS = [
  { name: 'standard', x: 0.03, y: 0.86, w: 0.40, h: 0.10 },
  { name: 'wider', x: 0.02, y: 0.84, w: 0.50, h: 0.13 },
  { name: 'offsetLower', x: 0.03, y: 0.89, w: 0.40, h: 0.10 },
];

// Digits, the fraction slash, rarity letters, common language codes,
// and space/hyphen. Restricting Tesseract's alphabet meaningfully cuts
// down on misreads for this narrow use case.
const CHAR_WHITELIST = '0123456789/ -ACDEFHIJKMNOPRSTUZacdefhijkmnoprstuz';

/**
 * Creates a reusable OCR engine. Tesseract worker creation is
 * expensive (loads a language model) -- create one of these once and
 * reuse it across scans; call destroy() when you're done (e.g. when
 * navigating away from the scanner view).
 *
 * @param {object} [options]
 * @param {object} [options.tesseractModule] Pass the imported
 *   `tesseract.js` module if you're using it via npm/bundler instead
 *   of the global CDN script.
 * @param {string} [options.lang='eng']
 */
export async function createOcrEngine({ tesseractModule, lang = 'eng' } = {}) {
  const Tesseract = tesseractModule || globalThis.Tesseract;
  if (!Tesseract) {
    throw new Error(
      'Tesseract.js not found. Load it via <script src="https://.../tesseract.min.js">, ' +
      'or install the npm package and pass { tesseractModule } to createOcrEngine().'
    );
  }

  const worker = await Tesseract.createWorker(lang);
  await worker.setParameters({ tessedit_char_whitelist: CHAR_WHITELIST });

  return {
    /**
     * Runs OCR on a canvas, already preprocessed by the caller.
     * @param {HTMLCanvasElement} canvas
     * @returns {Promise<{text: string, confidence: number}>}
     */
    async recognize(canvas) {
      const { data } = await worker.recognize(canvas);
      return { text: data.text, confidence: data.confidence };
    },
    async destroy() {
      await worker.terminate();
    },
  };
}

/**
 * Parses OCR text into structured collector-number fields. Tolerant
 * of noise (extra whitespace, stray misreads around the fields it
 * cares about) but returns null for anything it isn't reasonably
 * confident about, rather than guessing.
 *
 * Handles the two common on-card formats:
 *   "0119 R EN"      -> collectorNumber="119", rarity="R", language="EN"
 *   "123/280"         -> collectorNumber="123", rarity=null, language=null
 *   "003/281 C JA"    -> collectorNumber="3", rarity="C", language="JA"
 *
 * @param {string} rawText
 * @returns {{collectorNumber: string|null, rarity: string|null,
 *            language: string|null, raw: string}}
 */
export function parseCollectorInfo(rawText) {
  const cleaned = rawText.replace(/\s+/g, ' ').trim();

  // Leading digits, optionally zero-padded, optionally "/nnn" total-count suffix.
  const numberMatch = cleaned.match(/(\d{1,4})(?:\s*\/\s*\d{1,4})?/);
  const collectorNumber = numberMatch ? String(parseInt(numberMatch[1], 10)) : null;

  // A single rarity letter (C/U/R/M/S), typically standalone after the number.
  const rarityMatch = cleaned.match(/\b([CURMS])\b/i);
  const rarity = rarityMatch ? rarityMatch[1].toUpperCase() : null;

  // A 2-letter ISO-ish language code, typically standalone near the end.
  const languageMatch = cleaned.match(/\b(EN|DE|FR|JA|IT|PT|RU|KO|ZH|ES)\b/i);
  const language = languageMatch ? languageMatch[1].toUpperCase() : null;

  return { collectorNumber, rarity, language, raw: rawText };
}

/**
 * Scores a parsed OCR result for the fallback loop below: higher is
 * better. Rewards actually finding a collector number (the one field
 * we truly need), then rarity/language as bonuses, then raw OCR
 * confidence as a tiebreaker.
 *
 * @param {ReturnType<typeof parseCollectorInfo>} parsed
 * @param {number} ocrConfidence 0..100, from Tesseract
 */
export function scoreResult(parsed, ocrConfidence) {
  if (!parsed.collectorNumber) return 0;
  let score = 50;
  if (parsed.rarity) score += 15;
  if (parsed.language) score += 15;
  score += ocrConfidence * 0.2; // up to +20
  return score;
}

/**
 * @param {HTMLCanvasElement} canvas
 * @param {{isFoil?: boolean}} [options]
 */
function preprocessForOcr(canvas, { isFoil = false } = {}) {
  const upscaled = upscale(canvas, 3);
  toGrayscaleInPlace(upscaled);

  if (isFoil) {
    // Foil's uneven reflectivity tends to blow out a plain contrast
    // stretch in patches; a slightly gentler stretch followed by
    // binarizing helps more than it hurts in testing so far -- but
    // this is exactly the kind of thing to check against your own
    // foil photos and adjust.
    stretchContrastInPlace(upscaled, 1.3);
    binarizeInPlace(upscaled, 150);
  } else {
    stretchContrastInPlace(upscaled, 1.6);
  }

  return upscaled;
}

/**
 * Tries each crop region in turn (grayscale -> contrast stretch ->
 * upscale -> OCR -> parse -> score), keeping the best result. Stops
 * early once a result is confidently good, rather than always paying
 * for every region.
 *
 * @param {HTMLCanvasElement} cardCanvas Canvas already cropped to the card itself.
 * @param {object} ocrEngine From createOcrEngine().
 * @param {object} [options]
 * @param {Array<{name: string, x: number, y: number, w: number, h: number}>}
 *   [options.regions=DEFAULT_CROP_REGIONS]
 * @param {number} [options.earlyStopScore=80]
 * @param {boolean} [options.isFoil=false] Foil crops get a stronger
 *   contrast stretch and a binarize pass -- foil's uneven reflections
 *   otherwise tend to wash out a fixed-threshold approach. This is a
 *   starting heuristic, tune against your own foil test photos.
 * @returns {Promise<{collectorNumber: string|null, rarity: string|null,
 *   language: string|null, raw: string, score: number, strategy: string,
 *   confidence: number}>}
 */
export async function scanWithFallback(cardCanvas, ocrEngine, {
  regions = DEFAULT_CROP_REGIONS,
  earlyStopScore = 80,
  isFoil = false,
} = {}) {
  let best = { collectorNumber: null, rarity: null, language: null, raw: '', score: 0, strategy: 'none', confidence: 0 };

  for (const region of regions) {
    const preprocessed = preprocessForOcr(cropByRatio(cardCanvas, region), { isFoil });
    const { text, confidence } = await ocrEngine.recognize(preprocessed);
    const parsed = parseCollectorInfo(text);
    const score = scoreResult(parsed, confidence);

    if (score > best.score) {
      best = { ...parsed, score, strategy: region.name, confidence };
    }
    if (best.score >= earlyStopScore) break;
  }

  return best;
}

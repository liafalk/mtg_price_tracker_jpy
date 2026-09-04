/**
 * cardScanner.js
 *
 * Top-level entry point tying camera/file capture, foil detection, and
 * OCR together into a single scan() call. This is the piece you'll
 * most likely wire into your own UI; the other modules (camera.js,
 * imageProcessing.js, foilDetection.js, ocr.js) are exported
 * separately too, if you'd rather compose them yourself.
 */

import { captureFrameToCanvas, loadFileToCanvas } from './camera.js';
import { cropByRatio, detectCardAndRectify, getImageData } from './imageProcessing.js';
import { computeFoilSignals, detectFoil, DEFAULT_FOIL_THRESHOLDS } from './foilDetection.js';
import { createOcrEngine, scanWithFallback, DEFAULT_CROP_REGIONS } from './ocr.js';

// Where the card is expected to sit within the *captured frame* (not
// the card's own dimensions -- this crop happens first, and
// DEFAULT_CROP_REGIONS in ocr.js are then relative to its output).
// Defaults to "most of the frame" on the assumption your capture UI
// already guides the user to fill the frame with the card; adjust to
// match your actual on-screen guide overlay.
const DEFAULT_CARD_REGION = { x: 0.05, y: 0.05, w: 0.90, h: 0.90 };

export class CardScanner {
  /**
   * @param {object} [options]
   * @param {object} [options.tesseractModule] See createOcrEngine.
   * @param {string} [options.lang='eng']
   * @param {{x:number,y:number,w:number,h:number}} [options.cardRegion]
   *   Crop applied before anything else, to isolate the card from
   *   background. Override if your capture UI frames the card
   *   differently than DEFAULT_CARD_REGION assumes.
   * @param {typeof DEFAULT_FOIL_THRESHOLDS} [options.foilThresholds]
   * @param {Array} [options.ocrCropRegions] See DEFAULT_CROP_REGIONS in ocr.js.
  * @param {boolean} [options.autoDetectCard=false] Use OpenCV.js to find and
  *   perspective-correct the card before processing.
  * @param {object} [options.cvInstance] OpenCV.js runtime.
   */
  constructor({
    tesseractModule,
    lang = 'eng',
    cardRegion = DEFAULT_CARD_REGION,
    foilThresholds = DEFAULT_FOIL_THRESHOLDS,
    ocrCropRegions = DEFAULT_CROP_REGIONS,
    autoDetectCard = false,
    cvInstance = globalThis.cv,
  } = {}) {
    this._tesseractModule = tesseractModule;
    this._lang = lang;
    this.cardRegion = cardRegion;
    this.foilThresholds = foilThresholds;
    this.ocrCropRegions = ocrCropRegions;
    this.autoDetectCard = autoDetectCard;
    this.cvInstance = cvInstance;
    this._ocrEngine = null;
  }

  /** Lazily creates the Tesseract worker on first use (it's slow to spin up). */
  async _ensureOcrEngine() {
    if (!this._ocrEngine) {
      this._ocrEngine = await createOcrEngine({
        tesseractModule: this._tesseractModule,
        lang: this._lang,
      });
    }
    return this._ocrEngine;
  }

  /**
   * Full pipeline on an already-captured canvas: crop to card, detect
   * foil, OCR the collector number (with foil-aware preprocessing),
   * return everything together.
   *
   * @param {HTMLCanvasElement} sourceCanvas Raw capture (full camera
   *   frame or full uploaded photo) -- not yet cropped to the card.
   * @returns {Promise<{
   *   collectorNumber: string|null, rarity: string|null, language: string|null,
   *   isFoil: boolean, foilVotes: number, foilSignals: object,
   *   ocrConfidence: number, ocrStrategy: string, ocrScore: number,
    *   rawText: string, cardCanvas: HTMLCanvasElement,
    *   ocrCanvas: HTMLCanvasElement|null, timingMs: number
   * }>}
   */
  async scanCanvas(sourceCanvas, { skipAutomaticDetection = false } = {}) {
    const startedAt = performance.now();

    const detectedCardCanvas = this.autoDetectCard && !skipAutomaticDetection
      ? detectCardAndRectify(sourceCanvas, this.cvInstance)
      : null;
      let cardCanvas = detectedCardCanvas
        || (skipAutomaticDetection ? sourceCanvas : cropByRatio(sourceCanvas, this.cardRegion));
    let cardDetection = detectedCardCanvas ? 'automatic' : 'fallback';

    // Foil signals computed over the whole card face, not just the
    // number strip -- foil sheen is easier to pick up over a larger area.
    let foilSignals = computeFoilSignals(getImageData(cardCanvas));
    let foilResult = detectFoil(foilSignals, this.foilThresholds);

    const ocrEngine = await this._ensureOcrEngine();
    let ocrResult = await scanWithFallback(cardCanvas, ocrEngine, {
      regions: this.ocrCropRegions,
      isFoil: foilResult.isFoil,
    });

    // A partial rotated rectangle can look card-shaped while still producing
    // unusable OCR. Prefer the configured crop when automatic OCR is weak.
    if (detectedCardCanvas && ocrResult.score < 60) {
      const fallbackCanvas = cropByRatio(sourceCanvas, this.cardRegion);
      const fallbackSignals = computeFoilSignals(getImageData(fallbackCanvas));
      const fallbackFoil = detectFoil(fallbackSignals, this.foilThresholds);
      const fallbackOcr = await scanWithFallback(fallbackCanvas, ocrEngine, {
        regions: this.ocrCropRegions,
        isFoil: fallbackFoil.isFoil,
      });

      if (fallbackOcr.score >= ocrResult.score) {
        cardCanvas = fallbackCanvas;
        cardDetection = 'fallback';
        foilSignals = fallbackSignals;
        foilResult = fallbackFoil;
        ocrResult = fallbackOcr;
      }
    }

    return {
      collectorNumber: ocrResult.collectorNumber,
      rarity: ocrResult.rarity,
      language: ocrResult.language,
      isFoil: foilResult.isFoil,
      foilVotes: foilResult.votes,
      foilSignals,
      ocrConfidence: ocrResult.confidence,
      ocrStrategy: ocrResult.strategy,
      ocrScore: ocrResult.score,
      rawText: ocrResult.raw,
      cardCanvas,
      cardDetection,
      ocrSourceCanvas: ocrResult.sourceCanvas,
      ocrCanvas: ocrResult.preprocessedCanvas,
      timingMs: performance.now() - startedAt,
    };
  }

  /** Convenience: capture the current frame from a <video> element and scan it. */
  async scanVideo(videoEl) {
    return this.scanCanvas(captureFrameToCanvas(videoEl));
  }

  /** Convenience: load a File/Blob (e.g. from <input type="file">) and scan it. */
  async scanFile(file) {
    const canvas = await loadFileToCanvas(file);
    return this.scanCanvas(canvas);
  }

  /** Releases the Tesseract worker. Call this when done scanning (unmount/navigate away). */
  async destroy() {
    if (this._ocrEngine) {
      await this._ocrEngine.destroy();
      this._ocrEngine = null;
    }
  }
}

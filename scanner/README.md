# card-scanner

Standalone, dependency-light ES modules for the camera/OCR/foil-detection
piece of a card scanner: capture a photo (camera or file upload), find
and read the collector-number line, and guess whether the card is foil.
Everything runs client-side in the browser.

This is **original work**, not derived from any other project's source
-- the foil-detection signals and thresholds, the OCR fallback/scoring
logic, and the collector-number parsing were all designed from scratch
for this module. The general *shape* of the approach (pixel-statistic
heuristic feeding foil-aware OCR preprocessing, multi-crop-region
fallback with scoring) is a common pattern in this space, not novel --
but the actual code here is independent.

## Status

Functional and unit-tested where it can be (pure logic: foil math,
collector-number parsing, scoring). The camera/OCR pieces need a real
browser and haven't been exercised against real card photos yet --
**expect to calibrate the foil thresholds and possibly the OCR crop
regions against your own camera and lighting** before trusting this in
production. See "Calibration" below.

## Requirements

- A modern browser with camera support, for the live-capture path
  (file upload works everywhere with canvas support)
- [Tesseract.js](https://tesseract.projectnaptha.com/) — not bundled,
  load it however fits your setup:
  - CDN: `<script src="https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js"></script>`
    then it's available as `window.Tesseract`, which `createOcrEngine()`
    picks up automatically
  - npm: `npm install tesseract.js`, then pass the imported module as
    `createOcrEngine({ tesseractModule })` / `new CardScanner({ tesseractModule })`
- OpenCV.js — loaded from jsDelivr by `demo.html` for automatic card
  edge detection and perspective correction

No other dependencies. No bundler is required, but native ES modules must be
served over HTTP rather than opened with `file://`. Bundle it into your
existing app's build if you prefer.

## Quick start

From the repository root, serve the scanner folder locally:

```bash
python -m http.server 8080 --directory scanner
```

Then open <http://localhost:8080/demo.html>. The demo loads OpenCV.js and uses
it to detect and straighten the card automatically. This is required because
module imports such as `./src/camera.js` are blocked by browsers when the page is
opened from `file://`. Camera access also requires `localhost` or HTTPS. It's
a self-contained test page: start the camera or upload a photo, scan, and see the
parsed collector number, foil verdict, and raw signal numbers.

### Pick corners manually

The demo includes a corner picker for difficult images. Select a photo, click
the card corners clockwise starting at the top-left, and copy the generated
`const corners = [...]` value. Coordinates are reported in the original image's
pixel dimensions, even when the preview is displayed at a smaller size.
Copy the generated YOLO label line into a `.txt` file with the same base name
as the image, under the matching `labels/train`, `labels/val`, or `labels/test`
directory.

## Usage

```js
import { CardScanner } from './src/cardScanner.js';

const scanner = new CardScanner(); // picks up window.Tesseract automatically

// From a live <video> element:
const result = await scanner.scanVideo(videoEl);

// From an uploaded file:
const result = await scanner.scanFile(fileInput.files[0]);

// From a canvas you already have:
const result = await scanner.scanCanvas(myCanvas);

console.log(result);
// {
//   collectorNumber: '119', rarity: 'R', language: 'EN',
//   isFoil: false, foilVotes: 1, foilSignals: {...},
//   ocrConfidence: 87.3, ocrStrategy: 'standard', ocrScore: 92.5,
//   rawText: '0119 R EN', cardCanvas: <canvas>, ocrCanvas: <canvas>,
//   timingMs: 1840,
// }

// Release the OCR worker when you're done with the scanner (e.g. on
// unmount / navigating away from the scan view):
await scanner.destroy();
```

Each field of `result`:

| Field | Meaning |
|---|---|
| `collectorNumber` | Normalized (no leading zeros), or `null` if not confidently found |
| `rarity` | `C`/`U`/`R`/`M`/`S`, or `null` |
| `language` | 2-letter code (`EN`, `JA`, ...), or `null` |
| `isFoil` | Best guess from `foilDetection.js` |
| `foilVotes` | How many of the 3 foil signals tripped (0-3) — useful for calibration, see below |
| `foilSignals` | The raw numbers behind the verdict |
| `ocrConfidence` | Tesseract's own 0-100 confidence for the winning crop |
| `ocrStrategy` | Which crop region in `DEFAULT_CROP_REGIONS` won |
| `cardDetection` | `automatic` when OpenCV found and rectified a card, `hardcoded` for an explicit corner override, otherwise `fallback` |
| `ocrCanvas` | The processed crop sent to Tesseract, including grayscale, contrast, optional binarization, and upscaling |
| `ocrSourceCanvas` | The original winning OCR crop before preprocessing |
| `ocrScore` | This module's own scoring (see `ocr.js`), not Tesseract's |
| `rawText` | Unparsed OCR output, for debugging |
| `cardCanvas` | The normalized, perspective-corrected card used for processing when `cardDetection` is `automatic`; otherwise the fixed fallback crop |

If you'd rather compose the pieces yourself instead of using
`CardScanner`, every module is independently importable:

```js
import { startCamera, captureFrameToCanvas } from './src/camera.js';
import { cropByRatio, toGrayscaleInPlace, adjustGammaInPlace } from './src/imageProcessing.js';
import { computeFoilSignals, detectFoil } from './src/foilDetection.js';
import { createOcrEngine, scanWithFallback, parseCollectorInfo } from './src/ocr.js';
```

## Project layout

```
src/
  camera.js           # getUserMedia start/stop, frame capture, file upload, torch
  imageProcessing.js  # crop-by-ratio, grayscale, contrast stretch, binarize, upscale
  foilDetection.js    # pixel-statistic foil heuristic (see below)
  ocr.js              # Tesseract.js wrapper, collector-number parsing, multi-crop fallback
  cardScanner.js      # CardScanner class tying everything together
  index.js            # re-exports everything
demo.html             # standalone test/calibration page
```

## How foil detection works

Three pixel-statistic signals, computed over the card-region crop
(not just the tiny collector-number strip — foil sheen is easier to
read over more area):

- **`luminanceStdDev`** — standard deviation of per-pixel brightness.
  Foil scatters light unevenly, so brightness varies more across the
  image than a matte card under the same lighting.
- **`saturationVariance`** — variance of per-pixel HSV saturation.
  Foil's prismatic sheen tends to create localized color-shift
  "hotspots" a normal card's more uniform coloring doesn't have.
- **`specularHotspotRatio`** — fraction of pixels that are
  near-blown-out (luminance ≥ 245). Foil commonly produces small,
  sharp specular highlights under typical lighting that a matte card
  doesn't.

`detectFoil()` calls it foil if **at least 2 of these 3** trip their
threshold (`DEFAULT_FOIL_THRESHOLDS` in `foilDetection.js`). This
result also feeds `ocr.js`'s preprocessing choice — foil crops get a
gentler contrast stretch plus a binarize pass, since a plain stretch
tends to blow out patches unevenly on a reflective surface.

**These thresholds are starting points, not calibrated against a real
dataset.** They'll need adjusting for your actual camera and lighting
— see Calibration below.

## Calibration

Foil detection accuracy depends heavily on lighting, camera, and how
close/flat the card is held. Before relying on this:

1. Open `demo.html`.
2. Scan several **known-foil** cards and several **known-normal**
   cards under your actual capture conditions (lighting, distance,
   angle — whatever your real users will do).
3. Note the `luminanceStdDev` / `saturationVariance` /
   `specularHotspotRatio` numbers shown for each.
4. Look for a threshold on each signal that reasonably separates your
   foil scans from your normal scans, and update
   `DEFAULT_FOIL_THRESHOLDS` in `foilDetection.js` accordingly. You can
   also adjust `minVotes` (currently 2 of 3) if one signal turns out
   much more reliable than the others for your setup — e.g. drop to
   `minVotes: 1` weighted toward just `luminanceStdDev` if that's the
   only one that reliably separates your samples, or raise the
   individual thresholds instead of touching vote count.

The OCR crop regions (`DEFAULT_CROP_REGIONS` in `ocr.js`) may also need
adjusting — they assume a fairly standard modern card frame and a
capture that roughly fills `DEFAULT_CARD_REGION` in `cardScanner.js`.
If your on-screen capture guide frames the card differently, adjust
`cardRegion` when constructing `CardScanner`, and/or add/tweak entries
in `DEFAULT_CROP_REGIONS` for card frames whose collector-number
placement differs (older frames, some special sets).

## Known limitations / not handled here

- **Single global threshold in `binarizeInPlace`** — fine for a
  tightly-cropped, fairly flat background, but uneven lighting across
  the crop will hurt it. An adaptive/local threshold would do better;
  not implemented, to keep this dependency-free.
- **`DEFAULT_CROP_REGIONS` assumes a standard modern frame.** Very old
  frames, oversized/oddly-numbered promos, or cards where the
  collector-number strip sits somewhere unusual will need their own
  region(s) added.
- **Automatic detection fallback.** `cardRegion` in `CardScanner` remains a
  fixed-ratio fallback. Set `autoDetectCard: true` and provide an OpenCV.js
  runtime through `cvInstance` to detect a card quadrilateral and perspective-
  correct it automatically.
- **Language-code and rarity parsing is regex-based**, not
  cross-checked against Scryfall — false positives are possible on
  noisy OCR output (e.g. misreading a stray character as a rarity
  letter). Worth validating the returned `collectorNumber` /
  `rarity` / `language` against a real Scryfall lookup before trusting
  them outright, same as you'd sanity-check any OCR result.

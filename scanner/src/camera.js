/**
 * camera.js
 *
 * Thin wrapper around getUserMedia for card-scanning use: start/stop a
 * rear-camera stream, grab the current frame as a canvas, and (where
 * supported) toggle the torch/flash. No dependencies.
 */

/**
 * Starts a camera stream and attaches it to a <video> element.
 *
 * @param {HTMLVideoElement} videoEl
 * @param {object} [options]
 * @param {'user'|'environment'} [options.facingMode='environment']
 * @returns {Promise<MediaStream>}
 */
export async function startCamera(videoEl, { facingMode = 'environment' } = {}) {
  const stream = await navigator.mediaDevices.getUserMedia({
    video: {
      facingMode: { ideal: facingMode },
      width: { ideal: 1920 },
      height: { ideal: 1080 },
    },
    audio: false,
  });

  videoEl.srcObject = stream;
  videoEl.setAttribute('playsinline', 'true'); // iOS Safari: avoid fullscreen takeover
  await videoEl.play();

  return stream;
}

/** Stops every track on a stream (call this on unmount/navigate-away). */
export function stopCamera(stream) {
  if (!stream) return;
  for (const track of stream.getTracks()) {
    track.stop();
  }
}

/**
 * Draws the current video frame onto a new canvas at the video's native
 * resolution (not its displayed CSS size), so cropping math downstream
 * can work in real pixels.
 *
 * @param {HTMLVideoElement} videoEl
 * @returns {HTMLCanvasElement}
 */
export function captureFrameToCanvas(videoEl) {
  const canvas = document.createElement('canvas');
  canvas.width = videoEl.videoWidth;
  canvas.height = videoEl.videoHeight;

  const ctx = canvas.getContext('2d');
  ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);

  return canvas;
}

/**
 * Loads a File/Blob (e.g. from an <input type="file">) into a canvas at
 * its native resolution. Use this for the "upload a photo" fallback path.
 *
 * @param {File|Blob} file
 * @returns {Promise<HTMLCanvasElement>}
 */
export function loadFileToCanvas(file) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);

    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      canvas.getContext('2d').drawImage(img, 0, 0);
      URL.revokeObjectURL(url);
      resolve(canvas);
    };
    img.onerror = (err) => {
      URL.revokeObjectURL(url);
      reject(err);
    };
    img.src = url;
  });
}

/**
 * Whether the given stream's active video track supports a torch
 * (flash). Most laptop/desktop webcams don't; many phone rear cameras do.
 *
 * @param {MediaStream} stream
 * @returns {boolean}
 */
export function supportsTorch(stream) {
  const track = stream?.getVideoTracks?.()[0];
  if (!track || typeof track.getCapabilities !== 'function') return false;
  const caps = track.getCapabilities();
  return Boolean(caps.torch);
}

/**
 * Turns the torch on/off. Throws if unsupported -- check supportsTorch()
 * first and hide the UI control if it returns false.
 *
 * @param {MediaStream} stream
 * @param {boolean} on
 */
export async function setTorch(stream, on) {
  const track = stream?.getVideoTracks?.()[0];
  if (!track) throw new Error('No active video track');
  await track.applyConstraints({ advanced: [{ torch: on }] });
}

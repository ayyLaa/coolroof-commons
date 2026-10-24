import { seededNoise } from './demo-readings'

// A synthetic top-down photo in the layout ml/tests/coverage_images.py uses: grass, a dark
// roof, and a painted strip as wide as the scenario's coverage. The backend's OpenCV
// analysis reads it back to the same percentage (checked: 94.5 -> 94.5, 41 -> 41.0).
const SIZE_PX = 400
const ROOF_START_PX = 100
const ROOF_SIZE_PX = 200
const GRASS = [60, 140, 60]
const BITUMEN = [70, 70, 70]
const COATING = [245, 245, 245]
const NOISE_LEVEL = 4
const PERCENT = 100

function colourAt(x: number, y: number, coatedWidth: number): number[] {
  const onRoof =
    x >= ROOF_START_PX &&
    x < ROOF_START_PX + ROOF_SIZE_PX &&
    y >= ROOF_START_PX &&
    y < ROOF_START_PX + ROOF_SIZE_PX
  if (!onRoof) return GRASS
  return x < ROOF_START_PX + coatedWidth ? COATING : BITUMEN
}

export function drawRoofPhoto(coveragePct: number): Promise<Blob> {
  const canvas = document.createElement('canvas')
  canvas.width = SIZE_PX
  canvas.height = SIZE_PX
  const context = canvas.getContext('2d')
  if (!context) return Promise.reject(new Error('This browser cannot draw the demo roof photo.'))
  const image = context.createImageData(SIZE_PX, SIZE_PX)
  const coatedWidth = Math.round((ROOF_SIZE_PX * coveragePct) / PERCENT)
  const noise = seededNoise(`photo-${coveragePct}`)
  for (let y = 0; y < SIZE_PX; y++) {
    for (let x = 0; x < SIZE_PX; x++) {
      const offset = (y * SIZE_PX + x) * 4
      colourAt(x, y, coatedWidth).forEach((channel, index) => {
        image.data[offset + index] = Math.max(0, Math.min(255, channel + noise() * NOISE_LEVEL))
      })
      image.data[offset + 3] = 255
    }
  }
  context.putImageData(image, 0, 0)
  return new Promise((resolve, reject) =>
    canvas.toBlob(
      blob =>
        blob ? resolve(blob) : reject(new Error('The demo roof photo could not be encoded.')),
      'image/png',
    ),
  )
}

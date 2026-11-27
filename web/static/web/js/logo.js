import { raw } from "./ui.js";

/* Vecta mark: a rounded square with a "V" cut out of it. The right stroke runs longer than the left,
   so the letter reads as a direction. One colour (currentColor), no gradients. */
const PATH = "M8 1h16a7 7 0 0 1 7 7v16a7 7 0 0 1-7 7H8a7 7 0 0 1-7-7V8a7 7 0 0 1 7-7z M8 11 L11.7 11 L15.03 17.08 L20.3 6 L24.2 6 L15.4 24.5 Z";

export const logoMark = (size = 28) =>
  raw(`<svg viewBox="0 0 32 32" width="${size}" height="${size}" fill="currentColor" fill-rule="evenodd" role="img" aria-label="Vecta"><path d="${PATH}"/></svg>`);

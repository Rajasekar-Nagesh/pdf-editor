// pdf.js setup. The worker is bundled by Vite and loaded from our own origin.
import * as pdfjs from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

export type PDFDoc = pdfjs.PDFDocumentProxy;
export type PDFPage = pdfjs.PDFPageProxy;

export async function loadPdf(data: ArrayBuffer): Promise<PDFDoc> {
  // pdf.js transfers the buffer to its worker, so give it a copy.
  return pdfjs.getDocument({ data: new Uint8Array(data.slice(0)), isEvalSupported: false }).promise;
}

/** Render a page into a canvas at the given CSS scale (handles high-DPI screens).
 * Returns the pdf.js RenderTask so callers can cancel it when the zoom changes. */
export function renderPage(page: PDFPage, canvas: HTMLCanvasElement, scale: number) {
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const viewport = page.getViewport({ scale: scale * ratio });
  canvas.width = Math.floor(viewport.width);
  canvas.height = Math.floor(viewport.height);
  canvas.style.width = `${Math.floor(viewport.width / ratio)}px`;
  canvas.style.height = `${Math.floor(viewport.height / ratio)}px`;
  const ctx = canvas.getContext("2d")!;
  return page.render({ canvasContext: ctx, viewport });
}

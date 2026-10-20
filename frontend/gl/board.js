/**
 * @fileoverview The face board: enlarged face crops from the rendered
 * canvas with the grid and painted cells drawn over them. Same geometry as
 * web/painter.py and model.js, so clicks map through cellAt().
 */

import {
  BOARD, MATERIAL_COLORS, boardSize, gridEdges, materialLabel, parseCellKey, slotOrigin,
} from '../shared/model.js';

/**
 * @param {!HTMLCanvasElement} board
 * @param {!HTMLCanvasElement} rendered full-resolution render
 * @param {!Array<{x: number, y: number, w: number, h: number}>} faces
 * @param {{grid: number, cells: !Object}} layout
 * @param {?{face: number, row: number, col: number}=} cursor keyboard focus cell
 */
export function drawBoard(board, rendered, faces, layout, cursor = null) {
  const {width, height} = boardSize(faces.length);
  board.width = width;
  board.height = height;
  const ctx = board.getContext('2d');
  ctx.fillStyle = '#12161f';
  ctx.fillRect(0, 0, width, height);
  ctx.imageSmoothingQuality = 'high';

  faces.forEach((face, index) => {
    const {x: ox, y: oy} = slotOrigin(index);
    ctx.drawImage(rendered, face.x, face.y, face.w, face.h, ox, oy, BOARD.slot, BOARD.slot);
    const xs = gridEdges(face.w, layout.grid).map((e) => ox + Math.round((e * BOARD.slot) / face.w));
    const ys = gridEdges(face.h, layout.grid).map((e) => oy + Math.round((e * BOARD.slot) / face.h));

    ctx.strokeStyle = 'rgb(255 255 255 / 0.7)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (const x of xs) {
      ctx.moveTo(x + 0.5, oy);
      ctx.lineTo(x + 0.5, oy + BOARD.slot);
    }
    for (const y of ys) {
      ctx.moveTo(ox, y + 0.5);
      ctx.lineTo(ox + BOARD.slot, y + 0.5);
    }
    ctx.stroke();

    const fontSize = Math.max(9, Math.min(14, (xs[1] - xs[0]) / 3.5));
    ctx.font = `600 ${fontSize}px system-ui, sans-serif`;
    ctx.textBaseline = 'top';
    for (const [key, style] of Object.entries(layout.cells)) {
      const {face: f, row, col} = parseCellKey(key);
      if (f !== index || row >= layout.grid || col >= layout.grid) continue;
      const color = MATERIAL_COLORS[style.material];
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.strokeRect(xs[col] + 2, ys[row] + 2, xs[col + 1] - xs[col] - 4, ys[row + 1] - ys[row] - 4);
      ctx.fillStyle = color;
      ctx.fillText(materialLabel(style.material), xs[col] + 5, ys[row] + 5);
    }
    if (cursor?.face === index && cursor.row < layout.grid && cursor.col < layout.grid) {
      ctx.setLineDash([5, 3]);
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 3;
      const {row, col} = cursor;
      ctx.strokeRect(xs[col] + 1.5, ys[row] + 1.5, xs[col + 1] - xs[col] - 3, ys[row + 1] - ys[row] - 3);
      ctx.setLineDash([]);
    }
  });
}

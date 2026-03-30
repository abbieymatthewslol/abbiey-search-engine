# Manual QA — layout & panels

Run through on a **search results** page (query with text results). Use a wide window (>1100px) unless noted.

## Preview column

1. **Resize**: Drag the slim vertical bar between main results and the preview; width should change smoothly and persist after reload.
2. **Double-click bar**: Resets preview width to default.
3. **Keyboard**: Focus the bar (Tab), use ← / → to nudge width.
4. **Dock**: Click « in the preview header; column hides; a thin **‹** tab appears on the right edge. Click tab to restore.
5. **Auto-restore**: With column docked, hover a result or use **j**/**k**; preview should return and load.
6. **Narrow**: Below ~1100px width, preview is a slide-over; gutter should not appear; **Close** (×) still works.

## Research chat

1. Open chat (FAB), **drag top edge** to change height; persists after reload.
2. **Drag left edge** to change width (desktop); hidden on narrow/mobile width.
3. **Double-click** top or left edge to reset that dimension.
4. **Peek**: Chevron-down minimizes to a strip; chevron toggles back; main close still works.
5. **Keyboard**: Tab to height resize control, **↑**/**↓**; Tab to width control, **←**/**→** (when chat open, wide layout).

## AI summary (text tab)

1. **Dismiss** (up chevron): Card hides; **Show AI summary** link appears; click to restore.
2. Settings **AI Summary** off/on still behaves; turning on clears session dismiss.

## Settings

1. **Reset sizes & preview column**: Clears saved widths, undocks preview, resets chat sizing classes; does not clear history/settings otherwise.

## Reduced motion

1. OS / browser **prefers-reduced-motion**: panel transitions should feel instant (no long slides).

## Touch (tablet / touchscreen)

1. Same resize gestures on gutter and chat edges with finger/stylus where supported.

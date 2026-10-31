import { describe, expect, it } from 'vitest';
import { placePathCard } from './PathHoverCard';

const viewport = { width: 1000, height: 800 };
const card = { width: 600, height: 150 };

describe('placePathCard', () => {
  it('sits above the trigger when it fits there', () => {
    const place = placePathCard({ left: 100, top: 400, bottom: 420 }, card, viewport);
    expect(place.left).toBe(100);
    expect(place.top).toBe(246);
  });

  it('moves below a trigger near the top edge instead of leaving the window', () => {
    const place = placePathCard({ left: 100, top: 135, bottom: 155 }, card, viewport);
    expect(place.top).toBe(159);
  });

  it('stays inside the left and right edge at any card width', () => {
    expect(placePathCard({ left: 700, top: 400, bottom: 420 }, card, viewport).left).toBe(392);
    expect(placePathCard({ left: -20, top: 400, bottom: 420 }, card, viewport).left).toBe(8);
    expect(placePathCard({ left: 100, top: 400, bottom: 420 }, { width: 2000, height: 150 }, viewport).left).toBe(8);
  });

  it('takes the larger side and scrolls when it fits on neither', () => {
    const tall = { width: 600, height: 500 };
    const nearTop = placePathCard({ left: 0, top: 200, bottom: 220 }, tall, { width: 1000, height: 600 });
    expect(nearTop.top).toBe(224);
    expect(nearTop.maxHeight).toBe(368);

    const nearBottom = placePathCard({ left: 0, top: 500, bottom: 520 }, tall, { width: 1000, height: 600 });
    expect(nearBottom.top).toBe(8);
    expect(nearBottom.maxHeight).toBe(488);
  });
});

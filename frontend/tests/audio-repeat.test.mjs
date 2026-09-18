import { test } from "node:test";
import assert from "node:assert/strict";
import { nextAudioIndex } from "../src/lib/audio-repeat.ts";

test("normal playback advances and stops after the final clip", () => {
  assert.equal(nextAudioIndex(0, 3, "off"), 1);
  assert.equal(nextAudioIndex(2, 3, "off"), null);
});
test("playlist repeat wraps to the beginning after each complete cycle", () => {
  let index = 0;
  const heard = [];
  for (let n = 0; n < 7; n++) {
    heard.push(index);
    index = nextAudioIndex(index, 3, "all");
  }
  assert.deepEqual(heard, [0, 1, 2, 0, 1, 2, 0]);
});
test("repeat one stays on the selected clip, including a single-track player", () => {
  assert.equal(nextAudioIndex(1, 3, "one"), 1);
  assert.equal(nextAudioIndex(0, 1, "one"), 0);
  assert.equal(nextAudioIndex(0, 1, "all"), 0);
  assert.equal(nextAudioIndex(0, 1, "off"), null);
});
test("an empty playlist never starts a nonexistent track", () => {
  for (const mode of ["off", "all", "one"]) assert.equal(nextAudioIndex(0, 0, mode), null);
});

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseAudioTime } from '../src/lib/audio-time.ts';

test('the requested 11:20 target is exactly 680 seconds in English or Persian', () => {
  for (const value of ['11:20', '۱۱:۲۰', '١١:٢٠', ' 11:20 ']) {
    assert.equal(parseAudioTime(value, 2960), 680);
  }
});
test('supports long clips and hour notation', () => {
  assert.equal(parseAudioTime('71:20', 8000), 4280);
  assert.equal(parseAudioTime('1:11:20', 8000), 4280);
  assert.equal(parseAudioTime('0:00', 2960), 0);
  assert.equal(parseAudioTime('49:20', 2960), 2960);
});
test('rejects invalid times instead of silently seeking somewhere else', () => {
  for (const input of ['', '-1:20', '11:60', '1:70:00', '12.5', '49:21', 'abc', '11:2']) {
    assert.equal(parseAudioTime(input, 2960), null, input);
  }
  assert.equal(parseAudioTime('11:20', NaN), null);
  assert.equal(parseAudioTime('11:20', Infinity), null);
});

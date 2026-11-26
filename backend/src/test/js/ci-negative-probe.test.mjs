import test from 'node:test';
import assert from 'node:assert/strict';
test('controlled required-gate negative probe, never merge', () => { assert.fail('Expected WEB-G03 failure probe'); });

import { test } from "node:test";
import assert from "node:assert/strict";
import { forgetKey } from "../src/whatsapp.js";

test("a new stamp is a different one-shot for the same phone", () => {
  assert.equal(forgetKey("5511900000001", ""), "5511900000001");
  assert.equal(forgetKey("5511900000001", undefined), "5511900000001");
  assert.notEqual(forgetKey("5511900000001", "1"), forgetKey("5511900000001", "2"));
  assert.notEqual(forgetKey("5511900000001", "2"), "5511900000001");
});

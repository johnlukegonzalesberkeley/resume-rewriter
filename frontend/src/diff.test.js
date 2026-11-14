import test from "node:test";
import assert from "node:assert/strict";
import { diffWords } from "./diff.js";

// The words (not spaces) flagged as changed in a list of segments.
const changed = (segments) =>
  segments.filter((s) => s.changed && !s.space).map((s) => s.text);

test("identical text has no changes", () => {
  const d = diffWords("Trained new hires", "Trained new hires");
  assert.deepEqual(changed(d.before), []);
  assert.deepEqual(changed(d.after), []);
});

test("a swapped word is flagged on both sides", () => {
  const d = diffWords("Helped customers at the register", "Assisted customers at the register");
  assert.deepEqual(changed(d.before), ["Helped"]);
  assert.deepEqual(changed(d.after), ["Assisted"]);
});

test("added words show up only on the after side", () => {
  const d = diffWords("Trained new hires", "Trained 3 new hires");
  assert.deepEqual(changed(d.before), []);
  assert.deepEqual(changed(d.after), ["3"]);
});

test("removed words show up only on the before side", () => {
  const d = diffWords("Was responsible for closing the store", "Closing the store");
  assert.deepEqual(changed(d.after), []);
  assert.deepEqual(changed(d.before), ["Was", "responsible", "for"]);
});

test("case and surrounding punctuation are ignored", () => {
  const d = diffWords("Reduced load time by 35%", "reduced load time by 35%.");
  assert.deepEqual(changed(d.before), []);
  assert.deepEqual(changed(d.after), []);
});

test("space between two changed words is highlighted too, so runs form one block", () => {
  const d = diffWords("Trained new hires", "Trained new team members on cafe operations");
  const spaces = d.after.filter((s) => s.space && s.changed);
  assert.ok(spaces.length >= 2);
});

test("empty before text marks everything on the after side as new", () => {
  const d = diffWords("", "Brand new bullet");
  assert.deepEqual(changed(d.after), ["Brand", "new", "bullet"]);
  assert.deepEqual(d.before, []);
});

test("segments always rebuild the original text exactly", () => {
  const text = "Led a  4-person team,\tshipped to 120 users.";
  const d = diffWords("something else", text);
  assert.equal(d.after.map((s) => s.text).join(""), text);
});

import { expect, test } from "vitest";
import { parseImportedNote } from "../lib/import-note";

const captured = { title: "An idea", transcript: "Keep every word.", summary: ["A useful point"] };
const now = 1800000000000;

test("imports companion actions and uses the source file timestamp when capture time is absent", () => {
  expect(
    parseImportedNote({ ...captured, suggested_actions: ["Try it"] }, now - 60000, now),
  ).toEqual({
    ...captured,
    actions: ["Try it"],
    tags: [],
    recordedAt: now - 60000,
    contextEnabled: false,
  });
});

test("preserves portal fields while requiring fresh consent for live context", () => {
  const imported = parseImportedNote(
    { ...captured, actions: ["Review"], tags: ["Ideas"], recordedAt: 0, contextEnabled: true },
    now,
    now,
  );
  expect(imported).toMatchObject({
    actions: ["Review"],
    tags: ["Ideas"],
    recordedAt: 0,
    contextEnabled: false,
  });
});

test("rejects oversized source fields without silently truncating or dropping values", () => {
  for (const fields of [
    { title: "x".repeat(161) },
    { transcript: "x".repeat(60001) },
    { summary: Array(21).fill("point") },
    { summary: ["x".repeat(2001)] },
    { actions: Array(31).fill("action") },
    { suggested_actions: [false] },
    { tags: Array(11).fill("tag") },
    { tags: ["x".repeat(41)] },
  ])
    expect(() => parseImportedNote({ ...captured, ...fields }, now, now)).toThrow();
  expect(
    parseImportedNote({ ...captured, transcript: "x".repeat(60000) }, now, now).transcript,
  ).toHaveLength(60000);
});

test("rejects malformed files and invalid recording timestamps", () => {
  for (const data of [
    null,
    [],
    "text",
    {},
    { ...captured, transcript: 4 },
    { ...captured, summary: [4] },
    { ...captured, recordedAt: "yesterday" },
    { ...captured, recordedAt: -1 },
    { ...captured, recordedAt: Infinity },
    { ...captured, recordedAt: now + 86400001 },
  ])
    expect(() => parseImportedNote(data, now, now)).toThrow();
});

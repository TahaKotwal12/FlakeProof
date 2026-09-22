/**
 * Short shareable run slugs, e.g. "x7Kp2mQ9aB" (docs/04-API.md POST /api/runs).
 * Alphanumeric-only alphabet (no `-`/`_`) so slugs stay unambiguous in URLs,
 * chat messages, and the report/patch export filenames.
 */

import { customAlphabet } from "nanoid";

const ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz";
const SLUG_LENGTH = 10;

const nanoid = customAlphabet(ALPHABET, SLUG_LENGTH);

export function generateSlug(): string {
  return nanoid();
}

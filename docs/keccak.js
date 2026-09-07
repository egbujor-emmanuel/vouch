/* Keccak-256, the hash ERC-8004 commits with.
 *
 * Vendored rather than pulled from a CDN so the page has no external
 * dependency and cannot be silently changed underneath a viewer. This is the
 * one piece of the dashboard that must be exactly right: every VERIFIED badge
 * on the page is this function's answer.
 *
 * Keccak-f[1600], rate 1088 bits (136 bytes), original Keccak padding (0x01),
 * which is what Ethereum uses rather than the later SHA-3 padding (0x06).
 */
(function (global) {
  "use strict";

  const RC = [
    [0x00000000, 0x00000001], [0x00000000, 0x00008082],
    [0x80000000, 0x0000808a], [0x80000000, 0x80008000],
    [0x00000000, 0x0000808b], [0x00000000, 0x80000001],
    [0x80000000, 0x80008081], [0x80000000, 0x00008009],
    [0x00000000, 0x0000008a], [0x00000000, 0x00000088],
    [0x00000000, 0x80008009], [0x00000000, 0x8000000a],
    [0x00000000, 0x8000808b], [0x80000000, 0x0000008b],
    [0x80000000, 0x00008089], [0x80000000, 0x00008003],
    [0x80000000, 0x00008002], [0x80000000, 0x00000080],
    [0x00000000, 0x0000800a], [0x80000000, 0x8000000a],
    [0x80000000, 0x80008081], [0x80000000, 0x00008080],
    [0x00000000, 0x80000001], [0x80000000, 0x80008008],
  ];

  const R = [
    0, 1, 62, 28, 27, 36, 44, 6, 55, 20, 3, 10, 43, 25,
    39, 41, 45, 15, 21, 8, 18, 2, 61, 56, 14,
  ];

  // Lanes are 64-bit, held as [hi, lo] pairs of 32-bit words.
  function rotl(hi, lo, n) {
    if (n === 0) return [hi, lo];
    if (n < 32) {
      return [
        ((hi << n) | (lo >>> (32 - n))) >>> 0,
        ((lo << n) | (hi >>> (32 - n))) >>> 0,
      ];
    }
    if (n === 32) return [lo >>> 0, hi >>> 0];
    n -= 32;
    return [
      ((lo << n) | (hi >>> (32 - n))) >>> 0,
      ((hi << n) | (lo >>> (32 - n))) >>> 0,
    ];
  }

  function keccakF(S) {
    const C = new Array(10), D = new Array(10), B = new Array(50);
    for (let round = 0; round < 24; round++) {
      // theta
      for (let x = 0; x < 5; x++) {
        let hi = 0, lo = 0;
        for (let y = 0; y < 5; y++) {
          hi ^= S[2 * (x + 5 * y)];
          lo ^= S[2 * (x + 5 * y) + 1];
        }
        C[2 * x] = hi >>> 0;
        C[2 * x + 1] = lo >>> 0;
      }
      for (let x = 0; x < 5; x++) {
        const r = rotl(C[2 * ((x + 1) % 5)], C[2 * ((x + 1) % 5) + 1], 1);
        D[2 * x] = (C[2 * ((x + 4) % 5)] ^ r[0]) >>> 0;
        D[2 * x + 1] = (C[2 * ((x + 4) % 5) + 1] ^ r[1]) >>> 0;
      }
      for (let x = 0; x < 5; x++) {
        for (let y = 0; y < 5; y++) {
          S[2 * (x + 5 * y)] = (S[2 * (x + 5 * y)] ^ D[2 * x]) >>> 0;
          S[2 * (x + 5 * y) + 1] = (S[2 * (x + 5 * y) + 1] ^ D[2 * x + 1]) >>> 0;
        }
      }
      // rho and pi
      for (let x = 0; x < 5; x++) {
        for (let y = 0; y < 5; y++) {
          const i = x + 5 * y;
          const r = rotl(S[2 * i], S[2 * i + 1], R[i]);
          const j = y + 5 * ((2 * x + 3 * y) % 5);
          B[2 * j] = r[0];
          B[2 * j + 1] = r[1];
        }
      }
      // chi
      for (let x = 0; x < 5; x++) {
        for (let y = 0; y < 5; y++) {
          const i = x + 5 * y;
          const n1 = ((x + 1) % 5) + 5 * y;
          const n2 = ((x + 2) % 5) + 5 * y;
          S[2 * i] = (B[2 * i] ^ (~B[2 * n1] & B[2 * n2])) >>> 0;
          S[2 * i + 1] = (B[2 * i + 1] ^ (~B[2 * n1 + 1] & B[2 * n2 + 1])) >>> 0;
        }
      }
      // iota
      S[0] = (S[0] ^ RC[round][0]) >>> 0;
      S[1] = (S[1] ^ RC[round][1]) >>> 0;
    }
    return S;
  }

  /** keccak256 over raw bytes. Returns a 0x-prefixed hex string. */
  function keccak256(bytes) {
    const RATE = 136; // 1088 bits
    const S = new Array(50).fill(0);

    // pad10*1 with the original Keccak domain byte
    const padded = new Uint8Array(Math.ceil((bytes.length + 1) / RATE) * RATE);
    padded.set(bytes);
    padded[bytes.length] = 0x01;
    padded[padded.length - 1] |= 0x80;

    for (let off = 0; off < padded.length; off += RATE) {
      for (let i = 0; i < RATE / 8; i++) {
        const b = off + i * 8;
        // little-endian lane: low 4 bytes then high 4 bytes
        const lo =
          (padded[b] | (padded[b + 1] << 8) | (padded[b + 2] << 16) | (padded[b + 3] << 24)) >>> 0;
        const hi =
          (padded[b + 4] | (padded[b + 5] << 8) | (padded[b + 6] << 16) | (padded[b + 7] << 24)) >>> 0;
        S[2 * i] = (S[2 * i] ^ hi) >>> 0;
        S[2 * i + 1] = (S[2 * i + 1] ^ lo) >>> 0;
      }
      keccakF(S);
    }

    let out = "0x";
    for (let i = 0; i < 4; i++) {
      const hi = S[2 * i], lo = S[2 * i + 1];
      for (let b = 0; b < 4; b++) out += ((lo >>> (8 * b)) & 0xff).toString(16).padStart(2, "0");
      for (let b = 0; b < 4; b++) out += ((hi >>> (8 * b)) & 0xff).toString(16).padStart(2, "0");
    }
    return out;
  }

  global.keccak256 = keccak256;
  if (typeof module !== "undefined" && module.exports) module.exports = { keccak256 };
})(typeof globalThis !== "undefined" ? globalThis : this);

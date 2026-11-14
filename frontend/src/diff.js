// Word-level diff using the longest common subsequence (LCS) of the two texts' words.
// Words that appear in both texts, in the same order, are "unchanged". Everything else is
// "changed": removed from the before text, or added in the after text.

// Compare words ignoring case and surrounding punctuation, so "register." matches "register".
function normalize(word) {
  return word.toLowerCase().replace(/^[^\w%$]+|[^\w%$]+$/g, "");
}

// Rebuild a text as segments (words and the whitespace between them), tagging each word
// as changed or not. Whitespace between two changed words is marked changed too, so a
// run of changed words highlights as one block.
function toSegments(text, changedFlags) {
  const tokens = text.match(/\s+|\S+/g) || [];
  let wordIndex = 0;
  const segments = tokens.map((token) =>
    /^\s+$/.test(token)
      ? { text: token, changed: false, space: true }
      : { text: token, changed: changedFlags[wordIndex++], space: false }
  );
  segments.forEach((seg, i) => {
    if (seg.space && segments[i - 1]?.changed && segments[i + 1]?.changed) {
      seg.changed = true;
    }
  });
  return segments;
}

export function diffWords(before, after) {
  const a = before.match(/\S+/g) || [];
  const b = after.match(/\S+/g) || [];
  const n = a.length;
  const m = b.length;

  // dp[i][j] = length of the longest common word sequence of a[i..] and b[j..]
  const dp = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] =
        normalize(a[i]) === normalize(b[j])
          ? dp[i + 1][j + 1] + 1
          : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }

  // Walk the table to mark which words are part of the common sequence.
  const aChanged = new Array(n).fill(true);
  const bChanged = new Array(m).fill(true);
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (normalize(a[i]) === normalize(b[j])) {
      aChanged[i] = false;
      bChanged[j] = false;
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      i++;
    } else {
      j++;
    }
  }

  return {
    before: toSegments(before, aChanged),
    after: toSegments(after, bChanged),
  };
}

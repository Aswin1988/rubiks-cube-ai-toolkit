import { describe, expect, it } from "vitest";
import vectors from "@/generated/conformance.json";
import {
  MOVES,
  applyMove,
  destinationFor,
  faceletPose,
  isFaceletAffected,
  moveSpec,
  rotateVector,
} from "@/lib/cube";

const closeVector = (actual: readonly number[], expected: readonly number[]) => {
  actual.forEach((value, index) => expect(value).toBeCloseTo(expected[index], 8));
};

describe("Python engine conformance", () => {
  it.each(MOVES)("matches %s on every representative state", (move) => {
    for (const sample of vectors.representatives) {
      expect(applyMove(sample.state, move)).toBe(sample.after[move]);
    }
  });

  it.each(MOVES)("maps animated geometry to %s permutation destinations", (move) => {
    const { axis, angle } = moveSpec(move);
    for (let source = 0; source < 54; source += 1) {
      if (!isFaceletAffected(source, move)) continue;
      const destination = destinationFor(source, move);
      closeVector(
        rotateVector(faceletPose(source).position, axis, angle),
        faceletPose(destination).position,
      );
      closeVector(
        rotateVector(faceletPose(source).normal, axis, angle),
        faceletPose(destination).normal,
      );
    }
  });
});

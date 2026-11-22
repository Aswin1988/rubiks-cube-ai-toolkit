import vectors from "@/generated/conformance.json";

export const FACES = ["U", "R", "F", "D", "L", "B"] as const;
export type Face = (typeof FACES)[number];
export const MOVES = [
  "U", "U2", "U'", "R", "R2", "R'", "F", "F2", "F'",
  "D", "D2", "D'", "L", "L2", "L'", "B", "B2", "B'",
] as const;
export type Move = (typeof MOVES)[number];
export type Vector3 = readonly [number, number, number];

export const SOLVED_STATE = vectors.solved;

const permutations = vectors.permutations as Record<Move, number[]>;
const faceBasis: Record<Face, readonly [Vector3, Vector3, Vector3]> = {
  U: [[0, 1, 0], [1, 0, 0], [0, 0, -1]],
  R: [[1, 0, 0], [0, 0, -1], [0, 1, 0]],
  F: [[0, 0, 1], [1, 0, 0], [0, 1, 0]],
  D: [[0, -1, 0], [1, 0, 0], [0, 0, 1]],
  L: [[-1, 0, 0], [0, 0, 1], [0, 1, 0]],
  B: [[0, 0, -1], [-1, 0, 0], [0, 1, 0]],
};

function add(...values: Vector3[]): Vector3 {
  return values.reduce<Vector3>(
    (sum, value) => [sum[0] + value[0], sum[1] + value[1], sum[2] + value[2]],
    [0, 0, 0],
  );
}

function scale(value: Vector3, factor: number): Vector3 {
  return [value[0] * factor, value[1] * factor, value[2] * factor];
}

export function assertCubeState(state: string): void {
  if (state.length !== 54 || [...state].some((symbol) => !FACES.includes(symbol as Face))) {
    throw new Error("cube state must contain exactly 54 URFDLB symbols");
  }
}

export function applyMove(state: string, move: Move): string {
  assertCubeState(state);
  const result = Array<string>(54);
  permutations[move].forEach((destination, source) => {
    result[destination] = state[source];
  });
  return result.join("");
}

export function applyMoves(state: string, moves: readonly Move[]): string {
  return moves.reduce(applyMove, state);
}

export function inverseMove(move: Move): Move {
  if (move.endsWith("2")) return move;
  return (move.endsWith("'") ? move[0] : `${move}'`) as Move;
}

export interface FaceletPose {
  position: Vector3;
  gridPosition: Vector3;
  normal: Vector3;
}

export function faceletPose(index: number): FaceletPose {
  if (!Number.isInteger(index) || index < 0 || index >= 54) {
    throw new RangeError("facelet index must be between 0 and 53");
  }
  const face = FACES[Math.floor(index / 9)];
  const offset = index % 9;
  const row = Math.floor(offset / 3);
  const column = offset % 3;
  const [normal, right, up] = faceBasis[face];
  const gridPosition = add(normal, scale(right, column - 1), scale(up, 1 - row));
  const position = add(scale(normal, 1.52), scale(right, (column - 1) * 1.02), scale(up, (1 - row) * 1.02));
  return { position, gridPosition, normal };
}

export interface MoveSpec {
  axis: 0 | 1 | 2;
  sign: -1 | 1;
  angle: number;
}

export function moveSpec(move: Move): MoveSpec {
  const normal = faceBasis[move[0] as Face][0];
  const axis = normal.findIndex((value) => value !== 0) as 0 | 1 | 2;
  const sign = normal[axis] as -1 | 1;
  const visualTurns = move.endsWith("2") ? 2 : move.endsWith("'") ? -1 : 1;
  return { axis, sign, angle: -sign * visualTurns * (Math.PI / 2) };
}

export function isFaceletAffected(index: number, move: Move): boolean {
  const spec = moveSpec(move);
  return faceletPose(index).gridPosition[spec.axis] === spec.sign;
}

export function rotateVector(value: Vector3, axis: 0 | 1 | 2, angle: number): Vector3 {
  const cosine = Math.cos(angle);
  const sine = Math.sin(angle);
  const [x, y, z] = value;
  if (axis === 0) return [x, y * cosine - z * sine, y * sine + z * cosine];
  if (axis === 1) return [x * cosine + z * sine, y, -x * sine + z * cosine];
  return [x * cosine - y * sine, x * sine + y * cosine, z];
}

export function destinationFor(index: number, move: Move): number {
  return permutations[move][index];
}

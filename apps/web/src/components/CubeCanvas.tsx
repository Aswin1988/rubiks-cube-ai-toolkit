"use client";

import { OrbitControls, RoundedBox } from "@react-three/drei";
import { Canvas, useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import { Group, Quaternion, Vector3 as ThreeVector3 } from "three";
import {
  type Face,
  type Move,
  faceletPose,
  isFaceletAffected,
  moveSpec,
} from "@/lib/cube";

const COLORS: Record<Face, string> = {
  U: "#f8fafc",
  R: "#ef233c",
  F: "#22c55e",
  D: "#facc15",
  L: "#f97316",
  B: "#2563eb",
};

export interface CubeAnimation {
  move: Move;
  id: number;
}

interface Props {
  state: string;
  animation: CubeAnimation | null;
  durationMs: number;
  onAnimationComplete: () => void;
}

function Sticker({ index, color }: { index: number; color: Face }) {
  const pose = useMemo(() => faceletPose(index), [index]);
  const quaternion = useMemo(
    () =>
      new Quaternion().setFromUnitVectors(
        new ThreeVector3(0, 0, 1),
        new ThreeVector3(...pose.normal),
      ),
    [pose.normal],
  );
  return (
    <RoundedBox
      args={[0.88, 0.88, 0.045]}
      radius={0.09}
      smoothness={3}
      position={pose.position}
      quaternion={quaternion}
      castShadow
    >
      <meshStandardMaterial color={COLORS[color]} roughness={0.32} metalness={0.04} />
    </RoundedBox>
  );
}

function Core() {
  const cubies = useMemo(() => {
    const result: [number, number, number][] = [];
    for (const x of [-1, 0, 1]) {
      for (const y of [-1, 0, 1]) {
        for (const z of [-1, 0, 1]) result.push([x * 1.02, y * 1.02, z * 1.02]);
      }
    }
    return result;
  }, []);
  return (
    <group>
      {cubies.map((position) => (
        <RoundedBox
          key={position.join(":")}
          args={[0.98, 0.98, 0.98]}
          radius={0.09}
          smoothness={3}
          position={position}
          castShadow
          receiveShadow
        >
          <meshStandardMaterial color="#090b10" roughness={0.5} />
        </RoundedBox>
      ))}
    </group>
  );
}

function MovingLayer({
  indices,
  state,
  animation,
  durationMs,
  onComplete,
}: {
  indices: number[];
  state: string;
  animation: CubeAnimation;
  durationMs: number;
  onComplete: () => void;
}) {
  const group = useRef<Group>(null);
  const elapsed = useRef(0);
  const completed = useRef(false);
  const spec = moveSpec(animation.move);
  const axis = useMemo(() => {
    const vector = new ThreeVector3();
    vector.setComponent(spec.axis, 1);
    return vector;
  }, [spec.axis]);

  useEffect(() => {
    elapsed.current = 0;
    completed.current = false;
    group.current?.setRotationFromAxisAngle(axis, 0);
  }, [animation.id, axis]);

  useFrame((_frame, delta) => {
    if (!group.current || completed.current) return;
    elapsed.current += delta * 1000;
    const linear = Math.min(elapsed.current / durationMs, 1);
    const eased = 1 - Math.pow(1 - linear, 3);
    group.current.setRotationFromAxisAngle(axis, spec.angle * eased);
    if (linear === 1) {
      completed.current = true;
      onComplete();
    }
  });

  return (
    <group ref={group}>
      {indices.map((index) => (
        <Sticker key={index} index={index} color={state[index] as Face} />
      ))}
    </group>
  );
}

function CubeModel({ state, animation, durationMs, onAnimationComplete }: Props) {
  const all = useMemo(() => Array.from({ length: 54 }, (_, index) => index), []);
  const moving = animation ? all.filter((index) => isFaceletAffected(index, animation.move)) : [];
  const still = animation ? all.filter((index) => !isFaceletAffected(index, animation.move)) : all;
  return (
    <group rotation={[0.14, -0.22, 0]}>
      <Core />
      {still.map((index) => (
        <Sticker key={index} index={index} color={state[index] as Face} />
      ))}
      {animation && (
        <MovingLayer
          indices={moving}
          state={state}
          animation={animation}
          durationMs={durationMs}
          onComplete={onAnimationComplete}
        />
      )}
    </group>
  );
}

export function CubeCanvas(props: Props) {
  return (
    <Canvas shadows camera={{ position: [5.7, 4.7, 6.4], fov: 39 }} dpr={[1, 2]}>
      <color attach="background" args={["#071019"]} />
      <ambientLight intensity={1.15} />
      <directionalLight position={[5, 8, 5]} intensity={2.7} castShadow />
      <directionalLight position={[-4, -2, -3]} intensity={0.9} color="#4cc9f0" />
      <CubeModel {...props} />
      <OrbitControls
        makeDefault
        enablePan={false}
        enableDamping
        dampingFactor={0.07}
        minDistance={5.3}
        maxDistance={11}
      />
    </Canvas>
  );
}

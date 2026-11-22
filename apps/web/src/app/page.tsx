"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import type { CubeAnimation } from "@/components/CubeCanvas";
import { cubeApi, type SolveData } from "@/lib/api";
import { SOLVED_STATE, applyMove, inverseMove, type Move } from "@/lib/cube";

const CubeCanvas = dynamic(
  () => import("@/components/CubeCanvas").then((module) => module.CubeCanvas),
  { ssr: false, loading: () => <div className="canvasLoading">Preparing 3D scene…</div> },
);

type Busy = "scramble" | "solve" | null;
type PlaybackAnimation = CubeAnimation & { delta: -1 | 1 };

export default function Home() {
  const [state, setState] = useState(SOLVED_STATE);
  const [scramble, setScramble] = useState<Move[]>([]);
  const [solution, setSolution] = useState<Move[]>([]);
  const [cursor, setCursor] = useState(0);
  const [animation, setAnimation] = useState<PlaybackAnimation | null>(null);
  const [speed, setSpeed] = useState(1);
  const [autoplay, setAutoplay] = useState(false);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<SolveData | null>(null);
  const animationId = useRef(0);

  const beginForward = useCallback(() => {
    if (animation || cursor >= solution.length) return;
    animationId.current += 1;
    setAnimation({ move: solution[cursor], delta: 1, id: animationId.current });
  }, [animation, cursor, solution]);

  const beginBackward = useCallback(() => {
    if (animation || cursor <= 0) return;
    animationId.current += 1;
    setAutoplay(false);
    setAnimation({ move: inverseMove(solution[cursor - 1]), delta: -1, id: animationId.current });
  }, [animation, cursor, solution]);

  const finishAnimation = useCallback(() => {
    if (!animation) return;
    setState((current) => applyMove(current, animation.move));
    setCursor((current) => current + animation.delta);
    if (animation.delta === 1 && cursor + 1 >= solution.length) setAutoplay(false);
    setAnimation(null);
  }, [animation, cursor, solution.length]);

  useEffect(() => {
    if (!autoplay || animation || cursor >= solution.length) return;
    const timer = window.setTimeout(beginForward, 90);
    return () => window.clearTimeout(timer);
  }, [animation, autoplay, beginForward, cursor, solution.length]);

  const reset = useCallback(() => {
    setAutoplay(false);
    setAnimation(null);
    setState(SOLVED_STATE);
    setScramble([]);
    setSolution([]);
    setCursor(0);
    setMetrics(null);
    setError(null);
  }, []);

  const requestScramble = useCallback(async () => {
    setBusy("scramble");
    setAutoplay(false);
    setError(null);
    try {
      const result = await cubeApi.scramble(20);
      setState(result.state);
      setScramble(result.moves);
      setSolution([]);
      setCursor(0);
      setMetrics(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not generate a scramble.");
    } finally {
      setBusy(null);
    }
  }, []);

  const requestSolve = useCallback(async () => {
    setBusy("solve");
    setAutoplay(false);
    setAnimation(null);
    setError(null);
    try {
      const result = await cubeApi.solve(state);
      setSolution(result.moves);
      setCursor(0);
      setMetrics(result);
      setAutoplay(result.moves.length > 0);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The cube could not be solved.");
    } finally {
      setBusy(null);
    }
  }, [state]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement) return;
      if (event.key === "ArrowRight") {
        event.preventDefault();
        beginForward();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        beginBackward();
      } else if (event.key.toLowerCase() === "r") {
        reset();
      } else if (event.key.toLowerCase() === "s" && !busy) {
        void requestScramble();
      } else if (event.key === " ") {
        event.preventDefault();
        setAutoplay((playing) => !playing);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [beginBackward, beginForward, busy, requestScramble, reset]);

  const verification = metrics?.verification;
  const solved = state === SOLVED_STATE;
  const controlsDisabled = busy !== null || animation !== null;

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brandMark" aria-hidden="true"><i /><i /><i /></div>
        <div>
          <p className="eyebrow">Rubik&apos;s Cube AI Toolkit</p>
          <h1>Cube Lab</h1>
        </div>
        <div className={`engineStatus ${error ? "error" : ""}`}>
          <span aria-hidden="true" />
          {error ? "Action needed" : "Verified engine"}
        </div>
      </header>

      <section className="workspace" aria-label="Interactive Rubik's Cube">
        <div className="stage">
          <div className="stageHint">Drag to orbit · Pinch or scroll to zoom</div>
          <CubeCanvas
            state={state}
            animation={animation}
            durationMs={Math.round(520 / speed)}
            onAnimationComplete={finishAnimation}
          />
          <div className={`stateBadge ${solved ? "solved" : ""}`}>
            <span aria-hidden="true" /> {solved ? "Solved state" : `Move ${cursor} of ${solution.length}`}
          </div>
        </div>

        <aside className="panel" aria-label="Cube controls">
          <section className="controlSection heroControls">
            <div className="sectionHeading">
              <div><p className="kicker">Workspace</p><h2>Control the cube</h2></div>
              <span className="shortcutHint">S · R</span>
            </div>
            <div className="primaryGrid">
              <button className="button primary" onClick={() => void requestScramble()} disabled={controlsDisabled}>
                {busy === "scramble" ? <span className="spinner" /> : <span aria-hidden="true">✦</span>}
                {busy === "scramble" ? "Scrambling…" : "Scramble"}
              </button>
              <button className="button solve" onClick={() => void requestSolve()} disabled={controlsDisabled || solved}>
                {busy === "solve" ? <span className="spinner" /> : <span aria-hidden="true">◎</span>}
                {busy === "solve" ? "Solving…" : "Solve"}
              </button>
            </div>
            <button className="button reset" onClick={reset} disabled={controlsDisabled}>
              <span aria-hidden="true">↺</span> Reset cube
            </button>
          </section>

          {error && <div className="errorBox" role="alert"><strong>Couldn&apos;t complete that action.</strong>{error}</div>}

          <section className="controlSection playback">
            <div className="sectionHeading compact"><h2>Playback</h2><span>{cursor}/{solution.length} moves</span></div>
            <div className="transport" role="group" aria-label="Solution playback">
              <button aria-label="Step backward" onClick={beginBackward} disabled={controlsDisabled || cursor === 0}>‹</button>
              <button
                className="play"
                aria-label={autoplay ? "Pause solution" : "Play solution"}
                onClick={() => setAutoplay((playing) => !playing)}
                disabled={controlsDisabled || cursor >= solution.length}
              >{autoplay ? "Ⅱ" : "▶"}</button>
              <button aria-label="Step forward" onClick={beginForward} disabled={controlsDisabled || cursor >= solution.length}>›</button>
            </div>
            <label className="speedControl">
              <span>Animation speed</span><output>{speed.toFixed(2)}×</output>
              <input type="range" min="0.5" max="2" step="0.25" value={speed} onChange={(event) => setSpeed(Number(event.target.value))} />
            </label>
          </section>

          <Notation title="Scramble" moves={scramble} empty="Generate a scramble to begin." />
          <Notation title="Solution" moves={solution} activeIndex={cursor} empty="Solve the cube to reveal verified moves." />

          <section className="controlSection metrics" aria-label="Solve metrics">
            <div className="sectionHeading compact"><h2>Verification</h2>
              <span className={verification?.verified ? "verified" : "pending"}>{verification?.verified ? "Verified" : "Pending"}</span>
            </div>
            <dl>
              <div><dt>Solve time</dt><dd>{metrics ? `${metrics.elapsed_seconds.toFixed(3)}s` : "—"}</dd></div>
              <div><dt>HTM</dt><dd>{verification?.htm ?? "—"}</dd></div>
              <div><dt>QTM</dt><dd>{verification?.qtm ?? "—"}</dd></div>
            </dl>
          </section>
        </aside>
      </section>
      <p className="srOnly" aria-live="polite">{busy ? `${busy} in progress` : error ?? (solved ? "Cube is solved" : "Cube state updated")}</p>
    </main>
  );
}

function Notation({ title, moves, activeIndex, empty }: { title: string; moves: Move[]; activeIndex?: number; empty: string }) {
  return (
    <section className="controlSection notation">
      <div className="sectionHeading compact"><h2>{title}</h2><span>{moves.length ? `${moves.length} moves` : "—"}</span></div>
      {moves.length ? (
        <div className="moveList" aria-label={`${title} notation`}>
          {moves.map((move, index) => <code className={activeIndex === index ? "active" : activeIndex !== undefined && index < activeIndex ? "done" : ""} key={`${move}-${index}`}>{move}</code>)}
        </div>
      ) : <p className="emptyText">{empty}</p>}
    </section>
  );
}

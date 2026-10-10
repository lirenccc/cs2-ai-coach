import { useEffect, useMemo, useState } from "react";
import "./App.css";
import { asBridgeError, formatBridgeError } from "./bridgeError";
import {
  getAnalyzerHealth,
  getDesktopHealth,
  getMatchReview,
  importDemo,
} from "./native";
import { MatchReviewPage } from "./review/MatchReviewPage";
import { analyzerPill } from "./status";
import type {
  AnalyzerHealth,
  BridgeError,
  DesktopHealth,
  MatchReview,
} from "./types";

type State<T> =
  | { kind: "loading" }
  | { kind: "ready"; value: T }
  | { kind: "error"; error: BridgeError };

function StatusPill({ ok, text }: { ok: boolean; text: string }) {
  return <span className={`pill ${ok ? "ok" : "bad"}`}>{text}</span>;
}

export default function App() {
  const [desktop, setDesktop] = useState<State<DesktopHealth>>({
    kind: "loading",
  });
  const [analyzer, setAnalyzer] = useState<State<AnalyzerHealth>>({
    kind: "loading",
  });
  const [demoPath, setDemoPath] = useState("");
  const [matchId, setMatchId] = useState("");
  const [review, setReview] = useState<State<MatchReview> | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setDesktop({ kind: "loading" });
    setAnalyzer({ kind: "loading" });

    const [desktopResult, analyzerResult] = await Promise.allSettled([
      getDesktopHealth(),
      getAnalyzerHealth(),
    ]);

    setDesktop(
      desktopResult.status === "fulfilled"
        ? { kind: "ready", value: desktopResult.value }
        : {
            kind: "error",
            error: {
              code: "DESKTOP_BRIDGE",
              message: String(desktopResult.reason),
              retryable: true,
            },
          },
    );

    setAnalyzer(
      analyzerResult.status === "fulfilled"
        ? { kind: "ready", value: analyzerResult.value }
        : { kind: "error", error: asBridgeError(analyzerResult.reason) },
    );
  }

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => {
      void getAnalyzerHealth()
        .then((value) => setAnalyzer({ kind: "ready", value }))
        .catch((error) =>
          setAnalyzer({ kind: "error", error: asBridgeError(error) }),
        );
    }, 5000);
    return () => window.clearInterval(timer);
  }, []);

  const analyzerOkay = useMemo(
    () => analyzer.kind === "ready" && analyzer.value.status === "ok",
    [analyzer],
  );
  const analyzerBadge = analyzerPill(
    analyzer.kind,
    analyzer.kind === "ready" ? analyzer.value.status : undefined,
  );

  async function onImport() {
    if (!demoPath.trim()) return;
    setBusy(true);
    setReview({ kind: "loading" });
    try {
      const imported = await importDemo(demoPath.trim());
      setMatchId(imported.match_id);
      const payload = await getMatchReview(imported.match_id);
      setReview({ kind: "ready", value: payload });
    } catch (error) {
      setReview({ kind: "error", error: asBridgeError(error) });
    } finally {
      setBusy(false);
    }
  }

  async function onOpenReview() {
    if (!matchId.trim()) return;
    setBusy(true);
    setReview({ kind: "loading" });
    try {
      const payload = await getMatchReview(matchId.trim());
      setReview({ kind: "ready", value: payload });
    } catch (error) {
      setReview({ kind: "error", error: asBridgeError(error) });
    } finally {
      setBusy(false);
    }
  }

  if (review?.kind === "ready") {
    return (
      <main className="shell wide">
        <MatchReviewPage
          review={review.value}
          onBack={() => setReview(null)}
        />
        <footer>
          Offline demo review only · No injection · No process-memory access · No
          live competitive assistance
        </footer>
      </main>
    );
  }

  return (
    <main className="shell">
      <header className="hero">
        <div>
          <div className="eyebrow">CS2 AI COACH · P1.4</div>
          <h1>Demo review, grounded in evidence.</h1>
          <p>
            打开已解析比赛的 Match Review：回合 / 时间线 / 确定性 Incident /
            结构化证据。不需要 CS2、NetCon、截图或 AI。
          </p>
        </div>
        <button type="button" onClick={() => void refresh()}>
          刷新状态
        </button>
      </header>

      <section className="grid">
        <article className="card">
          <div className="cardTop">
            <h2>Desktop bridge</h2>
            <StatusPill
              ok={desktop.kind === "ready"}
              text={
                desktop.kind === "ready" ? "READY" : desktop.kind.toUpperCase()
              }
            />
          </div>
          {desktop.kind === "ready" ? (
            <dl>
              <dt>App</dt>
              <dd>{desktop.value.app}</dd>
              <dt>Version</dt>
              <dd>{desktop.value.version}</dd>
              <dt>Platform</dt>
              <dd>{desktop.value.platform}</dd>
            </dl>
          ) : (
            <p className="muted">
              {desktop.kind === "error"
                ? formatBridgeError(desktop.error)
                : "Checking Tauri bridge…"}
            </p>
          )}
        </article>

        <article className="card">
          <div className="cardTop">
            <h2>Analyzer sidecar</h2>
            <StatusPill ok={analyzerOkay} text={analyzerBadge.text} />
          </div>
          {analyzer.kind === "ready" ? (
            <dl>
              <dt>Version</dt>
              <dd>{analyzer.value.version}</dd>
              <dt>Parser</dt>
              <dd>{analyzer.value.parser.name}</dd>
              <dt>Parser available</dt>
              <dd>{String(analyzer.value.parser.available)}</dd>
            </dl>
          ) : (
            <p className="muted">
              {analyzer.kind === "error"
                ? formatBridgeError(analyzer.error)
                : "Checking analyzer…"}
            </p>
          )}
        </article>
      </section>

      <section className="card reviewOpen" aria-label="Open match review">
        <div className="eyebrow">MATCH REVIEW</div>
        <h2>打开离线复盘</h2>
        <p className="muted">
          通过 Tauri 桥调用 analyzer；renderer 不会拿到 sidecar token 或随机端口。
        </p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void onImport();
          }}
        >
          <label>
            Demo path
            <input
              aria-label="Demo path"
              value={demoPath}
              onChange={(event) => setDemoPath(event.target.value)}
              placeholder="C:\demos\match.dem"
            />
          </label>
          <button type="submit" disabled={busy || !demoPath.trim()}>
            Import & review
          </button>
        </form>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void onOpenReview();
          }}
        >
          <label>
            Match id
            <input
              aria-label="Match id"
              value={matchId}
              onChange={(event) => setMatchId(event.target.value)}
              placeholder="uuid from import"
            />
          </label>
          <button type="submit" disabled={busy || !matchId.trim()}>
            Open review
          </button>
        </form>
        {review?.kind === "loading" ? (
          <p className="muted" role="status">
            Loading match review…
          </p>
        ) : null}
        {review?.kind === "error" ? (
          <p className="muted" role="alert">
            {formatBridgeError(review.error)}
          </p>
        ) : null}
      </section>

      <footer>
        Offline demo review only · No injection · No process-memory access · No
        live competitive assistance
      </footer>
    </main>
  );
}

import { useEffect, useMemo, useState } from "react";
import "./App.css";
import { asBridgeError, formatBridgeError } from "./bridgeError";
import { getAnalyzerHealth, getDesktopHealth } from "./native";
import { analyzerPill } from "./status";
import type { AnalyzerHealth, BridgeError, DesktopHealth } from "./types";

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

  return (
    <main className="shell">
      <header className="hero">
        <div>
          <div className="eyebrow">CS2 AI COACH · v0.1</div>
          <h1>Demo review, grounded in evidence.</h1>
          <p>
            当前骨架先验证解析、回放、捕捉和 AI 四条技术链路；不会把未验证的
            CS2 集成伪装成完成状态。
          </p>
        </div>
        <button onClick={() => void refresh()}>刷新状态</button>
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

      <section className="card workflow">
        <div className="eyebrow">IMPLEMENTATION ORDER</div>
        <h2>先证明四条链路，再做产品 UI</h2>
        <ol>
          <li>
            <strong>Demo Parser</strong>
            <span>真实 .dem → normalized facts</span>
          </li>
          <li>
            <strong>NetCon</strong>
            <span>外部连接 CS2 → load / pause / seek</span>
          </li>
          <li>
            <strong>Capture</strong>
            <span>CS2 window → verified keyframes</span>
          </li>
          <li>
            <strong>AI</strong>
            <span>facts + frames → structured coaching</span>
          </li>
        </ol>
      </section>

      <footer>
        Offline demo review only · No injection · No process-memory access · No
        live competitive assistance
      </footer>
    </main>
  );
}

import { UpstreamMockConsole } from "./upstream-mock-console";

export default function Page() {
  return (
    <main>
      <header className="hero">
        <div>
          <p className="eyebrow">Development tool · Next.js full stack</p>
          <h1>SC Upstream Lab</h1>
          <p className="lede">
            Create upstream behavior, publish deterministic inspections, and watch what the platform
            can observe—without production code or hidden seed scripts.
          </p>
        </div>
        <div className="protocol-card" aria-label="Simulator topology">
          <span>Control</span>
          <strong>Next.js · :8094</strong>
          <span>Read protocols</span>
          <strong>gRPC :9091 · Flight :9093</strong>
        </div>
      </header>
      <UpstreamMockConsole />
    </main>
  );
}

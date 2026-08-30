import { UpstreamMockConsole } from "./upstream-mock-console";

export default function Page() {
  return (
    <main>
      <header className="page-header">
        <div>
          <h1>Upstream mock tools</h1>
          <p>Send source events, generate fixtures, and inspect state visible to local services.</p>
        </div>
        <div className="endpoints" aria-label="Simulator endpoints">
          <code>HTTP control :8094</code>
          <code>gRPC read :9091</code>
          <code>Flight read :9093</code>
        </div>
      </header>
      <UpstreamMockConsole />
    </main>
  );
}
